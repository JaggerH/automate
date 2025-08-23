import socket
import time
import requests
from typing import List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

class PortScanner:
    def __init__(self, timeout: int = 2):
        self.timeout = timeout
    
    def is_port_open(self, host: str, port: int) -> bool:
        """检查端口是否开放"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout)
                return sock.connect_ex((host, port)) == 0
        except Exception:
            return False
    
    def scan_ports(self, host: str, ports: List[int]) -> List[int]:
        """批量扫描端口"""
        open_ports = []
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_port = {
                executor.submit(self.is_port_open, host, port): port 
                for port in ports
            }
            
            for future in as_completed(future_to_port):
                port = future_to_port[future]
                try:
                    if future.result():
                        open_ports.append(port)
                except Exception as e:
                    print(f"扫描端口 {port} 出错: {e}")
        
        return sorted(open_ports)
    
    def find_available_port(self, host: str, start_port: int, max_attempts: int = 10) -> Optional[int]:
        """寻找可用端口"""
        for i in range(max_attempts):
            port = start_port + i
            if not self.is_port_open(host, port):
                return port
        return None
    
    def test_proxy(self, host: str, port: int, protocol: str = "http") -> bool:
        """测试代理是否可用"""
        if not self.is_port_open(host, port):
            return False
        
        try:
            proxy_url = f"{protocol}://{host}:{port}"
            proxies = {
                'http': proxy_url,
                'https': proxy_url
            }
            
            # 使用httpbin测试代理
            response = requests.get(
                'http://httpbin.org/ip',
                proxies=proxies,
                timeout=5
            )
            return response.status_code == 200
            
        except Exception:
            return False