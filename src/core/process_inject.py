#!/usr/bin/env python3
"""
Process Injection Mode Extractor
进程注入模式提取器

基于mitmproxy PID注入，提供Cookie和播放列表提取功能
参考smart_proxy架构，专注于进程注入模式
"""
import subprocess
import sys
import os
import psutil
import time
from pathlib import Path
from typing import List, Dict, Optional

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from src.utils.config_loader import config_loader
from src.core.csv_manager import CSVStatusManager
from src.extractors.netease_extractor import NeteaseExtractor
from src.extractors.quark_extractor import QuarkExtractor

class ProcessInject:
    """进程注入模式提取器"""
    
    def __init__(self):
        self.services_config = None
        self.csv_manager = None
        self.extractors = {}
        self.session_id = f"{int(time.time())}_inject"
        self.request_count = 0
        self.extract_count = 0
        
        # 目标进程映射
        self.target_processes = {
            'netease': ['cloudmusic.exe', 'CloudMusic.exe'],
            'quark': ['QuarkCloudDrive.exe', 'quark.exe']
        }
    
    def load(self, loader):
        """mitmproxy加载时初始化"""
        try:
            print("初始化进程注入提取器...")
            
            # 加载服务配置
            self.services_config = config_loader.get_enabled_services()
            
            # 初始化CSV管理器
            self.csv_manager = CSVStatusManager()
            
            # 初始化提取器
            self._init_extractors()
            
            # 开始会话
            self.csv_manager.start_session(self.session_id, "PID_Injection")
            
            print(f"已加载服务: {list(self.services_config.keys())}")
            
        except Exception as e:
            print(f"初始化失败: {e}")
            raise
    
    def _init_extractors(self):
        """初始化提取器"""
        for service_name, service_config in self.services_config.items():
            if service_name == 'netease':
                self.extractors[service_name] = NeteaseExtractor(service_config)
            elif service_name == 'quark':
                self.extractors[service_name] = QuarkExtractor(service_config)
            
            print(f"已初始化 {service_name} 提取器")
    
    def detect_processes(self, service: str) -> List[int]:
        """检测指定服务的目标进程"""
        pids = []
        target_names = self.target_processes.get(service, [])
        
        if not target_names:
            return pids
        
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] in target_names:
                    pids.append(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        return pids
    
    def get_all_target_pids(self) -> Dict[str, List[int]]:
        """获取所有启用服务的目标进程PID"""
        all_pids = {}
        
        for service_name in self.services_config.keys():
            pids = self.detect_processes(service_name)
            if pids:
                all_pids[service_name] = pids
        
        return all_pids
    
    def request(self, flow):
        """处理HTTP请求"""
        self.request_count += 1
        
        # 检查是否为目标服务域名
        target_service = self._identify_service(flow.request.pretty_host)
        if not target_service:
            return
        
        # 获取对应的提取器
        extractor = self.extractors.get(target_service)
        if not extractor:
            return
        
        # 委托给提取器处理
        try:
            extractor.handle_request(flow)
        except Exception as e:
            print(f"处理请求时出错 ({target_service}): {e}")
    
    def response(self, flow):
        """处理HTTP响应"""
        # 检查是否为目标服务域名
        target_service = self._identify_service(flow.request.pretty_host)
        if not target_service:
            return
        
        # 获取对应的提取器
        extractor = self.extractors.get(target_service)
        if not extractor:
            return
        
        # 委托给提取器处理
        try:
            result = extractor.handle_response(flow)
            if result:
                self.extract_count += 1
                print(f"成功提取 {target_service} 数据")
        except Exception as e:
            print(f"处理响应时出错 ({target_service}): {e}")
    
    def _identify_service(self, host: str) -> Optional[str]:
        """识别主机属于哪个服务"""
        for service_name, service_config in self.services_config.items():
            domains = service_config.get('domains', [])
            if any(domain in host.lower() for domain in domains):
                return service_name
        return None
    
    def done(self):
        """代理关闭时的统计"""
        if self.csv_manager:
            self.csv_manager.end_session(self.session_id, self.extract_count)
        
        print(f"\n进程注入会话结束")
        print(f"总请求: {self.request_count}")
        print(f"成功提取: {self.extract_count}")
        print("=" * 60)

# mitmproxy插件入口
addons = [ProcessInject()]