from mitmproxy import http, ctx
import time
import sys
import os
from typing import Optional, Dict

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from src.utils.config_loader import config_loader
from src.core.upstream_detector import UpstreamDetector
from src.core.csv_manager import CSVStatusManager
from src.extractors.netease_extractor import NeteaseExtractor
from src.extractors.quark_extractor import QuarkExtractor

class SmartChainProxy:
    def __init__(self):
        self.config = None
        self.services_config = None
        self.detector = None
        self.csv_manager = None
        self.extractors = {}
        self.upstream_proxy = None
        self.session_id = f"{int(time.time())}_proxy"
        self.request_count = 0
        self.extract_count = 0
        
    def load(self, loader):
        """mitmproxy加载时初始化"""
        try:
            print("初始化智能代理...")
            
            # 加载配置
            self.config = config_loader.get_proxy_config()['proxy']
            self.services_config = config_loader.get_enabled_services()
            
            # 初始化组件
            self.detector = UpstreamDetector(config_loader.get_proxy_config()['proxy'])
            self.csv_manager = CSVStatusManager()
            
            # 初始化提取器
            self._init_extractors()
            
            # 检测上游代理
            self.upstream_proxy = self.detector.detect_active_upstream()
            
            # 开始会话
            self.csv_manager.start_session(self.session_id, self.upstream_proxy)
            
            print(f"[OK] 代理初始化完成")
            print(f"上游代理: {self.upstream_proxy or '直连'}")
            print(f"监控服务: {', '.join(self.services_config.keys())}")
            
        except Exception as e:
            print(f"初始化失败: {e}")
            raise
    
    def _init_extractors(self):
        """初始化Cookie提取器"""
        for service_name, service_config in self.services_config.items():
            if service_name == 'netease':
                self.extractors[service_name] = NeteaseExtractor(service_config)
            elif service_name == 'quark':
                self.extractors[service_name] = QuarkExtractor(service_config)
            # 可以在这里添加更多提取器
            
        print(f"已加载 {len(self.extractors)} 个提取器")
    
    def request(self, flow: http.HTTPFlow):
        """处理HTTP请求"""
        self.request_count += 1
        
        # 1. 识别服务
        domain = flow.request.pretty_host
        service = self._identify_service(domain)
        
        # 调试: 打印所有请求和cookie信息
        print(f"\n[请求 #{self.request_count}] {domain} - {flow.request.path}")
        
        if flow.request.cookies:
            print(f"  请求Cookie ({len(flow.request.cookies)}个):")
            for name, value in flow.request.cookies.items():
                print(f"    {name}={value[:50]}{'...' if len(str(value)) > 50 else ''}")
        else:
            print(f"  请求Cookie: 无")
            
        if service:
            print(f"  匹配服务: {service}")
            if self._should_extract(service):
                flow.metadata['automate_extract'] = service
                flow.metadata['automate_url'] = flow.request.pretty_url
                print(f"  ✓ 已标记提取")
            else:
                print(f"  - 跳过提取 (间隔未到)")
        else:
            print(f"  匹配服务: 无")
        
        # 2. 设置上游代理链  
        if self.upstream_proxy:
            # 定期检查上游代理状态
            if self.request_count % 100 == 0:  # 每100个请求检查一次
                current_upstream = self.detector.detect_active_upstream()
                if current_upstream != self.upstream_proxy:
                    self.upstream_proxy = current_upstream
                    print(f"上游代理已切换: {current_upstream}")
            
            if self.upstream_proxy:
                flow.request.upstream_proxy = self.upstream_proxy
    
    def response(self, flow: http.HTTPFlow):
        """处理HTTP响应"""
        service = flow.metadata.get('automate_extract')
        
        # 调试: 打印响应cookie信息
        print(f"[响应] {flow.request.pretty_host} - 状态:{flow.response.status_code}")
        
        if flow.response.cookies:
            print(f"  响应Cookie ({len(flow.response.cookies)}个):")
            for name, value in flow.response.cookies.items():
                print(f"    {name}={value[:50]}{'...' if len(str(value)) > 50 else ''}")
        else:
            print(f"  响应Cookie: 无")
            
        if not service:
            print(f"  服务: 未标记提取")
            return
        
        print(f"  服务: {service} (准备提取)")
        url = flow.metadata.get('automate_url', '')
        
        # 提取Cookie
        extracted = False
        
        # 从请求Cookie中提取
        if flow.request.cookies:
            print(f"  尝试从请求Cookie提取...")
            cookie_data = self._extract_cookies(
                service, 
                dict(flow.request.cookies), 
                'request', 
                dict(flow.request.headers),
                url
            )
            if cookie_data:
                extracted = True
                print(f"  ✓ 请求Cookie提取成功")
        
        # 从响应Cookie中提取
        if flow.response.cookies:
            print(f"  尝试从响应Cookie提取...")
            cookie_data = self._extract_cookies(
                service,
                dict(flow.response.cookies),
                'response',
                dict(flow.response.headers), 
                url
            )
            if cookie_data:
                extracted = True
                print(f"  ✓ 响应Cookie提取成功")
        
        # 更新状态
        if extracted:
            self.extract_count += 1
            self.csv_manager.update_extract_status(
                service, 
                time.time(),
                self.services_config[service]['output_file']
            )
            print(f"  ✓ 状态已更新, 总提取次数: {self.extract_count}")
        else:
            print(f"  - 无有效cookie提取")
    
    def _identify_service(self, domain: str) -> Optional[str]:
        """识别域名属于哪个服务"""
        for service, config in self.services_config.items():
            if any(target_domain in domain for target_domain in config['domains']):
                return service
        return None
    
    def _should_extract(self, service: str) -> bool:
        """判断是否应该提取Cookie"""
        if service not in self.services_config:
            return False
        
        interval = self.services_config[service]['extract_interval']
        return self.csv_manager.should_extract(service, interval)
    
    def _extract_cookies(self, service: str, cookies: dict, source: str, headers: dict, url: str) -> bool:
        """提取并保存Cookie"""
        extractor = self.extractors.get(service)
        if not extractor:
            return False
        
        cookie_data = extractor.process_cookies(
            cookies, 
            source, 
            headers=headers, 
            url=url
        )
        
        if cookie_data:
            success = extractor.save_cookie(cookie_data)
            return success
        
        return False
    
    def done(self):
        """代理关闭时的清理工作"""
        try:
            if hasattr(self, 'csv_manager') and self.csv_manager:
                self.csv_manager.end_session(
                    self.session_id,
                    self.request_count,
                    self.extract_count
                )
            
            print(f"\n会话结束统计:")
            print(f"   请求总数: {self.request_count}")
            print(f"   提取次数: {self.extract_count}")
            print(f"   会话ID: {self.session_id}")
            
        except Exception as e:
            print(f"清理时出错: {e}")

# mitmproxy插件入口
addons = [SmartChainProxy()]