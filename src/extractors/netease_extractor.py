from typing import Dict, Optional
from .base_extractor import BaseExtractor

class NeteaseExtractor(BaseExtractor):
    """网易云音乐Cookie提取器"""
    
    def __init__(self, config: dict):
        super().__init__('netease', config)
        
        # 网易云关键Cookie字段
        self.key_cookies = [
            'MUSIC_U',      # 用户身份标识
            '__csrf',       # CSRF令牌  
            'NMTID',        # 设备ID
            'WEVNSM',       # 会话标识
            '__remember_me' # 记住登录
        ]
    
    def extract_from_request(self, cookies: dict, headers: dict, url: str) -> Optional[Dict]:
        """从请求中提取Cookie"""
        return self._extract_netease_cookies(cookies, 'request', url)
    
    def extract_from_response(self, cookies: dict, headers: dict, url: str) -> Optional[Dict]:
        """从响应中提取Cookie"""  
        return self._extract_netease_cookies(cookies, 'response', url)
    
    def _extract_netease_cookies(self, cookies: dict, source: str, url: str) -> Optional[Dict]:
        """提取网易云Cookie"""
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
                
            # 网易云相关Cookie通常以这些开头
            if (key in self.key_cookies or 
                key.startswith('MUSIC_') or 
                key.startswith('__') or
                key.startswith('NMTID') or
                key.startswith('WEVNSM')):
                cleaned_cookies[key] = str(value)
        
        if not cleaned_cookies:
            return None
        
        print(f"网易云Cookie提取成功: {self.get_cookie_preview(cleaned_cookies)} (来源: {source})")
        
        return cleaned_cookies
    
    def is_valid_cookie(self, cookies: dict) -> bool:
        """验证网易云Cookie是否有效"""
        if not cookies:
            return False
        
        # 至少需要包含MUSIC_U（最重要的身份标识）
        return 'MUSIC_U' in cookies and cookies['MUSIC_U']
    
    def format_cookie_output(self, cookie_data: dict) -> dict:
        """格式化为网易云音乐sync兼容的格式"""
        cookie_string = '; '.join([f'{k}={v}' for k, v in cookie_data.items()])
        
        # 尝试从MUSIC_U中解析用户信息（如果需要）
        profile = {}
        account = {}
        
        if 'MUSIC_U' in cookie_data:
            # 这里可以根据需要解析MUSIC_U中的用户信息
            # 暂时留空，music-sync会通过API获取
            pass
        
        return {
            'cookie': cookie_string,
            'timestamp': int(self._get_current_timestamp()),
            'profile': profile,
            'account': account,
            'loginTime': int(self._get_current_timestamp() * 1000)  # 毫秒时间戳
        }
    
    def _get_current_timestamp(self) -> float:
        """获取当前时间戳"""
        import time
        return time.time()