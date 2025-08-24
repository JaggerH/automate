from typing import Dict, Optional
import json
import time
import os
import logging
from pathlib import Path
from .base_extractor import BaseExtractor

# 设置日志
logger = logging.getLogger(__name__)

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
        
        # 频率控制 - 支持多用户
        self.last_cookie_extract_by_user = {}  # 每个用户独立的提取时间
        self.cookie_interval = self.cookie_config.get('interval', 300)  # 默认5分钟
        
        # 延迟导入NeteaseCrypto
        if self.playlist_config.get('enabled', False):
            try:
                from src.utils.netease_crypto import NeteaseCrypto
                self.crypto = NeteaseCrypto()
                logger.info(f"EAPI解密工具已初始化，目标播放列表: {self.target_playlist_ids}")
            except ImportError as e:
                logger.warning(f"无法加载EAPI解密工具: {e}")
                logger.warning("播放列表提取功能将被禁用")
        
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
        
        # 尝试从MUSIC_U中解析用户信息
        profile = {}
        account = {}
        user_id = None
        
        if 'MUSIC_U' in cookie_data:
            user_id = self._extract_user_id_from_music_u(cookie_data['MUSIC_U'])
            if user_id:
                account['id'] = user_id
                logger.debug(f"从MUSIC_U解析出用户ID: {user_id}")
        
        return {
            'cookie': cookie_string,
            'timestamp': int(self._get_current_timestamp()),
            'profile': profile,
            'account': account,
            'user_id': user_id,  # 添加用户ID字段
            'loginTime': int(self._get_current_timestamp() * 1000)  # 毫秒时间戳
        }
    
    def _extract_user_id_from_music_u(self, music_u_value: str) -> Optional[str]:
        """从MUSIC_U Cookie中提取用户ID"""
        try:
            import base64
            import json
            
            # MUSIC_U是Base64编码的JSON数据
            # 格式通常是: {"userId":123456789,"exp":1234567890}
            decoded_bytes = base64.b64decode(music_u_value + '==')  # 添加padding
            decoded_str = decoded_bytes.decode('utf-8')
            user_data = json.loads(decoded_str)
            
            user_id = user_data.get('userId')
            if user_id:
                return str(user_id)
                
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.debug(f"解析MUSIC_U失败: {e}")
        except Exception as e:
            logger.warning(f"解析MUSIC_U时发生未知错误: {e}")
        
        return None
    
    def _get_current_timestamp(self) -> float:
        """获取当前时间戳"""
        import time
        return time.time()
    
    def _create_output_dirs(self):
        """创建输出目录"""
        try:
            # Cookie输出目录
            if self.cookie_config.get('enabled', False):
                cookie_file = self.cookie_config.get('output_file', '')
                if cookie_file:
                    cookie_path = Path(cookie_file).parent
                    cookie_path.mkdir(parents=True, exist_ok=True)
                    logger.debug(f"Cookie输出目录已创建: {cookie_path}")
            
            # 播放列表输出目录  
            if self.playlist_config.get('enabled', False):
                playlist_dir = self.playlist_config.get('output_dir', '')
                if playlist_dir:
                    playlist_path = Path(playlist_dir)
                    playlist_path.mkdir(parents=True, exist_ok=True)
                    logger.debug(f"播放列表输出目录已创建: {playlist_path}")
                    
        except (OSError, PermissionError) as e:
            logger.error(f"创建输出目录失败: {e}")
            raise
    
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
        
        # 提取Cookie - 添加频率控制
        if (self.cookie_config.get('enabled', False) and 
            self._should_extract_cookie(flow)):
            cookies = {k: str(v) for k, v in flow.response.cookies.items()}
            headers = {k: v for k, v in flow.response.headers.items()}
            
            cookie_data = self.extract_from_response(cookies, headers, flow.request.pretty_url)
            if cookie_data:
                self._save_cookie_data(cookie_data)
                # 更新最后提取时间 - 支持多用户
                self._update_extract_time(cookie_data)
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
        # 先检查是否是重要的API请求
        path = flow.request.path.lower()
        
        # EAPI请求通常包含完整的Cookie
        if '/eapi/' in path:
            pass
        # API请求
        elif '/api/' in path:
            pass
        # 其他重要端点
        elif any(p in path for p in ['/weapi/', '/login', '/user', '/batch']):
            pass
        else:
            return False
        
        # 尝试获取用户ID进行频率控制
        cookies = {k: str(v) for k, v in flow.request.cookies.items()}
        user_id = None
        
        if 'MUSIC_U' in cookies:
            user_id = self._extract_user_id_from_music_u(cookies['MUSIC_U'])
        
        # 使用用户ID或默认键进行频率控制
        user_key = user_id if user_id else 'default'
        current_time = time.time()
        last_extract_time = self.last_cookie_extract_by_user.get(user_key, 0)
        
        if current_time - last_extract_time < self.cookie_interval:
            logger.debug(f"用户 {user_key} 的Cookie提取间隔未到，跳过")
            return False
        
        return True
    
    def _extract_cookie_from_request(self, flow):
        """从请求中提取Cookie"""
        try:
            # 从请求头中获取Cookie
            cookies = {k: str(v) for k, v in flow.request.cookies.items()}
            headers = {k: v for k, v in flow.request.headers.items()}
            
            if not cookies:
                logger.debug("请求中没有Cookie")
                return
            
            # 调试信息 - 只在DEBUG级别显示
            logger.debug(f"检测到请求中的Cookie: {list(cookies.keys())[:3]}... (共{len(cookies)}个)")
            
            # 检查是否包含关键Cookie
            key_cookies_found = [key for key in self.key_cookies if key in cookies]
            if key_cookies_found:
                logger.debug(f"发现关键Cookie: {key_cookies_found}")
            
            cookie_data = self.extract_from_request(cookies, headers, flow.request.pretty_url)
            if cookie_data:
                self._save_cookie_data(cookie_data)
                # 更新最后提取时间 - 支持多用户
                self._update_extract_time(cookie_data)
                logger.info(f"Cookie提取成功: {len(cookie_data)}个字段")
            else:
                logger.debug("Cookie提取失败：不符合提取条件")
                
        except (UnicodeDecodeError, KeyError, ValueError) as e:
            logger.error(f"Cookie提取失败: {e}")
        except Exception as e:
            logger.exception("未预期的Cookie提取错误")
            # 对于未知错误，重新抛出以便调试
            raise
    
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
                            logger.info(f"检测到目标播放列表ID: {playlist_id}")
                            flow.metadata['target_playlist_id'] = playlist_id
                            
        except (UnicodeDecodeError, KeyError) as e:
            logger.error(f"解密播放列表请求失败: {e}")
        except Exception as e:
            logger.exception("播放列表请求处理失败")
            raise
    
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
                            logger.info(f"成功解密播放列表: {playlist.get('name', 'N/A')} ({playlist.get('trackCount', 0)}首歌)")
                            return playlist_data
                    except json.JSONDecodeError as e:
                        logger.error(f"播放列表数据JSON解析失败: {e}")
            else:
                logger.error(f"播放列表响应解密失败: {decrypt_result.get('error', 'Unknown')}")
                
        except Exception as e:
            logger.exception("处理播放列表响应失败")
            raise
        
        return None
    
    def _update_extract_time(self, cookie_data: dict):
        """更新指定用户的最后提取时间"""
        user_id = None
        
        # 从cookie_data中获取用户ID
        if 'MUSIC_U' in cookie_data:
            user_id = self._extract_user_id_from_music_u(cookie_data['MUSIC_U'])
        
        user_key = user_id if user_id else 'default'
        self.last_cookie_extract_by_user[user_key] = time.time()
        
        logger.debug(f"用户 {user_key} 的Cookie提取时间已更新")
    
    def _save_cookie_data(self, cookie_data: dict):
        """保存Cookie数据 - 支持多用户，使用原子写入"""
        try:
            output_file = self.cookie_config.get('output_file', '')
            if not output_file:
                return
            
            formatted_data = self.format_cookie_output(cookie_data)
            user_id = formatted_data.get('user_id')
            
            # 如果有用户ID，按用户保存；否则使用默认文件名
            if user_id:
                # 多用户模式：data/outputs/netease/cookie_123456789.json
                output_path = Path(output_file)
                user_cookie_file = output_path.parent / f"cookie_{user_id}.json"
                final_path = user_cookie_file
                logger.info(f"检测到用户ID {user_id}，使用多用户模式保存")
            else:
                # 单用户模式：使用配置的默认路径
                final_path = Path(output_file)
                logger.debug("未检测到用户ID，使用默认Cookie文件")
            
            # 原子写入：先写临时文件再重命名
            temp_file = final_path.with_suffix('.tmp')
            
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(formatted_data, f, ensure_ascii=False, indent=2)
            
            # 原子操作：重命名临时文件
            temp_file.rename(final_path)
            
            logger.info(f"Cookie已保存到: {final_path}")
            
        except (IOError, OSError) as e:
            logger.error(f"保存Cookie文件失败: {e}")
            # 清理临时文件
            if 'temp_file' in locals():
                temp_file.unlink(missing_ok=True)
        except Exception as e:
            logger.exception("Cookie保存过程中发生未知错误")
            raise
    
    def _save_playlist_data(self, playlist_data: dict, playlist_id: str):
        """保存播放列表数据 - 使用原子写入"""
        try:
            output_dir = Path(self.playlist_config.get('output_dir', ''))
            if not output_dir:
                return
            
            # 只保存一个文件，不带时间戳
            output_file = output_dir / f"playlist_{playlist_id}.json"
            
            # 原子写入：保存完整数据
            temp_file = output_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(playlist_data, f, ensure_ascii=False, indent=2)
            temp_file.rename(output_file)
            
            logger.info(f"播放列表已保存到: {output_file}")
            
        except (IOError, OSError) as e:
            logger.error(f"保存播放列表文件失败: {e}")
            # 清理临时文件
            self._cleanup_temp_files(output_dir, playlist_id)
        except Exception as e:
            logger.exception("播放列表保存过程中发生未知错误")
    
    def _cleanup_temp_files(self, output_dir: Path, playlist_id: str):
        """清理临时文件"""
        try:
            # 清理可能存在的临时文件
            temp_file = output_dir / f"playlist_{playlist_id}.tmp"
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)
        except Exception as e:
            logger.debug(f"清理临时文件时出错: {e}")
    
    def cleanup(self):
        """清理资源，防止内存泄漏"""
        try:
            # 重置crypto对象，释放加密资源
            if hasattr(self, 'crypto') and self.crypto:
                self.crypto = None
            
            # 清理缓存的时间戳
            self.last_cookie_extract_by_user.clear()
            
            logger.debug(f"{self.service_name} 提取器资源已清理")
            
        except Exception as e:
            logger.error(f"清理 {self.service_name} 提取器资源时出错: {e}")
    
    def __del__(self):
        """析构函数，确保资源被清理"""
        try:
            self.cleanup()
        except:
            pass  # 析构函数中不应抛出异常