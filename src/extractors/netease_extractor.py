from typing import Dict, Optional
import json
import time
import os
import logging
from datetime import datetime
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
        
        # songs数据临时存储（用于合并playlist和songs数据）
        self.temp_songs_storage = {}
        self._last_playlist_id = None  # 记录最近处理的playlist ID
        
        # 存储playlist的trackIds用于顺序匹配
        self.playlist_track_ids = {}  # {playlist_id: [track_id1, track_id2, ...]}
        
        # 分步模式状态管理
        self.pending_playlists = {}  # {playlist_id: playlist_response_data}
        
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
        
        logger.info(f"网易云Cookie提取成功: {self.get_cookie_preview(cleaned_cookies)} (来源: {source})")
        
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
        """检查是否为播放列表相关的EAPI请求"""
        path_lower = path.lower()
        return '/eapi/' in path_lower and (
            'playlist' in path_lower or 
            '/song/detail' in path_lower  # 歌曲详情API包含tracks数据
        )
    
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
                    if isinstance(data, dict):
                        # 播放列表详情请求
                        if 'id' in data:
                            playlist_id = str(data['id'])
                            if playlist_id in [str(pid) for pid in self.target_playlist_ids]:
                                logger.info(f"检测到目标播放列表ID: {playlist_id}")
                                flow.metadata['target_playlist_id'] = playlist_id
                                # 记录最近的playlist_id用于关联songs请求
                                self._last_playlist_id = playlist_id
                        
                        # 歌曲详情请求 - 从c字段中的id数组推断playlist
                        elif 'c' in data:
                            # 新的歌曲详情请求格式：c是JSON字符串 "[{\"id\": xxx}, {\"id\": yyy}, ...]"
                            c_raw = data.get('c')
                            try:
                                # c字段是JSON字符串，需要先解析
                                if isinstance(c_raw, str):
                                    c_data = json.loads(c_raw)
                                else:
                                    c_data = c_raw if isinstance(c_raw, list) else []
                                
                                if isinstance(c_data, list) and len(c_data) > 0:
                                    # 提取id数组
                                    song_ids = []
                                    for item in c_data:
                                        if isinstance(item, dict) and 'id' in item:
                                            song_id = item['id']
                                            # ID可能是字符串，需要转换
                                            if isinstance(song_id, str) and song_id.isdigit():
                                                song_ids.append(int(song_id))
                                            elif isinstance(song_id, int):
                                                song_ids.append(song_id)
                                
                                    if song_ids:
                                        logger.info(f"检测到歌曲详情请求，包含{len(song_ids)}首歌")
                                        flow.metadata['is_songs_request'] = True
                                        flow.metadata['song_ids'] = song_ids
                                        
                                        # 尝试匹配已保存的trackIds找到对应的playlist
                                        matched_playlist_id = self._match_playlist_by_track_ids(song_ids)
                                        if matched_playlist_id:
                                            flow.metadata['target_playlist_id'] = matched_playlist_id
                                            logger.info(f"根据ID顺序匹配到播放列表: {matched_playlist_id}")
                                        else:
                                            # 没有匹配的playlist，使用通用标记
                                            flow.metadata['target_playlist_id'] = 'songs_batch'
                                            logger.info(f"未找到匹配的播放列表，标记为songs批量请求")
                                            
                            except json.JSONDecodeError as e:
                                logger.error(f"解析c字段JSON失败: {e}")
                            except Exception as e:
                                logger.error(f"处理c字段时出错: {e}")
                        
                        # 兼容旧格式的ids字段
                        elif 'ids' in data:
                            ids = data.get('ids', [])
                            if isinstance(ids, list) and len(ids) > 0:
                                logger.info(f"检测到旧格式歌曲详情请求，包含{len(ids)}首歌")
                                flow.metadata['is_songs_request'] = True
                                flow.metadata['song_ids'] = ids
                                flow.metadata['target_playlist_id'] = 'songs_batch'
                            
        except (UnicodeDecodeError, KeyError) as e:
            logger.error(f"解密播放列表请求失败: {e}")
        except Exception as e:
            logger.exception("播放列表请求处理失败")
            raise
    
    def _extract_playlist_from_response(self, flow):
        """从响应中提取播放列表数据 - 支持v4/v6两种模式"""
        if not self._validate_response_conditions(flow):
            return None
        
        try:
            response_data = self._decrypt_response_content(flow.response.content)
            if not response_data:
                return None
            
            # 分两种模式处理
            if self._is_playlist_response(response_data):
                return self._handle_playlist_response(response_data, flow)
            elif self._is_songs_response(response_data):
                return self._handle_songs_response(response_data, flow)
            
            return None
            
        except Exception as e:
            logger.exception("处理播放列表响应失败")
            raise
    
    def _validate_response_conditions(self, flow) -> bool:
        """验证响应处理的前置条件"""
        return bool(self.crypto and flow.response.content)
    
    def _decrypt_response_content(self, response_content) -> Optional[dict]:
        """解密响应内容并解析JSON"""
        try:
            import binascii
            hex_content = binascii.hexlify(response_content).decode('ascii')
            
            decrypt_result = self.crypto.eapi_decrypt(hex_content)
            if not decrypt_result.get('success'):
                logger.error(f"响应解密失败: {decrypt_result.get('error', 'Unknown')}")
                return None
            
            decrypted_data = decrypt_result.get('data')
            if not isinstance(decrypted_data, str):
                logger.error("解密数据格式错误：不是字符串")
                return None
            
            return json.loads(decrypted_data)
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            return None
    
    def _is_playlist_response(self, response_data: dict) -> bool:
        """检查是否为播放列表响应"""
        return isinstance(response_data, dict) and 'playlist' in response_data
    
    def _is_songs_response(self, response_data: dict) -> bool:
        """检查是否为歌曲详情响应"""
        return (isinstance(response_data, dict) and 
                'songs' in response_data and 
                isinstance(response_data.get('songs'), list) and 
                len(response_data.get('songs', [])) > 0)
    
    def _handle_playlist_response(self, response_data: dict, flow) -> dict:
        """处理播放列表响应 - 自动判断v4/v6模式"""
        playlist = response_data['playlist']
        playlist_id = str(playlist.get('id', ''))
        tracks = playlist.get('tracks', [])
        track_ids = playlist.get('trackIds', [])
        
        print(f"[PLAYLIST] 检测到播放列表响应: {playlist.get('name', 'N/A')} (ID: {playlist_id})")
        
        if self._is_complete_playlist(tracks):
            # 模式1: v6完整模式 - 直接保存
            return self._handle_complete_playlist(response_data, playlist_id)
        else:
            # 模式2: v4分步模式 - 保存trackIds等待songs
            return self._handle_partial_playlist(response_data, playlist_id, track_ids)
    
    def _handle_songs_response(self, response_data: dict, flow) -> dict:
        """处理歌曲响应 - 尝试匹配并合并到playlist"""
        songs = response_data.get('songs', [])
        song_ids = flow.metadata.get('song_ids', [])
        
        print(f"[SONGS] 检测到歌曲响应: {len(songs)}首歌曲")
        
        # 尝试找到匹配的playlist
        matched_playlist_id = self._match_playlist_by_track_ids(song_ids)
        
        if matched_playlist_id:
            print(f"[MATCH] 匹配到播放列表: {matched_playlist_id}")
            return self._merge_songs_into_existing_playlist(matched_playlist_id, songs, response_data)
        else:
            print(f"[WARN] 未找到匹配的播放列表，songs数据暂存")
            return self._store_unmatched_songs(songs, response_data)
    
    def _save_playlist_track_ids(self, playlist_id: str, track_ids: list):
        """保存播放列表的trackIds用于后续匹配"""
        extracted_ids = self._extract_track_ids(track_ids)
        
        if extracted_ids:
            self.playlist_track_ids[playlist_id] = extracted_ids
            logger.info(f"  保存播放列表 {playlist_id} 的trackIds: {len(extracted_ids)}个ID")
            logger.debug(f"  trackIds前3个: {extracted_ids[:3]}")
    
    def _extract_track_ids(self, track_ids: list) -> list:
        """从trackIds数组中提取实际的ID值"""
        extracted_ids = []
        
        for track_id_item in track_ids:
            if isinstance(track_id_item, dict) and 'id' in track_id_item:
                extracted_ids.append(track_id_item['id'])
            elif isinstance(track_id_item, (int, str)):
                extracted_ids.append(int(track_id_item) if str(track_id_item).isdigit() else track_id_item)
        
        return extracted_ids
    
    # 模式1: 完整播放列表处理
    def _is_complete_playlist(self, tracks: list) -> bool:
        """判断是否为完整的播放列表(v6模式)"""
        return isinstance(tracks, list) and len(tracks) > 0
    
    def _handle_complete_playlist(self, response_data: dict, playlist_id: str) -> dict:
        """处理完整播放列表 - v6模式"""
        playlist = response_data['playlist']
        track_count = len(playlist.get('tracks', []))
        
        print(f"[V6] 完整模式: 播放列表包含{track_count}首完整歌曲，直接保存")
        
        # 直接保存完整数据
        self._save_complete_playlist(response_data, playlist_id)
        return response_data
    
    # 模式2: 分步播放列表处理  
    def _handle_partial_playlist(self, response_data: dict, playlist_id: str, track_ids: list) -> dict:
        """处理部分播放列表 - v4模式"""
        extracted_ids = self._extract_track_ids(track_ids)
        
        if extracted_ids:
            self.playlist_track_ids[playlist_id] = extracted_ids
            self.pending_playlists[playlist_id] = response_data
            print(f"[V4] 分步模式: 播放列表tracks为空，保存{len(extracted_ids)}个trackIds等待歌曲数据")
            print(f"     等待匹配歌曲请求...")
        
        # 暂时不保存，等待songs数据合并
        return response_data
    
    def _merge_songs_into_existing_playlist(self, playlist_id: str, songs: list, response_data: dict) -> dict:
        """将songs数据合并到已有的playlist中"""
        # 检查是否有对应的playlist数据等待合并
        if playlist_id in self.pending_playlists:
            playlist_data = self.pending_playlists[playlist_id]
            
            # 执行合并
            merged_data = self._perform_playlist_songs_merge(playlist_data, songs)
            
            print(f"[MERGE] 合并成功: 播放列表{playlist_id}现在包含{len(songs)}首完整歌曲")
            
            # 保存合并后的完整数据
            self._save_complete_playlist(merged_data, playlist_id)
            
            # 清理临时数据
            del self.pending_playlists[playlist_id]
            if playlist_id in self.playlist_track_ids:
                del self.playlist_track_ids[playlist_id]
                
            return merged_data
        else:
            print(f"[WARN] 找到匹配但无等待的playlist数据，songs数据暂存")
            return self._store_matched_songs(playlist_id, songs, response_data)
    
    def _store_unmatched_songs(self, songs: list, response_data: dict) -> dict:
        """存储未匹配的songs数据"""
        return {
            'type': 'songs_data', 
            'songs': songs, 
            'privileges': response_data.get('privileges', [])
        }
    
    def _store_matched_songs(self, playlist_id: str, songs: list, response_data: dict) -> dict:
        """存储已匹配但无等待playlist的songs数据"""
        # 可以存储到temp_songs_storage等待后续处理
        self.temp_songs_storage[playlist_id] = {
            'songs': songs,
            'privileges': response_data.get('privileges', []),
            'timestamp': time.time()
        }
        return {
            'type': 'matched_songs_data',
            'playlist_id': playlist_id,
            'songs': songs, 
            'privileges': response_data.get('privileges', [])
        }
    
    # 数据合并核心逻辑
    def _perform_playlist_songs_merge(self, playlist_data: dict, songs: list) -> dict:
        """执行playlist和songs的数据合并"""
        merged_data = playlist_data.copy()
        
        if 'playlist' in merged_data:
            merged_data['playlist']['tracks'] = songs
            merged_data['playlist']['trackCount'] = len(songs)
            
        return merged_data
    
    def _save_complete_playlist(self, playlist_data: dict, playlist_id: str):
        """保存完整的播放列表数据"""
        try:
            output_dir = Path(self.playlist_config.get('output_dir', ''))
            if not output_dir:
                return
            
            output_file = output_dir / f"playlist_{playlist_id}.json"
            
            # 原子写入
            import uuid
            temp_suffix = f'.tmp_{uuid.uuid4().hex[:8]}'
            temp_file = output_file.with_suffix(temp_suffix)
            
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(playlist_data, f, ensure_ascii=False, indent=2)
            
            # Windows原子重命名
            if output_file.exists():
                output_file.unlink()
            temp_file.rename(output_file)
            
            logger.info(f"播放列表已保存到: {output_file}")
            
        except Exception as e:
            logger.error(f"保存播放列表文件失败: {e}")
    
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
            import uuid
            temp_suffix = f'.tmp_{uuid.uuid4().hex[:8]}'
            temp_file = final_path.with_suffix(temp_suffix)
            
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(formatted_data, f, ensure_ascii=False, indent=2)
            
            # 原子操作：重命名临时文件（Windows需要先删除目标文件）
            if final_path.exists():
                final_path.unlink()
            temp_file.rename(final_path)
            
            logger.info(f"Cookie已保存到: {final_path}")
            
        except (IOError, OSError) as e:
            logger.error(f"保存Cookie文件失败: {e}")
            # 清理临时文件
            if 'temp_file' in locals() and temp_file.exists():
                temp_file.unlink(missing_ok=True)
        except Exception as e:
            logger.exception("Cookie保存过程中发生未知错误")
            raise
    
    def _save_playlist_data(self, playlist_data: dict, playlist_id: str):
        """保存播放列表数据 - 使用原子写入，tracks为空时放弃保存"""
        try:
            output_dir = Path(self.playlist_config.get('output_dir', ''))
            if not output_dir:
                return
            
            # 检查数据类型并验证
            if playlist_data.get('type') == 'songs_data':
                # 这是songs数据，暂存等待合并
                songs_count = len(playlist_data.get('songs', []))
                logger.info(f"获取到{songs_count}首歌曲数据，等待播放列表基本信息")
                self._store_songs_data(playlist_id, playlist_data)
                return
            
            # 这是播放列表基本数据，检查tracks
            if 'playlist' in playlist_data:
                playlist = playlist_data['playlist']
                tracks = playlist.get('tracks', [])
                
                # 如果tracks为空，尝试合并已存储的songs数据
                if not tracks or len(tracks) == 0:
                    logger.warning(f"播放列表 {playlist_id} 的tracks为空，尝试合并songs数据")
                    merged_data = self._merge_songs_into_playlist(playlist_data, playlist_id)
                    if not merged_data:
                        logger.warning(f"播放列表 {playlist_id} 无法获取完整tracks数据，放弃保存")
                        return
                    playlist_data = merged_data
                    tracks = playlist_data['playlist'].get('tracks', [])
                
                # 最终验证：如果tracks仍然为空，放弃保存
                if not tracks or len(tracks) == 0:
                    logger.warning(f"播放列表 {playlist_id} tracks为空，放弃保存")
                    return
                
                logger.info(f"播放列表 {playlist.get('name', 'N/A')} 包含 {len(tracks)} 首歌，准备保存")
            
            # 只保存一个文件，不带时间戳
            output_file = output_dir / f"playlist_{playlist_id}.json"
            
            # 原子写入：保存完整数据
            import uuid
            temp_suffix = f'.tmp_{uuid.uuid4().hex[:8]}'
            temp_file = output_file.with_suffix(temp_suffix)
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(playlist_data, f, ensure_ascii=False, indent=2)
            
            # Windows原子重命名
            if output_file.exists():
                output_file.unlink()
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
            # 清理可能存在的临时文件（包括UUID后缀的）
            for temp_file in output_dir.glob(f"playlist_{playlist_id}.tmp*"):
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
            
            # 清理临时songs存储
            if hasattr(self, 'temp_songs_storage'):
                self.temp_songs_storage.clear()
            
            # 清理trackIds存储
            if hasattr(self, 'playlist_track_ids'):
                self.playlist_track_ids.clear()
            
            # 清理分步模式状态
            if hasattr(self, 'pending_playlists'):
                self.pending_playlists.clear()
            
            logger.debug(f"{self.service_name} 提取器资源已清理")
            
        except Exception as e:
            logger.error(f"清理 {self.service_name} 提取器资源时出错: {e}")
    
    def _store_songs_data(self, playlist_id: str, songs_data: dict):
        """临时存储songs数据"""
        songs = songs_data.get('songs', [])
        privileges = songs_data.get('privileges', [])
        
        # 如果是批量songs请求，为所有目标playlist都存储
        if playlist_id == 'songs_batch':
            for target_id in self.target_playlist_ids:
                target_id_str = str(target_id)
                self.temp_songs_storage[target_id_str] = {
                    'songs': songs,
                    'privileges': privileges,
                    'timestamp': time.time(),
                    'match_method': 'batch'
                }
                logger.info(f"已为播放列表 {target_id_str} 暂存 {len(songs)} 首歌曲数据（批量模式）")
        else:
            # 精确匹配的playlist存储
            self.temp_songs_storage[playlist_id] = {
                'songs': songs,
                'privileges': privileges,
                'timestamp': time.time(),
                'match_method': 'track_id_order'
            }
            logger.info(f"已为播放列表 {playlist_id} 暂存 {len(songs)} 首歌曲数据（顺序匹配）")
    
    def _merge_songs_into_playlist(self, playlist_data: dict, playlist_id: str):
        """将songs数据合并到playlist中"""
        if playlist_id not in self.temp_songs_storage:
            logger.warning(f"未找到播放列表 {playlist_id} 的songs数据")
            return None
        
        stored_songs = self.temp_songs_storage[playlist_id]
        songs = stored_songs.get('songs', [])
        
        if not songs:
            logger.warning(f"播放列表 {playlist_id} 的存储songs数据为空")
            return None
        
        # 合并数据
        merged_data = playlist_data.copy()
        if 'playlist' in merged_data:
            merged_data['playlist']['tracks'] = songs
            # 更新统计信息
            merged_data['playlist']['trackCount'] = len(songs)
            
        # 清理临时存储
        del self.temp_songs_storage[playlist_id]
        logger.info(f"成功合并 {len(songs)} 首歌曲到播放列表 {playlist_id}")
        
        return merged_data
    
    def _match_playlist_by_track_ids(self, song_ids: list) -> str:
        """根据歌曲ID顺序匹配播放列表"""
        if not song_ids:
            return None
        
        # 检查每个已保存的playlist的trackIds
        for playlist_id, track_ids in self.playlist_track_ids.items():
            # 放宽长度匹配条件：允许10%的差异（比如某些歌曲下架）
            length_diff_rate = abs(len(track_ids) - len(song_ids)) / max(len(track_ids), len(song_ids), 1)
            
            if length_diff_rate <= 0.1:  # 允许10%的长度差异
                # 长度相近，检查ID顺序匹配度
                match_count = 0
                min_length = min(len(track_ids), len(song_ids))
                
                for i in range(min_length):
                    if i < len(track_ids) and i < len(song_ids):
                        if track_ids[i] == song_ids[i]:
                            match_count += 1
                        else:
                            # ID不匹配，记录位置用于调试
                            logger.debug(f"位置{i}: trackId={track_ids[i]} != songId={song_ids[i]}")
                
                # 计算匹配率（基于较小的数组）
                match_rate = match_count / min_length if min_length > 0 else 0
                print(f"[MATCH] 播放列表 {playlist_id} 长度: {len(track_ids)} vs {len(song_ids)}, 匹配率: {match_rate:.2%} ({match_count}/{min_length})")
                
                # 如果匹配率很高（>85%），认为是同一个播放列表
                if match_rate > 0.85:
                    print(f"[MATCH] 找到高匹配度播放列表: {playlist_id} (匹配率: {match_rate:.2%})")
                    return playlist_id
            else:
                print(f"[MATCH] 播放列表 {playlist_id} 长度差异过大: {len(track_ids)} vs {len(song_ids)} (差异率: {length_diff_rate:.1%})")
        
        return None
    
    def __del__(self):
        """析构函数，确保资源被清理"""
        try:
            self.cleanup()
        except:
            pass  # 析构函数中不应抛出异常