import hashlib
import os
from typing import Optional, Tuple
from pathlib import Path

try:
    import mutagen
    from mutagen.mp3 import MP3
    from mutagen.flac import FLAC
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

class AudioInfoExtractor:
    
    @staticmethod
    def get_file_hash(file_path: str) -> Optional[str]:
        """计算文件的MD5 hash值"""
        if not os.path.exists(file_path):
            return None
            
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            print(f"Error calculating hash for {file_path}: {e}")
            return None
    
    @staticmethod
    def get_audio_bitrate(file_path: str) -> Optional[int]:
        """获取音频文件的码率"""
        if not MUTAGEN_AVAILABLE:
            # print("Mutagen library not available. Please install: pip install mutagen")
            return None
            
        if not os.path.exists(file_path):
            return None
        
        try:
            # 使用mutagen自动检测文件格式，而不依赖扩展名
            audio_file = mutagen.File(file_path)
            if audio_file and hasattr(audio_file, 'info') and audio_file.info:
                return getattr(audio_file.info, 'bitrate', None)
                    
        except Exception as e:
            # 只在verbose模式下显示错误，避免控制台被刷屏
            # print(f"Error reading audio info for {file_path}: {e}")
            pass
            
        return None
    
    @staticmethod
    def get_audio_info(file_path: str) -> Tuple[Optional[int], Optional[str]]:
        """获取音频文件的码率和hash值"""
        bitrate = AudioInfoExtractor.get_audio_bitrate(file_path)
        file_hash = AudioInfoExtractor.get_file_hash(file_path)
        
        return bitrate, file_hash
    
    @staticmethod
    def extract_bitrate_from_filename(filename: str) -> Optional[int]:
        """从文件名中提取码率信息 (格式: id-bitrate-hash.mp3)"""
        try:
            base_name = os.path.splitext(filename)[0]
            parts = base_name.split('-')
            
            if len(parts) >= 2:
                return int(parts[1])
        except (ValueError, IndexError):
            pass
            
        return None