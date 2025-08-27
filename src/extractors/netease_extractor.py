"""
Work Step
1. trigger is response
2. matched domain/path
3. decode payload and response.content
4. if content include tracks and tracks length > 0, save json
5. if content include tracks and tracks length == 0, wait for songs, save json
"""
from typing import Dict, Optional, List, Union
import os
import json
import time
import logging
import uuid
from pathlib import Path
from .base_extractor import BaseExtractor
from src.utils.netease_crypto import NeteaseCrypto
from mitmproxy.http import HTTPFlow
import sqlite3
logger = logging.getLogger(__name__)

class PlaylistState:
    """简单时间窗口播放列表状态管理器"""
    
    def __init__(self, window_seconds: int = 30):
        self.time_window = window_seconds  # 时间窗口（秒）
        self.pending_data = {}  # {timestamp: {'type': 'playlist/songs', 'data': ..., 'timestamp': ...}}
    
    def store_data(self, content):            
        if "playlist" in content:
            logger.info(f"[V4] 分步模式: 播放列表tracks为空，保存基础数据等待歌曲数据")
            self.store_playlist_data(content)
        elif "songs" in content:
            logger.info(f"[V4] 分步模式: 分步获取到歌曲列表")
            self.store_songs_data(content)
        else:
            raise ValueError("PlaylistState.store_data undefined situation")
        
        merged_data = self.try_merge_recent_data()
        if merged_data:
            logger.info("[TIME_WINDOW] 成功合并播放列表和歌曲数据")
            return True, merged_data["playlist"]
        else:
            logger.info("[TIME_WINDOW] 暂存播放列表数据，等待歌曲数据")
            return False, None
            
    def store_playlist_data(self, playlist_data: dict) -> str:
        """存储播放列表数据，返回存储key"""
        timestamp = time.time()
        # 使用更精确的key避免重复
        key = f"playlist_{timestamp}_{len(self.pending_data)}"
        
        self.pending_data[key] = {
            'type': 'playlist',
            'data': playlist_data.copy(),  # 深拷贝避免修改原数据
            'timestamp': timestamp
        }
        
        logger.debug(f"存储播放列表数据，key: {key}")
        return key
    
    def store_songs_data(self, songs_data: dict) -> str:
        """存储歌曲数据，返回存储key"""
        timestamp = time.time()
        # 使用更精确的key避免重复
        key = f"songs_{timestamp}_{len(self.pending_data)}"
        
        self.pending_data[key] = {
            'type': 'songs',
            'data': songs_data.copy(),  # 深拷贝避免修改原数据
            'timestamp': timestamp
        }
        
        logger.debug(f"存储歌曲数据，key: {key}")
        return key
    
    def get_recent_data(self, data_type: str = None) -> List[dict]:
        """获取时间窗口内的数据"""
        now = time.time()
        recent_data = []
        
        for entry in self.pending_data.values():
            if self.is_within_window(entry['timestamp']):
                if data_type is None or entry['type'] == data_type:
                    recent_data.append(entry)
        
        return recent_data
    
    def is_within_window(self, timestamp: float) -> bool:
        """检查时间戳是否在时间窗口内"""
        return time.time() - timestamp <= self.time_window
    
    def cleanup_expired_data(self) -> int:
        """清理时间窗口外的过期数据，返回清理数量"""
        now = time.time()
        expired_keys = []
        
        for key, entry in self.pending_data.items():
            if not self.is_within_window(entry['timestamp']):
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.pending_data[key]
        
        if expired_keys:
            logger.info(f"清理了{len(expired_keys)}个过期数据项")
        
        return len(expired_keys)
    
    def try_merge_recent_data(self) -> Optional[dict]:
        """尝试合并时间窗口内的播放列表和歌曲数据"""
        # 自动清理过期数据
        self.cleanup_expired_data()
        
        # 获取最近的数据
        recent_playlist = self.get_recent_data('playlist')
        recent_songs = self.get_recent_data('songs')
        
        if not recent_playlist or not recent_songs:
            return None
        
        # 取最新的播放列表和歌曲数据
        latest_playlist = max(recent_playlist, key=lambda x: x['timestamp'])
        latest_songs = max(recent_songs, key=lambda x: x['timestamp'])
        
        return self._merge_playlist_and_songs(
            latest_playlist['data'], 
            latest_songs['data']
        )
    
    def _merge_playlist_and_songs(self, playlist_data: dict, songs_data: dict) -> dict:
        """合并播放列表和歌曲数据"""
        import copy
        merged_data = copy.deepcopy(playlist_data)  # 深拷贝避免修改原数据
        
        if 'playlist' in merged_data and 'songs' in songs_data:
            songs = songs_data['songs']
            track_ids = merged_data['playlist'].get('trackIds', [])
            
            # 对比trackIds和songs的长度
            track_ids_count = len(track_ids)
            songs_count = len(songs)
            
            logger.info(f"播放列表trackIds数量: {track_ids_count}, songs数量: {songs_count}")
            
            if track_ids_count != songs_count:
                logger.warning(f"trackIds和songs数量不一致! trackIds: {track_ids_count}, songs: {songs_count}")
                
                # 找出缺失的track id
                existing_song_ids = {song.get('id') for song in songs if song.get('id')}
                missing_track_ids = []
                
                for track_item in track_ids:
                    track_id = track_item.get('id') if isinstance(track_item, dict) else track_item
                    if track_id not in existing_song_ids:
                        missing_track_ids.append(track_id)
                
                if missing_track_ids:
                    logger.info(f"发现 {len(missing_track_ids)} 首缺失的歌曲: {missing_track_ids[:5]}{'...' if len(missing_track_ids) > 5 else ''}")
                    
                    # 尝试从本地数据库补足缺失的歌曲信息
                    missing_songs = self._fetch_missing_songs_from_db(missing_track_ids)
                    if missing_songs:
                        songs.extend(missing_songs)
                        logger.info(f"从本地数据库成功补足 {len(missing_songs)} 首歌曲信息")
                
                # 按trackIds的顺序重新排序songs
                ordered_songs = self._reorder_songs_by_track_ids(track_ids, songs)
                merged_data['playlist']['tracks'] = copy.deepcopy(ordered_songs)
            else:
                merged_data['playlist']['tracks'] = copy.deepcopy(songs)
            
            merged_data['playlist']['trackCount'] = len(merged_data['playlist']['tracks'])
            logger.info(f"成功合并播放列表数据，最终包含{len(merged_data['playlist']['tracks'])}首歌曲")
        
        return merged_data
    
    def _fetch_missing_songs_from_db(self, missing_track_ids: list) -> list:
        """从本地数据库获取缺失的歌曲信息"""
        if not missing_track_ids:
            return []
            
        # 获取NetEase云音乐数据库路径
        local_appdata = os.environ.get('LOCALAPPDATA')
        if not local_appdata:
            logger.warning("无法获取LOCALAPPDATA环境变量，无法访问本地数据库")
            return []
        
        db_path = Path(local_appdata) / "NetEase" / "CloudMusic" / "Library" / "webdb.dat"
        if not db_path.exists():
            logger.warning(f"本地数据库文件不存在: {db_path}")
            return []
        
        conn = None
        try:
            # 转换track_ids为int类型
            missing_songs = []
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            # 构建IN查询的占位符
            placeholders = ','.join('?' * len(missing_track_ids))
            
            # 批量查询dbTrack表
            query = f"SELECT id, jsonStr FROM dbTrack WHERE id IN ({placeholders})"
            cursor.execute(query, missing_track_ids)
            db_track_results = cursor.fetchall()
            
            found_ids = set()
            for row in db_track_results:
                try:
                    track_id, json_str = row
                    if json_str:
                        track_detail = json.loads(json_str)
                        # 转换字段格式以匹配API响应格式
                        self._transform_track_fields(track_detail)
                        missing_songs.append(track_detail)
                        found_ids.add(int(track_id))
                        logger.debug(f"从dbTrack找到歌曲: {track_detail.get('name', 'Unknown')} (ID: {track_id})")
                except json.JSONDecodeError:
                    logger.debug(f"歌曲 {row[0]} JSON解析失败")
                except Exception as e:
                    logger.debug(f"处理歌曲 {row[0]} 时出错: {e}")
            
            # 统计查找结果
            not_found_ids = [tid for tid in missing_track_ids if tid not in found_ids]
            if not_found_ids:
                logger.debug(f"以下歌曲在本地数据库中未找到: {not_found_ids[:10]}{'...' if len(not_found_ids) > 10 else ''}")
            
            logger.info(f"从本地数据库成功找到 {len(missing_songs)}/{len(missing_track_ids)} 首歌曲")
            return missing_songs
            
        except Exception as e:
            logger.error(f"从本地数据库获取歌曲信息时出错: {e}")
            return []
        finally:
            if conn is not None: conn.close()
    
    def _transform_track_fields(self, track_detail: dict) -> None:
        """转换数据库中的字段格式以匹配API响应格式"""
        try:
            if 'id' in track_detail:
                track_detail['id'] = int(track_detail['id'])
            # 转换 album -> al
            if 'album' in track_detail:
                track_detail['al'] = track_detail.pop('album')
                # 确保 al.id 为整数类型
                if isinstance(track_detail['al'], dict) and 'id' in track_detail['al']:
                    track_detail['al']['id'] = int(track_detail['al']['id'])
            
            # 转换 artists -> ar
            if 'artists' in track_detail:
                track_detail['ar'] = track_detail.pop('artists')
                # 确保 ar 中每个元素的 id 为整数类型
                if isinstance(track_detail['ar'], list):
                    for artist in track_detail['ar']:
                        if isinstance(artist, dict) and 'id' in artist:
                            artist['id'] = int(artist['id'])
            
            if 'commentThreadId' in track_detail:
                track_detail.pop('commentThreadId')
            
            if 'privilege' in track_detail:
                track_detail.pop('privilege')
        except Exception as e:
            logger.debug(f"转换歌曲字段时出错: {e}")
    
    def _reorder_songs_by_track_ids(self, track_ids: list, songs: list) -> list:
        """按trackIds的顺序重新排序songs"""
        try:
            # 创建歌曲ID到歌曲对象的映射
            song_dict = {song.get('id'): song for song in songs if song.get('id')}
            
            # 按trackIds顺序构建有序的歌曲列表
            ordered_songs = []
            for track_item in track_ids:
                track_id = track_item.get('id') if isinstance(track_item, dict) else track_item
                
                if track_id in song_dict:
                    ordered_songs.append(song_dict[track_id])
                else:
                    logger.debug(f"歌曲 {track_id} 在songs中未找到，跳过")
            
            logger.info(f"按trackIds顺序重新排序，得到 {len(ordered_songs)} 首歌曲")
            return ordered_songs
            
        except Exception as e:
            logger.error(f"重新排序歌曲时出错: {e}")
            return songs  # 出错时返回原始songs列表
    
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
        self._setup_output_directories()
        
        # 根据配置选择播放列表状态管理策略
        time_window = self.playlist_config.get('time_window_seconds', 30)
        self.playlist_state = PlaylistState(window_seconds=time_window)
        logger.info(f"使用时间窗口合并策略，窗口大小: {time_window}秒")
        
        self.user_extract_times = {}  # 用户频率控制
        self.cookie_interval = self.cookie_config.get('interval', 300)
        
        # 目标播放列表
        self.target_playlist_ids = [str(pid) for pid in self.playlist_config.get('target_ids', [])]
        
        self.decoder = NeteaseCrypto()
    
    def _setup_output_directories(self) -> None:
        """设置输出目录"""
        # Cookie输出目录
        if self.cookie_config.get('enabled'):
            if not self.cookie_config.get('output_dir'):
                raise ValueError("cookie_config dose not have a attribute output_dir")
            cookie_path = Path(self.cookie_config['output_dir'])
            FileManager.ensure_directory(cookie_path)
        
        # 播放列表输出目录
        if self.playlist_config.get('enabled'):
            if not self.playlist_config.get('output_dir'):
                raise ValueError("playlist_config dose not have a attribute output_dir")
            playlist_path = Path(self.playlist_config['output_dir'])
            FileManager.ensure_directory(playlist_path)
    
    def handle_request(self, flow:HTTPFlow):
        pass
    
    def handle_response(self, flow: HTTPFlow) -> Optional[dict]:
        """统一处理HTTP响应 - 合并了原handle_request的逻辑"""
        extracted_data = None
        
        # Cookie提取（优先从响应中提取，更完整）
        if self.cookie_config.get('enabled', False):
            self.extract_cookie(flow)
        
        # 播放列表处理（合并请求解析和响应处理）
        if self.playlist_config.get('enabled', False):
            if self._is_playlist_request(flow):
                self.extract_playlist(flow)
        
        # 定期清理过期数据
        self.playlist_state.cleanup_expired_data()
        
        return extracted_data
    # ============================================
    #            Cookie Extract
    # ============================================
    def extract_cookie(self, flow:HTTPFlow):
        """
        Extract cookie step:
        1. check last_extract_time
        2. if cookie file not exist or expired
        3. save cooie to file
        """
        useid = 'DEFAULT'  # 以后可以获取userid来支持多用户提取
        last_extract_time = self.user_extract_times.get(useid)
        now = time.time()
        if (last_extract_time is None) or (now - last_extract_time > self.cookie_interval):
            if self.is_valid_cookie(flow):
                self.save_cookie(flow)
                self.user_extract_times[useid] = now

        
    def is_valid_cookie(self, flow:HTTPFlow):
        """
        将request.cookies解析为dict用于校验是否登陆成功/包含关键字段
        """
        cookies = {k: str(v) for k, v in flow.request.cookies.items()}
        return cookies.get('MUSIC_U') is not None
        
    def save_cookie(self, flow:HTTPFlow):
        """保存Cookie数据"""
        try:
            headers = {
                'headers': {k: v for k, v in flow.request.headers.items()},
                'cookies': {k: str(v) for k, v in flow.request.cookies.items()} if flow.request.cookies else {}
            }
            cookie_path = Path(self.cookie_config['output_dir'])
            cookie_path = cookie_path / f"cookie.json"
            FileManager.atomic_write_json(cookie_path, headers)
        except Exception as e:
            logger.error(f"保存Cookie数据失败: {e}")
    
    # ============================================
    #            PlayList Extract
    # ============================================
    def _is_playlist_request(self, flow: HTTPFlow):
        path_lower = flow.request.path.lower()
        return ('/eapi/' in path_lower and 
                any(playlist_path in path_lower for playlist_path in self.PLAYLIST_PATHS))
        
    def extract_playlist(self, flow: HTTPFlow):
        """处理播放列表响应"""
        content = self.decoder.decrypt_response_content(flow)
        
        if "playlist" in content:
            playlist = content['playlist']
            playlist_id = str(playlist.get('id', ''))
            tracks = playlist.get('tracks', [])
            logger.info(f"[PLAYLIST] 检测到播放列表响应: {playlist.get('name', 'N/A')} (ID: {playlist_id})")
            
            # 检查播放列表ID是否在目标列表中
            if playlist_id not in self.target_playlist_ids:
                logger.info(f"[FILTER] 跳过播放列表 {playlist_id}，不在目标列表中")
                return
            
            if tracks:
                # 完整数据，直接保存
                logger.info(f"[V6] 完整模式: 播放列表包含{len(tracks)}首歌曲，直接保存")
                self._save_playlist_file(playlist)
            else:
                # 部分数据，等待歌曲数据
                logger.info(f"[V4] 分步模式: 播放列表tracks为空，保存基础数据等待歌曲数据")
                is_merged, playlist = self.playlist_state.store_data(content)
                if is_merged:
                    self._save_playlist_file(playlist)
        elif "songs" in content:
            logger.info(f"[V4] 分步模式: 分步获取到歌曲列表")
            is_merged, playlist = self.playlist_state.store_data(content)
            if is_merged:
                self._save_playlist_file(playlist)
            
    def _save_playlist_file(self, playlist_data: dict) -> None:
        """保存播放列表文件"""
        output_dir = self.playlist_config.get('output_dir')
        try:
            playlist_id = playlist_data["id"]
            output_file = Path(output_dir) / f"playlist_{playlist_id}.json"
            
            if FileManager.atomic_write_json(output_file, playlist_data):
                logger.info(f"播放列表已保存到: {output_file}")
        except Exception as e:
            logger.error(f"保存播放列表文件失败: {e}")