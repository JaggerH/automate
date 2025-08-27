import os
import re
import glob
from typing import List, Optional, Tuple, Union
from pathlib import Path

class FileMatcher:
    
    @staticmethod
    def clean_filename(text: str) -> str:
        """清理文件名，移除非法字符"""
        invalid_chars = r'[<>:"/\\|?*]'
        return re.sub(invalid_chars, '_', text).strip()
    
    @staticmethod
    def generate_filename(track: dict) -> str:
        """根据track信息生成文件名: 艺术家 - 歌曲名"""
        artists = []
        for artist in track.get('ar', []):
            artists.append(artist['name'])
        
        artist_str = ', '.join(artists) if artists else 'Unknown Artist'
        track_name = track.get('name', 'Unknown Track')
        
        artist_str = FileMatcher.clean_filename(artist_str)
        track_name = FileMatcher.clean_filename(track_name)
        
        return f"{artist_str} - {track_name}"
    
    @staticmethod
    def find_file_in_user_dir(user_dirs: Union[str, List[str]], base_filename: str) -> Optional[str]:
        """在用户目录中查找文件，支持mp3和flac格式，支持多个目录"""
        # 处理单个目录或目录列表
        if isinstance(user_dirs, str):
            user_dirs = [user_dirs]
        
        extensions = ['.mp3', '.flac']
        all_matches = []
        
        for user_dir in user_dirs:
            if not os.path.exists(user_dir):
                continue
                
            matches = []
            
            for ext in extensions:
                # 直接匹配
                pattern = os.path.join(user_dir, f"{base_filename}{ext}")
                found_files = glob.glob(pattern)
                matches.extend(found_files)
                
                # 递归搜索
                pattern_recursive = os.path.join(user_dir, '**', f"{base_filename}{ext}")
                found_files_recursive = glob.glob(pattern_recursive, recursive=True)
                matches.extend(found_files_recursive)
            
            all_matches.extend(matches)
        
        # 去重
        unique_matches = list(set(all_matches))
        
        if len(unique_matches) == 1:
            return unique_matches[0]
        elif len(unique_matches) > 1:
            # 如果有多个匹配，返回第一个（可以后续优化为选择最佳匹配）
            return unique_matches[0]
        
        return None
    
    @staticmethod
    def find_file_in_input_dir(input_dir: str, track_id: int) -> Optional[Tuple[str, int]]:
        """在input目录中查找文件，格式: id-bitrate-hash，返回最高码率的文件"""
        if not os.path.exists(input_dir):
            return None
            
        pattern = os.path.join(input_dir, f"{track_id}-*-*.uc")
        matches = glob.glob(pattern)
        
        # if not matches:
        #     pattern_recursive = os.path.join(input_dir, '**', f"{track_id}-*-*.uc")
        #     matches = glob.glob(pattern_recursive, recursive=True)
        
        if not matches:
            return None
        
        best_file = None
        best_bitrate = 0
        
        for file_path in matches:
            filename = os.path.basename(file_path)
            parts = filename.replace('.uc', '').split('-')
            
            if len(parts) >= 2:
                try:
                    bitrate = int(parts[1])
                    if bitrate > best_bitrate:
                        best_bitrate = bitrate
                        best_file = file_path
                except ValueError:
                    continue
        
        return (best_file, best_bitrate) if best_file else None
    
    @staticmethod
    def decode_uc_file(input_path, output_path):
        """解密网易云音乐的.uc缓存文件"""
        try:
            with open(input_path, "rb") as f:
                data = bytearray(f.read())
            
            # 网易云音乐的解密算法
            for i in range(len(data)):
                data[i] ^= 0xA3   # 异或解密
            
            # 写入解密后的文件
            with open(output_path, "wb") as f:
                f.write(data)
                
            # 避免特殊字符编码问题，只在verbose模式显示详细信息
            # print(f"成功解密: {os.path.basename(input_path)} -> {os.path.basename(output_path)}")
            
        except Exception as e:
            print(f"解密失败 {input_path}: {e}")
            raise
        
    @staticmethod
    def copy_and_rename_file(source_path: str, output_dir: str, new_filename: str) -> str:
        """复制文件到output目录并重命名"""
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        dest_path = os.path.join(output_dir, f"{new_filename}.mp3")
        
        # decode_uc_file的参数是正确的：source_path(文件), dest_path(文件)
        FileMatcher.decode_uc_file(source_path, dest_path)
        return dest_path