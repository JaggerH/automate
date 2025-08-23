from typing import Dict, Optional
from .base_extractor import BaseExtractor

class QuarkExtractor(BaseExtractor):
    """夸克网盘Cookie提取器"""
    
    def __init__(self, config: dict):
        super().__init__('quark', config)
        
        # 夸克关键Cookie字段
        self.key_cookies = [
            '__pus',        # 用户会话
            'q_c1',         # 用户标识1  
            '__puus',       # 用户标识2
            'kw_token',     # 访问令牌
            '__kp',         # 设备标识
            '__kps'         # 会话标识
        ]
    
    def extract_from_request(self, cookies: dict, headers: dict, url: str) -> Optional[Dict]:
        """从请求中提取Cookie"""
        return self._extract_quark_cookies(cookies, 'request', url)
    
    def extract_from_response(self, cookies: dict, headers: dict, url: str) -> Optional[Dict]:
        """从响应中提取Cookie"""  
        return self._extract_quark_cookies(cookies, 'response', url)
    
    def _extract_quark_cookies(self, cookies: dict, source: str, url: str) -> Optional[Dict]:
        """提取夸克Cookie"""
        if not self.is_valid_cookie(cookies):
            return None
        
        # 检查是否包含关键Cookie
        key_cookies_found = any(key in cookies for key in self.key_cookies)
        
        if not key_cookies_found:
            return None
        
        # 过滤和清理Cookie
        cleaned_cookies = {}
        
        for key, value in cookies.items():
            # 跳过空值
            if not value:
                continue
                
            # 夸克相关Cookie
            if (key in self.key_cookies or 
                key.startswith('__pu') or 
                key.startswith('q_') or
                key.startswith('kw_') or
                key.startswith('__k')):
                cleaned_cookies[key] = str(value)
        
        if not cleaned_cookies:
            return None
        
        print(f"夸克Cookie提取成功: {self.get_cookie_preview(cleaned_cookies)} (来源: {source})")
        
        return cleaned_cookies
    
    def is_valid_cookie(self, cookies: dict) -> bool:
        """验证夸克Cookie是否有效"""
        if not cookies:
            return False
        
        # 至少需要包含__pus或__puus（重要的身份标识）
        return any(key in cookies and cookies[key] for key in ['__pus', '__puus', 'q_c1'])
    
    def format_cookie_output(self, cookie_data: dict) -> dict:
        """格式化为标准格式"""
        cookie_string = '; '.join([f'{k}={v}' for k, v in cookie_data.items()])
        
        return {
            'service': 'quark',
            'timestamp': int(self._get_current_timestamp()),
            'extracted_at': self._get_current_time_string(),
            'cookie_string': cookie_string,
            'cookie_data': cookie_data
        }
    
    def _get_current_timestamp(self) -> float:
        """获取当前时间戳"""
        import time
        return time.time()
    
    def _get_current_time_string(self) -> str:
        """获取当前时间字符串"""
        import time
        return time.ctime()