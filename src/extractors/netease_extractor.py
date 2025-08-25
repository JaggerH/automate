#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NetEase Extractor - 重构版本

重构要点：
1. 消除代码冗余，提取公共方法
2. 简化状态管理，使用统一的数据结构  
3. 提高错误处理的健壮性
4. 优化算法逻辑，提高可维护性
"""

from typing import Dict, Optional, List, Union
import json
import time
import logging
import uuid
import base64
import binascii
from datetime import datetime
from pathlib import Path
from .base_extractor import BaseExtractor

logger = logging.getLogger(__name__)


class PlaylistState:
    """播放列表状态管理器"""
    
    def __init__(self):
        # 统一状态管理：将分散的字典统一到一个状态类中
        self.pending_data = {}  # 等待合并的数据 {playlist_id: {'type': 'playlist|songs', 'data': ..., 'timestamp': ...}}
        self.track_ids_cache = {}  # trackIds缓存 {playlist_id: [track_ids]}
        
    def store_playlist_data(self, playlist_id: str, playlist_data: dict) -> None:
        """存储播放列表基础数据"""
        self.pending_data[playlist_id] = {
            'type': 'playlist',
            'data': playlist_data,
            'timestamp': time.time()
        }
        
        # 提取并缓存trackIds
        if 'playlist' in playlist_data:
            track_ids = playlist_data['playlist'].get('trackIds', [])
            extracted_ids = self._extract_track_ids(track_ids)
            if extracted_ids:
                self.track_ids_cache[playlist_id] = extracted_ids
    
    def store_songs_data(self, playlist_id: str, songs_data: dict) -> None:
        """存储歌曲数据"""
        self.pending_data[playlist_id] = {
            'type': 'songs',
            'data': songs_data,
            'timestamp': time.time()
        }
    
    def try_merge_data(self, playlist_id: str) -> Optional[dict]:
        """尝试合并播放列表和歌曲数据"""
        if playlist_id not in self.pending_data:
            return None
            
        entry = self.pending_data[playlist_id]
        
        if entry['type'] == 'playlist':
            playlist_data = entry['data']
            # 检查是否已经是完整数据
            tracks = playlist_data.get('playlist', {}).get('tracks', [])
            if tracks:
                # 已经是完整数据，直接返回
                return playlist_data
            
            # 查找对应的songs数据进行合并
            # 这里可以添加更复杂的匹配逻辑
            return None
        
        return None
    
    def find_matching_playlist(self, song_ids: List[int]) -> Optional[str]:
        """根据歌曲ID找到匹配的播放列表"""
        if not song_ids:
            return None
            
        best_match = None
        best_score = 0.0
        
        for playlist_id, track_ids in self.track_ids_cache.items():
            score = self._calculate_match_score(track_ids, song_ids)
            if score > best_score and score > 0.85:  # 85%匹配度阈值
                best_score = score
                best_match = playlist_id
        
        return best_match
    
    def clear_data(self, playlist_id: str) -> None:
        """清理指定播放列表的数据"""
        self.pending_data.pop(playlist_id, None)
        self.track_ids_cache.pop(playlist_id, None)
    
    def cleanup_old_data(self, max_age: int = 600) -> None:
        """清理过期数据（默认10分钟）"""
        current_time = time.time()
        expired_keys = []
        
        for playlist_id, entry in self.pending_data.items():
            if current_time - entry['timestamp'] > max_age:
                expired_keys.append(playlist_id)
        
        for key in expired_keys:
            self.clear_data(key)
            
        if expired_keys:
            logger.info(f"清理了{len(expired_keys)}个过期的播放列表数据")
    
    def _extract_track_ids(self, track_ids: list) -> List[int]:
        """提取trackIds数组中的ID值"""
        extracted_ids = []
        for item in track_ids:
            if isinstance(item, dict) and 'id' in item:
                extracted_ids.append(item['id'])
            elif isinstance(item, (int, str)):
                if isinstance(item, str) and item.isdigit():
                    extracted_ids.append(int(item))
                elif isinstance(item, int):
                    extracted_ids.append(item)
        return extracted_ids
    
    def _calculate_match_score(self, track_ids: List[int], song_ids: List[int]) -> float:
        """计算两个ID列表的匹配度"""
        if not track_ids or not song_ids:
            return 0.0
        
        # 允许10%的长度差异
        length_diff_rate = abs(len(track_ids) - len(song_ids)) / max(len(track_ids), len(song_ids))
        if length_diff_rate > 0.1:
            return 0.0
        
        # 计算顺序匹配度
        min_length = min(len(track_ids), len(song_ids))
        match_count = sum(1 for i in range(min_length) if track_ids[i] == song_ids[i])
        
        return match_count / min_length if min_length > 0 else 0.0


class FileManager:
    """文件操作管理器"""
    
    @staticmethod
    def atomic_write_json(file_path: Path, data: dict) -> bool:
        """原子写入JSON文件"""
        try:
            # 创建临时文件
            temp_suffix = f'.tmp_{uuid.uuid4().hex[:8]}'
            temp_file = file_path.with_suffix(temp_suffix)
            
            # 写入临时文件
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # 原子重命名（Windows需要先删除目标文件）
            if file_path.exists():
                file_path.unlink()
            temp_file.rename(file_path)
            
            return True
            
        except Exception as e:
            logger.error(f"原子写入文件失败 {file_path}: {e}")
            # 清理临时文件
            if 'temp_file' in locals() and temp_file.exists():
                temp_file.unlink(missing_ok=True)
            return False
    
    @staticmethod
    def ensure_directory(file_path: Union[Path, str]) -> bool:
        """确保目录存在"""
        try:
            path = Path(file_path)
            if path.is_file():
                path = path.parent
            path.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"创建目录失败 {file_path}: {e}")
            return False


class NeteaseExtractor(BaseExtractor):
    """网易云音乐提取器 - 重构版"""
    
    # 类常量
    KEY_COOKIES = [
        'MUSIC_U',      # 用户身份标识
        '__csrf',       # CSRF令牌  
        'NMTID',        # 设备ID
        'WEVNSM',       # 会话标识
        '__remember_me' # 记住登录
    ]
    
    COOKIE_PREFIXES = ('MUSIC_', '__', 'NMTID', 'WEVNSM')
    API_PATHS = ('/eapi/', '/api/', '/weapi/', '/login', '/user', '/batch')
    PLAYLIST_PATHS = ('playlist', '/song/detail')
    
    def __init__(self, config: dict):
        super().__init__('netease', config)
        
        # 配置管理
        self.features = config.get('features', {})
        self.cookie_config = self.features.get('extract_cookie', {})
        self.playlist_config = self.features.get('extract_playlist', {})
        
        # 状态管理
        self.playlist_state = PlaylistState()
        self.user_extract_times = {}  # 用户频率控制
        self.cookie_interval = self.cookie_config.get('interval', 300)
        
        # 目标播放列表
        self.target_playlist_ids = [str(pid) for pid in self.playlist_config.get('target_ids', [])]
        
        # 初始化加密工具和输出目录
        self.crypto = self._init_crypto()
        self._setup_output_directories()
    
    def _init_crypto(self) -> Optional[object]:
        """初始化EAPI解密工具"""
        if not self.playlist_config.get('enabled', False):
            return None
            
        try:
            from src.utils.netease_crypto import NeteaseCrypto
            crypto = NeteaseCrypto()
            logger.info(f"EAPI解密工具已初始化，目标播放列表: {self.target_playlist_ids}")
            return crypto
        except ImportError as e:
            logger.warning(f"无法加载EAPI解密工具: {e}")
            return None
    
    def _setup_output_directories(self) -> None:
        """设置输出目录"""
        try:
            # Cookie输出目录
            if self.cookie_config.get('enabled') and self.cookie_config.get('output_file'):
                cookie_path = Path(self.cookie_config['output_file']).parent
                FileManager.ensure_directory(cookie_path)
            
            # 播放列表输出目录
            if self.playlist_config.get('enabled') and self.playlist_config.get('output_dir'):
                playlist_path = Path(self.playlist_config['output_dir'])
                FileManager.ensure_directory(playlist_path)
                
        except Exception as e:
            logger.error(f"设置输出目录失败: {e}")
            raise
    
    # Cookie提取相关方法
    def extract_from_request(self, cookies: dict, headers: dict, url: str) -> Optional[Dict]:
        """从请求中提取Cookie"""
        return self._extract_netease_cookies(cookies, 'request', url)
    
    def extract_from_response(self, cookies: dict, headers: dict, url: str) -> Optional[Dict]:
        """从响应中提取Cookie"""  
        return self._extract_netease_cookies(cookies, 'response', url)
    
    def _extract_netease_cookies(self, cookies: dict, source: str, url: str) -> Optional[Dict]:
        """提取网易云Cookie - 简化版本"""
        if not self._is_valid_cookie_dict(cookies):
            return None
        
        # 过滤关键Cookie
        cleaned_cookies = self._filter_netease_cookies(cookies)
        if not cleaned_cookies:
            return None
        
        logger.info(f"网易云Cookie提取成功: {self.get_cookie_preview(cleaned_cookies)} (来源: {source})")
        return cleaned_cookies
    
    def _is_valid_cookie_dict(self, cookies: dict) -> bool:
        """验证Cookie字典是否有效"""
        return bool(cookies and cookies.get('MUSIC_U'))
    
    def _filter_netease_cookies(self, cookies: dict) -> dict:
        """过滤网易云相关Cookie"""
        cleaned = {}
        
        for key, value in cookies.items():
            if not value:  # 跳过空值
                continue
                
            # 检查是否为网易云相关Cookie
            if (key in self.KEY_COOKIES or 
                any(key.startswith(prefix) for prefix in self.COOKIE_PREFIXES)):
                cleaned[key] = str(value)
        
        return cleaned
    
    def format_cookie_output(self, cookie_data: dict) -> dict:
        """格式化Cookie输出"""
        cookie_string = '; '.join(f'{k}={v}' for k, v in cookie_data.items())
        current_time = int(time.time())
        
        # 解析用户信息
        user_id = self._extract_user_id_from_music_u(cookie_data.get('MUSIC_U', ''))
        account = {'id': user_id} if user_id else {}
        
        return {
            'cookie': cookie_string,
            'timestamp': current_time,
            'profile': {},
            'account': account,
            'user_id': user_id,
            'loginTime': current_time * 1000
        }
    
    def _extract_user_id_from_music_u(self, music_u_value: str) -> Optional[str]:
        """从MUSIC_U中提取用户ID - 增强错误处理"""
        if not music_u_value:
            return None
            
        try:
            # Base64解码，添加padding处理
            padding_needed = 4 - (len(music_u_value) % 4)
            if padding_needed < 4:
                music_u_value += '=' * padding_needed
                
            decoded_bytes = base64.b64decode(music_u_value)
            decoded_str = decoded_bytes.decode('utf-8')
            user_data = json.loads(decoded_str)
            
            user_id = user_data.get('userId')
            return str(user_id) if user_id else None
            
        except Exception as e:
            logger.debug(f"解析MUSIC_U失败: {e}")
            return None
    
    # 请求处理方法
    def handle_request(self, flow) -> None:
        """处理HTTP请求"""
        # Cookie提取
        if (self.cookie_config.get('enabled', False) and 
            self._should_extract_cookie(flow)):
            self._process_cookie_extraction(flow)
        
        # 播放列表请求处理
        if (self.playlist_config.get('enabled', False) and 
            self._is_playlist_request(flow.request.path)):
            self._process_playlist_request(flow)
    
    def handle_response(self, flow) -> Optional[dict]:
        """处理HTTP响应"""
        extracted_data = None
        
        # Cookie提取
        if (self.cookie_config.get('enabled', False) and 
            self._should_extract_cookie(flow)):
            extracted_data = self._process_cookie_response(flow)
        
        # 播放列表响应处理
        if (self.playlist_config.get('enabled', False) and 
            flow.metadata.get('target_playlist_id')):
            playlist_data = self._process_playlist_response(flow)
            if playlist_data:
                extracted_data = {'type': 'playlist', 'data': playlist_data}
        
        # 定期清理过期数据
        self.playlist_state.cleanup_old_data()
        
        return extracted_data
    
    def _should_extract_cookie(self, flow) -> bool:
        """判断是否应该提取Cookie - 简化版本"""
        path = flow.request.path.lower()
        
        # 检查是否为目标API路径
        if not any(api_path in path for api_path in self.API_PATHS):
            return False
        
        # 频率控制
        user_id = self._get_user_id_from_flow(flow)
        user_key = user_id or 'default'
        
        current_time = time.time()
        last_extract_time = self.user_extract_times.get(user_key, 0)
        
        return current_time - last_extract_time >= self.cookie_interval
    
    def _get_user_id_from_flow(self, flow) -> Optional[str]:
        """从flow中获取用户ID"""
        try:
            cookies = {k: str(v) for k, v in flow.request.cookies.items()}
            music_u = cookies.get('MUSIC_U')
            return self._extract_user_id_from_music_u(music_u) if music_u else None
        except Exception:
            return None
    
    def _process_cookie_extraction(self, flow) -> None:
        """处理Cookie提取 - 简化版本"""
        try:
            cookies = {k: str(v) for k, v in flow.request.cookies.items()}
            headers = {k: v for k, v in flow.request.headers.items()}
            
            cookie_data = self.extract_from_request(cookies, headers, flow.request.pretty_url)
            if cookie_data:
                self._save_cookie_data(cookie_data)
                self._update_user_extract_time(cookie_data)
                logger.info(f"Cookie提取成功: {len(cookie_data)}个字段")
                
        except Exception as e:
            logger.error(f"Cookie提取失败: {e}")
    
    def _process_cookie_response(self, flow) -> Optional[dict]:
        """处理Cookie响应"""
        try:
            cookies = {k: str(v) for k, v in flow.response.cookies.items()}
            headers = {k: v for k, v in flow.response.headers.items()}
            
            cookie_data = self.extract_from_response(cookies, headers, flow.request.pretty_url)
            if cookie_data:
                self._save_cookie_data(cookie_data)
                self._update_user_extract_time(cookie_data)
                return {'type': 'cookie', 'data': cookie_data}
        except Exception as e:
            logger.error(f"Cookie响应处理失败: {e}")
        
        return None
    
    # 播放列表处理方法
    def _is_playlist_request(self, path: str) -> bool:
        """检查是否为播放列表请求"""
        path_lower = path.lower()
        return ('/eapi/' in path_lower and 
                any(playlist_path in path_lower for playlist_path in self.PLAYLIST_PATHS))
    
    def _process_playlist_request(self, flow) -> None:
        """处理播放列表请求"""
        if not (self.crypto and flow.request.content):
            return
        
        try:
            content = flow.request.content.decode('utf-8')
            if not content.startswith('params='):
                return
                
            encrypted_hex = content[7:]  # 去掉'params='
            result = self.crypto.eapi_decrypt(encrypted_hex)
            
            if not result.get('success'):
                return
                
            data = result.get('data')
            if not isinstance(data, dict):
                return
            
            # 处理不同类型的请求
            if 'id' in data:
                # 播放列表详情请求
                self._handle_playlist_detail_request(data, flow)
            elif 'c' in data:
                # 歌曲详情请求
                self._handle_song_detail_request(data, flow)
                
        except Exception as e:
            logger.error(f"播放列表请求处理失败: {e}")
    
    def _handle_playlist_detail_request(self, data: dict, flow) -> None:
        """处理播放列表详情请求"""
        playlist_id = str(data['id'])
        if playlist_id in self.target_playlist_ids:
            logger.info(f"检测到目标播放列表ID: {playlist_id}")
            flow.metadata['target_playlist_id'] = playlist_id
    
    def _handle_song_detail_request(self, data: dict, flow) -> None:
        """处理歌曲详情请求"""
        try:
            c_raw = data.get('c')
            if isinstance(c_raw, str):
                c_data = json.loads(c_raw)
            else:
                c_data = c_raw if isinstance(c_raw, list) else []
            
            if not isinstance(c_data, list):
                return
                
            # 提取歌曲ID
            song_ids = []
            for item in c_data:
                if isinstance(item, dict) and 'id' in item:
                    song_id = item['id']
                    if isinstance(song_id, str) and song_id.isdigit():
                        song_ids.append(int(song_id))
                    elif isinstance(song_id, int):
                        song_ids.append(song_id)
            
            if not song_ids:
                return
                
            logger.info(f"检测到歌曲详情请求，包含{len(song_ids)}首歌")
            flow.metadata['is_songs_request'] = True
            flow.metadata['song_ids'] = song_ids
            
            # 尝试匹配播放列表
            matched_playlist_id = self.playlist_state.find_matching_playlist(song_ids)
            if matched_playlist_id:
                flow.metadata['target_playlist_id'] = matched_playlist_id
                logger.info(f"根据ID顺序匹配到播放列表: {matched_playlist_id}")
            else:
                flow.metadata['target_playlist_id'] = 'songs_batch'
                logger.info("未找到匹配的播放列表，标记为songs批量请求")
                
        except Exception as e:
            logger.error(f"处理歌曲详情请求失败: {e}")
    
    def _process_playlist_response(self, flow) -> Optional[dict]:
        """处理播放列表响应 - 简化版本"""
        if not (self.crypto and flow.response.content):
            return None
        
        try:
            # 解密响应内容
            response_data = self._decrypt_eapi_response(flow.response.content)
            if not response_data:
                return None
            
            # 根据响应类型处理
            if self._is_playlist_response(response_data):
                return self._handle_playlist_response(response_data, flow)
            elif self._is_songs_response(response_data):
                return self._handle_songs_response(response_data, flow)
            
            return None
            
        except Exception as e:
            logger.error(f"播放列表响应处理失败: {e}")
            return None
    
    def _decrypt_eapi_response(self, response_content: bytes) -> Optional[dict]:
        """解密EAPI响应内容"""
        try:
            hex_content = binascii.hexlify(response_content).decode('ascii')
            decrypt_result = self.crypto.eapi_decrypt(hex_content)
            
            if not decrypt_result.get('success'):
                logger.error(f"响应解密失败: {decrypt_result.get('error', 'Unknown')}")
                return None
            
            decrypted_data = decrypt_result.get('data')
            if not isinstance(decrypted_data, str):
                return None
                
            return json.loads(decrypted_data)
            
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"解密或解析响应失败: {e}")
            return None
    
    def _is_playlist_response(self, response_data: dict) -> bool:
        """检查是否为播放列表响应"""
        return isinstance(response_data, dict) and 'playlist' in response_data
    
    def _is_songs_response(self, response_data: dict) -> bool:
        """检查是否为歌曲响应"""
        return (isinstance(response_data, dict) and 
                'songs' in response_data and 
                isinstance(response_data.get('songs'), list) and 
                len(response_data.get('songs', [])) > 0)
    
    def _handle_playlist_response(self, response_data: dict, flow) -> dict:
        """处理播放列表响应"""
        playlist = response_data['playlist']
        playlist_id = str(playlist.get('id', ''))
        tracks = playlist.get('tracks', [])
        
        logger.info(f"[PLAYLIST] 检测到播放列表响应: {playlist.get('name', 'N/A')} (ID: {playlist_id})")
        
        if tracks:
            # 完整数据，直接保存
            logger.info(f"[V6] 完整模式: 播放列表包含{len(tracks)}首歌曲，直接保存")
            self._save_playlist_file(response_data, playlist_id)
            return response_data
        else:
            # 部分数据，等待歌曲数据
            logger.info(f"[V4] 分步模式: 播放列表tracks为空，保存基础数据等待歌曲数据")
            self.playlist_state.store_playlist_data(playlist_id, response_data)
            return response_data
    
    def _handle_songs_response(self, response_data: dict, flow) -> dict:
        """处理歌曲响应"""
        songs = response_data.get('songs', [])
        song_ids = flow.metadata.get('song_ids', [])
        
        logger.info(f"[SONGS] 检测到歌曲响应: {len(songs)}首歌曲")
        
        # 尝试找到匹配的播放列表
        matched_playlist_id = self.playlist_state.find_matching_playlist(song_ids)
        
        if matched_playlist_id:
            logger.info(f"[MATCH] 匹配到播放列表: {matched_playlist_id}")
            return self._merge_and_save_playlist(matched_playlist_id, songs, response_data)
        else:
            logger.warning("[WARN] 未找到匹配的播放列表，songs数据暂存")
            return {'type': 'unmatched_songs', 'songs': songs}
    
    def _merge_and_save_playlist(self, playlist_id: str, songs: list, response_data: dict) -> dict:
        """合并并保存播放列表数据"""
        # 获取基础播放列表数据
        playlist_entry = self.playlist_state.pending_data.get(playlist_id)
        if not playlist_entry or playlist_entry['type'] != 'playlist':
            logger.warning(f"找不到播放列表{playlist_id}的基础数据")
            return {'type': 'orphan_songs', 'songs': songs}
        
        # 合并数据
        playlist_data = playlist_entry['data'].copy()
        if 'playlist' in playlist_data:
            playlist_data['playlist']['tracks'] = songs
            playlist_data['playlist']['trackCount'] = len(songs)
        
        logger.info(f"[MERGE] 合并成功: 播放列表{playlist_id}包含{len(songs)}首歌曲")
        
        # 保存完整数据
        self._save_playlist_file(playlist_data, playlist_id)
        
        # 清理状态
        self.playlist_state.clear_data(playlist_id)
        
        return playlist_data
    
    # 文件保存方法
    def _save_cookie_data(self, cookie_data: dict) -> None:
        """保存Cookie数据"""
        output_file = self.cookie_config.get('output_file')
        if not output_file:
            return
        
        try:
            formatted_data = self.format_cookie_output(cookie_data)
            user_id = formatted_data.get('user_id')
            
            # 确定保存路径
            if user_id:
                # 多用户模式
                output_path = Path(output_file)
                final_path = output_path.parent / f"cookie_{user_id}.json"
                logger.info(f"检测到用户ID {user_id}，使用多用户模式保存")
            else:
                # 单用户模式
                final_path = Path(output_file)
                logger.debug("未检测到用户ID，使用默认Cookie文件")
            
            # 原子写入
            if FileManager.atomic_write_json(final_path, formatted_data):
                logger.info(f"Cookie已保存到: {final_path}")
            else:
                logger.error(f"Cookie保存失败: {final_path}")
                
        except Exception as e:
            logger.error(f"保存Cookie数据失败: {e}")
    
    def _save_playlist_file(self, playlist_data: dict, playlist_id: str) -> None:
        """保存播放列表文件"""
        output_dir = self.playlist_config.get('output_dir')
        if not output_dir:
            return
        
        try:
            output_file = Path(output_dir) / f"playlist_{playlist_id}.json"
            
            if FileManager.atomic_write_json(output_file, playlist_data):
                logger.info(f"播放列表已保存到: {output_file}")
            else:
                logger.error(f"播放列表保存失败: {output_file}")
                
        except Exception as e:
            logger.error(f"保存播放列表文件失败: {e}")
    
    def _update_user_extract_time(self, cookie_data: dict) -> None:
        """更新用户提取时间"""
        user_id = None
        if 'MUSIC_U' in cookie_data:
            user_id = self._extract_user_id_from_music_u(cookie_data['MUSIC_U'])
        
        user_key = user_id or 'default'
        self.user_extract_times[user_key] = time.time()
        logger.debug(f"用户 {user_key} 的Cookie提取时间已更新")
    
    # 兼容性方法 - 保持向后兼容
    def is_valid_cookie(self, cookies: dict) -> bool:
        """验证Cookie是否有效 - 兼容性方法"""
        return self._is_valid_cookie_dict(cookies)
    
    def _extract_playlist_from_response(self, flow):
        """提取播放列表响应 - 兼容性方法"""
        return self._process_playlist_response(flow)
    
    # 清理方法
    def cleanup(self) -> None:
        """清理资源"""
        try:
            self.crypto = None
            self.user_extract_times.clear()
            self.playlist_state.pending_data.clear()
            self.playlist_state.track_ids_cache.clear()
            logger.debug(f"{self.service_name} 提取器资源已清理")
        except Exception as e:
            logger.error(f"清理资源失败: {e}")
    
    def __del__(self):
        """析构函数"""
        try:
            self.cleanup()
        except:
            pass