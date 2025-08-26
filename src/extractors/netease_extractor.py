"""
Work Step
1. trigger is response
2. matched domain/path
3. decode payload and response.content
4. if content include tracks and tracks length > 0, save json
5. if content include tracks and tracks length == 0, wait for songs, save json
"""
from typing import Dict, Optional, List, Union
import json
import time
import logging
import uuid
from pathlib import Path
from .base_extractor import BaseExtractor
from src.utils.netease_crypto import NeteaseCrypto
from mitmproxy.http import HTTPFlow

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
            return True, merged_data
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
            merged_data['playlist']['tracks'] = copy.deepcopy(songs)  # 深拷贝歌曲数据
            merged_data['playlist']['trackCount'] = len(songs)
            logger.info(f"成功合并播放列表数据，包含{len(songs)}首歌曲")
        
        return merged_data
    
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
        if (last_extract_time is None) or (now - last_extract_time > self.interval):
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
            playlist_id = playlist_data["playlist"]["id"]
            output_file = Path(output_dir) / f"playlist_{playlist_id}.json"
            
            if FileManager.atomic_write_json(output_file, playlist_data):
                logger.info(f"播放列表已保存到: {output_file}")
        except Exception as e:
            logger.error(f"保存播放列表文件失败: {e}")