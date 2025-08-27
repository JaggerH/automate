import os
import re
import glob
import hashlib
import requests
from typing import List, Optional, Tuple, Union, Dict, Set
from pathlib import Path
import datetime
import subprocess

try:
    import mutagen
    from mutagen.flac import FLAC, Picture
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TDRC
    from mutagen.mp4 import MP4, MP4Cover
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

class FileMatcher:
    
    def __init__(self, user_dirs: Optional[Union[str, List[str]]] = None, 
                 input_dir: Optional[str] = None, 
                 output_dir: Optional[str] = None):
        """
        初始化文件匹配器，建立目录文件索引
        
        Args:
            user_dirs: 用户音乐目录，支持单个目录或目录列表
            input_dir: 输入目录（缓存文件目录）
            output_dir: 输出目录
        """
        self.user_dirs = self._normalize_dirs(user_dirs) if user_dirs else []
        self.input_dir = input_dir
        self.output_dir = output_dir
        
        # 文件索引缓存
        self.user_files_index: Dict[str, str] = {}  # filename -> full_path
        self.output_files_index: Dict[str, str] = {}  # filename -> full_path  
        self.input_files_index: Dict[str, Tuple[str, int]] = {}  # track_id -> (full_path, bitrate)
        
        # 构建索引
        self._build_file_indexes()
    
    def _normalize_dirs(self, dirs: Union[str, List[str]]) -> List[str]:
        """标准化目录列表"""
        if isinstance(dirs, str):
            return [dirs]
        return dirs
    
    def _build_file_indexes(self):
        """构建文件索引以提高查找效率"""
        # 构建用户目录索引
        for user_dir in self.user_dirs:
            if os.path.exists(user_dir):
                self._build_audio_index(user_dir, self.user_files_index)
        
        # 构建输出目录索引
        if self.output_dir and os.path.exists(self.output_dir):
            self._build_audio_index(self.output_dir, self.output_files_index)
        
        # 构建输入目录索引（.uc文件）
        if self.input_dir and os.path.exists(self.input_dir):
            self._build_input_index(self.input_dir)
    
    def _build_audio_index(self, directory: str, index: Dict[str, str]):
        """构建音频文件索引"""
        extensions = ['.mp3', '.flac', '.m4a']
        for ext in extensions:
            pattern = os.path.join(directory, f"*{ext}")
            for file_path in glob.glob(pattern):
                filename = os.path.splitext(os.path.basename(file_path))[0]
                index[filename] = file_path
    
    def _build_input_index(self, directory: str):
        """构建输入目录(.uc文件)索引"""
        pattern = os.path.join(directory, "*-*-*.uc")
        for file_path in glob.glob(pattern):
            filename = os.path.basename(file_path)
            parts = filename.replace('.uc', '').split('-')
            
            if len(parts) >= 3:
                try:
                    track_id = parts[0]
                    bitrate = int(parts[1])
                    
                    # 保留最高码率的文件
                    if track_id not in self.input_files_index or bitrate > self.input_files_index[track_id][1]:
                        self.input_files_index[track_id] = (file_path, bitrate)
                except ValueError:
                    continue
    
    def find_file_by_filename(self, base_filename: str) -> Optional[Tuple[str, str]]:
        """
        按文件名查找文件（实例方法），按优先级搜索3个目录
        
        Args:
            base_filename: 基础文件名（不含扩展名）
            
        Returns:
            Tuple[file_path, source_type] 或 None
            source_type: 'user', 'output', 'input'
        """
        # 优先级1: 用户目录
        if base_filename in self.user_files_index:
            return self.user_files_index[base_filename], 'user'
        
        # 优先级2: 输出目录
        if base_filename in self.output_files_index:
            return self.output_files_index[base_filename], 'output'
        
        # 输入目录不支持文件名查找，只支持track_id查找
        return None
    
    def find_file_by_track_id(self, track_id: int) -> Optional[Tuple[str, int, str]]:
        """
        按track_id查找输入目录文件
        
        Args:
            track_id: 曲目ID
            
        Returns:
            Tuple[file_path, bitrate, source_type] 或 None
        """
        track_id_str = str(track_id)
        if track_id_str in self.input_files_index:
            file_path, bitrate = self.input_files_index[track_id_str]
            return file_path, bitrate, 'input'
        
        return None
    
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
        
        extensions = ['.mp3', '.flac', '.m4a']
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
                # pattern_recursive = os.path.join(user_dir, '**', f"{base_filename}{ext}")
                # found_files_recursive = glob.glob(pattern_recursive, recursive=True)
                # matches.extend(found_files_recursive)
            
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
    def detect_audio_format(file_path):
        cmd = ["ffprobe", "-v", "error", "-show_entries",
            "format=format_name", "-of", "default=noprint_wrappers=1:nokey=1", file_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        fmt = result.stdout.strip().lower()
        print(fmt)
        if "mp3" in fmt:
            return ".mp3"
        elif "mov" in fmt or "mp4" in fmt or "m4a" in fmt:
            return ".m4a"
        elif "flac" in fmt:
            return ".flac"
        else:
            return None
    
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
    def copy_and_rename_file(source_path: str, output_dir: str, new_filename: str, 
                            track_metadata: Optional[Dict] = None) -> str:
        """复制文件到output目录并重命名，可选添加元数据"""
        # if not os.path.exists(output_dir):
        #     os.makedirs(output_dir, exist_ok=True)
        
        # dest_path = os.path.join(output_dir, f"{new_filename}.mp3")
        
        # # decode_uc_file的参数是正确的：source_path(文件), dest_path(文件)
        # FileMatcher.decode_uc_file(source_path, dest_path)
        
        # # 添加音频元数据
        # if track_metadata:
        #     FileMatcher.write_audio_metadata(dest_path, track_metadata)
        
        # return dest_path
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        # 临时路径先解密
        temp_path = os.path.join(output_dir, f"{new_filename}.mp3")
        FileMatcher.decode_uc_file(source_path, temp_path)
        
        # 用 ffprobe 或 mutagen 自动检测文件类型
        ext = ".mp3"
        try:
            MP3(temp_path)
            ext = ".mp3"
        except Exception:
            try:
                MP4(temp_path)
                ext = ".m4a"
            except Exception:
                try:
                    FLAC(temp_path)
                    ext = ".flac"
                except Exception:
                    print(f"无法识别音频格式: {temp_path}")
                    os.remove(temp_path)
                    raise ValueError("未知音频格式")
        
        # 最终目标路径
        dest_path = os.path.join(output_dir, f"{new_filename}{ext}")
        os.rename(temp_path, dest_path)
        
        # 添加元数据
        if track_metadata:
            FileMatcher.write_audio_metadata(dest_path, track_metadata)
        
        return dest_path
    
    @staticmethod
    def write_audio_metadata(file_path: str, track_metadata: Dict) -> bool:
        """
        向音频文件写入元数据（封面、歌手、专辑等信息）
        支持 MP3, M4A/MP4, FLAC。
        """
        if not os.path.exists(file_path):
            print(f"文件不存在: {file_path}")
            return False

        ext = os.path.splitext(file_path)[1].lower()

        try:
            # ================= MP3 =================
            if ext == ".mp3":
                audio = MP3(file_path, ID3=ID3)
                if audio.tags is None:
                    audio.add_tags()

                if track_metadata.get("name"):
                    audio.tags.add(TIT2(encoding=3, text=track_metadata["name"]))

                if track_metadata.get("ar"):
                    artists = [a["name"] for a in track_metadata["ar"] if "name" in a]
                    if artists:
                        audio.tags.add(TPE1(encoding=3, text=artists))

                if track_metadata.get("al") and "name" in track_metadata["al"]:
                    audio.tags.add(TALB(encoding=3, text=track_metadata["al"]["name"]))

                if track_metadata.get("publishTime"):
                    try:
                        year = datetime.datetime.fromtimestamp(track_metadata["publishTime"] / 1000).year
                        audio.tags.add(TDRC(encoding=3, text=str(year)))
                    except Exception:
                        pass

                if track_metadata.get("al") and track_metadata["al"].get("picUrl"):
                    cover_data = FileMatcher.download_cover_image(track_metadata["al"]["picUrl"])
                    if cover_data:
                        audio.tags.add(APIC(
                            encoding=3,
                            mime='image/jpeg',
                            type=3,  # 封面
                            desc='Cover',
                            data=cover_data
                        ))

                audio.save()
                return True

            # ================= M4A / MP4 =================
            elif ext in [".m4a", ".mp4"]:
                audio = MP4(file_path)

                if track_metadata.get("name"):
                    audio["©nam"] = track_metadata["name"]

                if track_metadata.get("ar"):
                    artists = [a["name"] for a in track_metadata["ar"] if "name" in a]
                    if artists:
                        audio["©ART"] = ", ".join(artists)

                if track_metadata.get("al") and "name" in track_metadata["al"]:
                    audio["©alb"] = track_metadata["al"]["name"]

                if track_metadata.get("publishTime"):
                    try:
                        year = datetime.datetime.fromtimestamp(track_metadata["publishTime"] / 1000).year
                        audio["©day"] = str(year)
                    except Exception:
                        pass

                if track_metadata.get("al") and track_metadata["al"].get("picUrl"):
                    cover_data = FileMatcher.download_cover_image(track_metadata["al"]["picUrl"])
                    if cover_data:
                        audio["covr"] = [MP4Cover(cover_data, imageformat=MP4Cover.FORMAT_JPEG)]

                audio.save()
                return True

            # ================= FLAC =================
            elif ext == ".flac":
                audio = FLAC(file_path)

                if track_metadata.get("name"):
                    audio["title"] = track_metadata["name"]

                if track_metadata.get("ar"):
                    artists = [a["name"] for a in track_metadata["ar"] if "name" in a]
                    if artists:
                        audio["artist"] = ", ".join(artists)

                if track_metadata.get("al") and "name" in track_metadata["al"]:
                    audio["album"] = track_metadata["al"]["name"]

                if track_metadata.get("publishTime"):
                    try:
                        year = datetime.datetime.fromtimestamp(track_metadata["publishTime"] / 1000).year
                        audio["date"] = str(year)
                    except Exception:
                        pass

                if track_metadata.get("al") and track_metadata["al"].get("picUrl"):
                    cover_data = FileMatcher.download_cover_image(track_metadata["al"]["picUrl"])
                    if cover_data:
                        pic = Picture()
                        pic.data = cover_data
                        pic.type = 3  # 封面
                        pic.mime = "image/jpeg"
                        audio.add_picture(pic)

                audio.save()
                return True

            else:
                print(f"不支持的音频格式: {file_path}")
                return False

        except Exception as e:
            print(f"写入元数据失败 {file_path}: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        
    @staticmethod
    def download_cover_image(cover_url: str, timeout: int = 10) -> Optional[bytes]:
        """
        下载封面图片
        
        Args:
            cover_url: 封面图片URL
            timeout: 下载超时时间（秒）
            
        Returns:
            bytes: 图片数据，失败时返回None
        """
        if not cover_url:
            return None
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(cover_url, headers=headers, timeout=timeout)
            response.raise_for_status()
            
            # 检查是否为图片类型
            content_type = response.headers.get('content-type', '').lower()
            if 'image' not in content_type:
                print(f"Warning: Invalid image content type: {content_type}")
                return None
                
            return response.content
            
        except requests.RequestException as e:
            print(f"Failed to download cover image from {cover_url}: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error downloading cover: {e}")
            return None