from abc import ABC, abstractmethod
from typing import Dict, Optional, Any
import json
import time
from pathlib import Path

class BaseExtractor(ABC):
    """Cookie提取器基类"""
    
    def __init__(self, service_name: str, config: dict):
        self.service_name = service_name
        self.config = config
        self.output_file = config.get('output_file', f'data/outputs/{service_name}_cookie.json')
        self.cookie_format = config.get('cookie_format', 'standard')
    
    @abstractmethod
    def extract_from_request(self, cookies: dict, headers: dict, url: str) -> Optional[Dict]:
        """从请求中提取Cookie"""
        pass
    
    @abstractmethod
    def extract_from_response(self, cookies: dict, headers: dict, url: str) -> Optional[Dict]:
        """从响应中提取Cookie"""
        pass
    
    def process_cookies(self, cookies: dict, source: str, **kwargs) -> Optional[Dict]:
        """处理Cookie数据"""
        if source == 'request':
            return self.extract_from_request(cookies, kwargs.get('headers', {}), kwargs.get('url', ''))
        elif source == 'response':
            return self.extract_from_response(cookies, kwargs.get('headers', {}), kwargs.get('url', ''))
        
        return None
    
    def format_cookie_output(self, cookie_data: dict) -> dict:
        """格式化Cookie输出"""
        base_output = {
            'service': self.service_name,
            'timestamp': int(time.time()),
            'extracted_at': time.ctime(),
            'cookie_data': cookie_data
        }
        
        if self.cookie_format == 'netease_auth':
            # 网易云音乐特殊格式
            cookie_string = '; '.join([f'{k}={v}' for k, v in cookie_data.items()])
            return {
                'cookie': cookie_string,
                'timestamp': base_output['timestamp'],
                'profile': {},  # 可以从cookie中提取用户信息
                'account': {}
            }
        else:
            # 标准格式
            return base_output
    
    def save_cookie(self, cookie_data: dict) -> bool:
        """保存Cookie到文件"""
        try:
            # 确保输出目录存在
            output_path = Path(self.output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 格式化输出
            formatted_data = self.format_cookie_output(cookie_data)
            
            # 写入文件
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(formatted_data, f, indent=2, ensure_ascii=False)
            
            print(f"{self.service_name} Cookie已保存: {self.output_file}")
            return True
            
        except Exception as e:
            print(f"保存Cookie失败: {e}")
            return False
    
    def is_valid_cookie(self, cookies: dict) -> bool:
        """验证Cookie是否有效"""
        return bool(cookies and any(cookies.values()))
    
    def get_cookie_preview(self, cookies: dict) -> str:
        """获取Cookie预览（用于日志）"""
        if not cookies:
            return "Empty"
        
        # 显示前几个重要的cookie
        preview_keys = list(cookies.keys())[:3]
        preview = []
        
        for key in preview_keys:
            value = str(cookies[key])
            if len(value) > 10:
                value = value[:10] + "..."
            preview.append(f"{key}={value}")
        
        result = "; ".join(preview)
        if len(cookies) > 3:
            result += f" (+{len(cookies) - 3} more)"
        
        return result