import socket
import time
import requests
from typing import List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from ..utils.port_scanner import PortScanner

class UpstreamDetector:
    def __init__(self, config):
        self.config = config
        self.scanner = PortScanner()
        self.active_upstream = None
        self.last_check = 0
        self.check_interval = self.config['upstream']['fallback']['retry_interval']
        
    def detect_active_upstream(self) -> Optional[str]:
        """检测可用的上游代理"""
        # 如果未启用上游代理，返回None
        if not self.config['upstream']['enabled']:
            return None
            
        # 检查缓存
        if time.time() - self.last_check < self.check_interval:
            return self.active_upstream
            
        clash_config = self.config['upstream']['clash_detection']
        hosts = clash_config['hosts']
        ports = clash_config['ports']
        protocols = clash_config['protocols']
        
        print("检测可用的上游代理...")
        
        # 并发检测所有端口
        candidates = []
        for host in hosts:
            for port in ports:
                for protocol in protocols:
                    candidates.append((host, port, protocol))
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_candidate = {
                executor.submit(self._test_proxy, host, port, protocol): (host, port, protocol)
                for host, port, protocol in candidates
            }
            
            for future in as_completed(future_to_candidate):
                host, port, protocol = future_to_candidate[future]
                try:
                    if future.result():
                        upstream_url = f"{protocol}://{host}:{port}"
                        print(f"检测到可用上游代理: {upstream_url}")
                        self.active_upstream = upstream_url
                        self.last_check = time.time()
                        return upstream_url
                except Exception as e:
                    pass  # 静默处理单个检测失败
        
        # 未找到可用代理
        if self.config['upstream']['fallback']['direct_connection']:
            print("[WARNING] 未检测到可用的上游代理，将使用直连")
            self.active_upstream = None
        else:
            print("[ERROR] 未检测到可用的上游代理，且禁用了直连")
            
        self.last_check = time.time()
        return self.active_upstream
    
    def _test_proxy(self, host: str, port: int, protocol: str) -> bool:
        """测试代理是否可用"""
        try:
            # 先检查端口是否开放
            print(f"  测试端口 {host}:{port} ({protocol})...")
            if not self.scanner.is_port_open(host, port):
                print(f"  端口 {port} 未开放")
                return False
            
            print(f"  端口 {port} 已开放，测试代理功能...")
            
            # 通过代理测试HTTP请求，使用多个测试URL
            proxy_url = f"{protocol}://{host}:{port}"
            proxies = {
                'http': proxy_url,
                'https': proxy_url
            }
            
            # 测试URL列表，优先使用国内可访问的
            test_urls = [
                'http://httpbin.org/ip',
                'http://www.baidu.com',
                'http://www.google.com',
            ]
            
            for test_url in test_urls:
                try:
                    print(f"    尝试通过代理访问: {test_url}")
                    response = requests.get(
                        test_url,
                        proxies=proxies,
                        timeout=5,
                        headers={'User-Agent': 'Mozilla/5.0 automate-proxy-test'}
                    )
                    
                    if response.status_code == 200:
                        print(f"  代理 {protocol}://{host}:{port} 测试成功")
                        return True
                        
                except Exception as e:
                    print(f"    测试URL {test_url} 失败: {str(e)[:50]}")
                    continue
            
            print(f"  代理 {protocol}://{host}:{port} 所有测试URL均失败")
            return False
            
        except Exception as e:
            print(f"  测试代理 {protocol}://{host}:{port} 异常: {e}")
            return False
    
    def is_upstream_available(self) -> bool:
        """检查当前上游代理是否可用"""
        if not self.active_upstream:
            return False
            
        # 解析代理URL
        try:
            import urllib.parse
            parsed = urllib.parse.urlparse(self.active_upstream)
            return self.scanner.test_proxy(parsed.hostname, parsed.port, parsed.scheme)
        except Exception:
            return False
    
    def get_status_info(self) -> dict:
        """获取上游代理状态信息"""
        return {
            'enabled': self.config['upstream']['enabled'],
            'active_upstream': self.active_upstream,
            'last_check': time.ctime(self.last_check) if self.last_check else 'Never',
            'next_check': time.ctime(self.last_check + self.check_interval) if self.last_check else 'Now',
            'available': self.is_upstream_available()
        }