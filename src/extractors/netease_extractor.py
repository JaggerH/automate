from typing import Dict, Optional
import json
import time
import os
from pathlib import Path
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
        
        # 功能配置
        self.features = config.get('features', {})
        self.cookie_config = self.features.get('extract_cookie', {})
        self.playlist_config = self.features.get('extract_playlist', {})
        
        # 初始化EAPI解密工具
        self.crypto = None
        self.target_playlist_ids = self.playlist_config.get('target_ids', [])
        
        # 延迟导入NeteaseCrypto
        if self.playlist_config.get('enabled', False):
            try:
                from src.utils.netease_crypto import NeteaseCrypto
                self.crypto = NeteaseCrypto()
                print(f"EAPI解密工具已初始化，目标播放列表: {self.target_playlist_ids}")
            except ImportError as e:
                print(f"Warning: 无法加载EAPI解密工具: {e}")
                print("播放列表提取功能将被禁用")
        
        # 创建输出目录
        self._create_output_dirs()
    
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
    
    def _create_output_dirs(self):
        """创建输出目录"""
        # Cookie输出目录
        if self.cookie_config.get('enabled', False):
            cookie_file = self.cookie_config.get('output_file', '')
            if cookie_file:
                Path(cookie_file).parent.mkdir(parents=True, exist_ok=True)
        
        # 播放列表输出目录
        if self.playlist_config.get('enabled', False):
            playlist_dir = self.playlist_config.get('output_dir', '')
            if playlist_dir:
                Path(playlist_dir).mkdir(parents=True, exist_ok=True)
    
    def handle_request(self, flow):
        """处理HTTP请求 - 新增方法"""
        # 提取请求中的Cookie（网易云主要Cookie在请求头中）
        # 只在有意义的请求中提取Cookie，避免频繁提取相同数据
        if (self.cookie_config.get('enabled', False) and 
            self._should_extract_cookie(flow)):
            self._extract_cookie_from_request(flow)
        
        # 检查是否为EAPI播放列表请求
        if (self.playlist_config.get('enabled', False) and 
            self._is_playlist_eapi_request(flow.request.path)):
            
            self._extract_playlist_from_request(flow)
    
    def handle_response(self, flow):
        """处理HTTP响应 - 新增方法"""
        extracted_data = None
        
        # 提取Cookie
        if self.cookie_config.get('enabled', False):
            cookies = {k: str(v) for k, v in flow.response.cookies.items()}
            headers = {k: v for k, v in flow.response.headers.items()}
            
            cookie_data = self.extract_from_response(cookies, headers, flow.request.pretty_url)
            if cookie_data:
                self._save_cookie_data(cookie_data)
                extracted_data = {'type': 'cookie', 'data': cookie_data}
        
        # 处理播放列表响应
        if (self.playlist_config.get('enabled', False) and 
            flow.metadata.get('target_playlist_id')):
            
            playlist_data = self._extract_playlist_from_response(flow)
            if playlist_data:
                self._save_playlist_data(playlist_data, flow.metadata['target_playlist_id'])
                extracted_data = {'type': 'playlist', 'data': playlist_data}
        
        return extracted_data
    
    def _should_extract_cookie(self, flow) -> bool:
        """判断是否应该从该请求中提取Cookie"""
        # API请求更可能包含完整的认证Cookie
        path = flow.request.path.lower()
        
        # EAPI请求通常包含完整的Cookie
        if '/eapi/' in path:
            return True
        
        # API请求
        if '/api/' in path:
            return True
        
        # 其他重要端点
        important_paths = ['/weapi/', '/login', '/user', '/batch']
        if any(p in path for p in important_paths):
            return True
        
        return False
    
    def _extract_cookie_from_request(self, flow):
        """从请求中提取Cookie"""
        try:
            # 从请求头中获取Cookie
            cookies = {k: str(v) for k, v in flow.request.cookies.items()}
            headers = {k: v for k, v in flow.request.headers.items()}
            
            # 调试信息
            if cookies:
                cookie_keys = list(cookies.keys())
                print(f"检测到请求中的Cookie: {cookie_keys[:3]}... (共{len(cookies)}个)")
                
                # 检查是否包含关键Cookie
                key_cookies_found = [key for key in self.key_cookies if key in cookies]
                if key_cookies_found:
                    print(f"发现关键Cookie: {key_cookies_found}")
            else:
                print("请求中没有Cookie")
                return
            
            cookie_data = self.extract_from_request(cookies, headers, flow.request.pretty_url)
            if cookie_data:
                self._save_cookie_data(cookie_data)
                print(f"✅ 从请求中提取Cookie成功: {len(cookie_data)}个字段")
            else:
                print("Cookie提取失败：不符合提取条件")
                
        except Exception as e:
            print(f"从请求提取Cookie失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _is_playlist_eapi_request(self, path: str) -> bool:
        """检查是否为播放列表EAPI请求"""
        return '/eapi/' in path.lower() and 'playlist' in path.lower()
    
    def _extract_playlist_from_request(self, flow):
        """从请求中提取播放列表ID - 参考debug_ne_addon.py"""
        if not self.crypto or not flow.request.content:
            return
        
        try:
            content = flow.request.content.decode('utf-8')
            if content.startswith('params='):
                encrypted_hex = content[7:]  # 去掉'params='
                result = self.crypto.eapi_decrypt(encrypted_hex)
                
                if result.get('success'):
                    data = result.get('data')
                    if isinstance(data, dict) and 'id' in data:
                        playlist_id = str(data['id'])
                        if playlist_id in [str(pid) for pid in self.target_playlist_ids]:
                            print(f"检测到目标播放列表ID: {playlist_id}")
                            flow.metadata['target_playlist_id'] = playlist_id
                            
        except Exception as e:
            print(f"解密播放列表请求失败: {e}")
    
    def _extract_playlist_from_response(self, flow):
        """从响应中提取播放列表数据 - 参考debug_ne_addon.py"""
        if not self.crypto or not flow.response.content:
            return None
        
        try:
            # 将二进制响应转换为hex字符串
            import binascii
            hex_content = binascii.hexlify(flow.response.content).decode('ascii')
            
            # 解密响应
            decrypt_result = self.crypto.eapi_decrypt(hex_content)
            if decrypt_result.get('success'):
                decrypted_data = decrypt_result.get('data')
                if isinstance(decrypted_data, str):
                    try:
                        playlist_data = json.loads(decrypted_data)
                        if isinstance(playlist_data, dict) and 'playlist' in playlist_data:
                            playlist = playlist_data['playlist']
                            print(f"成功解密播放列表: {playlist.get('name', 'N/A')} ({playlist.get('trackCount', 0)}首歌)")
                            return playlist_data
                    except json.JSONDecodeError:
                        print("播放列表数据JSON解析失败")
            else:
                print(f"播放列表响应解密失败: {decrypt_result.get('error', 'Unknown')}")
                
        except Exception as e:
            print(f"处理播放列表响应失败: {e}")
        
        return None
    
    def _save_cookie_data(self, cookie_data: dict):
        """保存Cookie数据"""
        try:
            output_file = self.cookie_config.get('output_file', '')
            if not output_file:
                return
            
            formatted_data = self.format_cookie_output(cookie_data)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(formatted_data, f, ensure_ascii=False, indent=2)
            
            print(f"Cookie已保存到: {output_file}")
            
        except Exception as e:
            print(f"保存Cookie失败: {e}")
    
    def _save_playlist_data(self, playlist_data: dict, playlist_id: str):
        """保存播放列表数据"""
        try:
            output_dir = Path(self.playlist_config.get('output_dir', ''))
            if not output_dir:
                return
            
            # 生成文件名
            timestamp = int(time.time())
            filename = f"playlist_{playlist_id}_{timestamp}.json"
            output_file = output_dir / filename
            
            # 保存完整数据
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(playlist_data, f, ensure_ascii=False, indent=2)
            
            print(f"播放列表已保存到: {output_file}")
            
            # 同时保存一个latest文件便于访问
            latest_file = output_dir / f"playlist_{playlist_id}_latest.json"
            with open(latest_file, 'w', encoding='utf-8') as f:
                json.dump(playlist_data, f, ensure_ascii=False, indent=2)
            
        except Exception as e:
            print(f"保存播放列表失败: {e}")