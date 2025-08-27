import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy import create_engine, or_
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from contextlib import contextmanager

from .models import Base, Playlist, Track, playlist_track_association
from .file_matcher import FileMatcher
from .audio_info import AudioInfoExtractor

class DatabaseManager:
    
    def __init__(self, database_url: str = "sqlite:///music_sync.db"):
        self.engine = create_engine(database_url, echo=False)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    @contextmanager
    def get_session(self) -> Session:
        """获取数据库会话，支持事务"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
    
    def sync_playlist_from_json(self, json_data: Dict[str, Any], user_dir: str, 
                               input_dir: str, output_dir: str) -> bool:
        """从JSON数据同步播放列表到数据库"""
        
        try:
            with self.get_session() as session:
                playlist_data = json_data
                
                playlist = session.query(Playlist).filter_by(
                    netease_id=playlist_data['id']
                ).first()
                
                if not playlist:
                    playlist = Playlist(
                        netease_id=playlist_data['id'],
                        name=playlist_data.get('name', ''),
                        description=playlist_data.get('description'),
                        creator_id=playlist_data.get('creator', {}).get('userId'),
                        creator_name=playlist_data.get('creator', {}).get('nickname'),
                        track_count=playlist_data.get('trackCount', 0),
                        cover_img_url=playlist_data.get('coverImgUrl')
                    )
                    
                    if 'createTime' in playlist_data:
                        playlist.create_time = datetime.fromtimestamp(
                            playlist_data['createTime'] / 1000
                        )
                    
                    session.add(playlist)
                    session.flush()
                else:
                    playlist.name = playlist_data.get('name', playlist.name)
                    playlist.description = playlist_data.get('description', playlist.description)
                    playlist.track_count = playlist_data.get('trackCount', playlist.track_count)
                    playlist.cover_img_url = playlist_data.get('coverImgUrl', playlist.cover_img_url)
                
                existing_associations = session.query(playlist_track_association).filter_by(
                    playlist_id=playlist.id
                ).all()
                for assoc in existing_associations:
                    session.execute(
                        playlist_track_association.delete().where(
                            playlist_track_association.c.playlist_id == playlist.id
                        )
                    )
                
                tracks_data = playlist_data.get('tracks', [])
                
                for position, track_data in enumerate(tracks_data):
                    self._process_track(session, track_data, playlist, position, 
                                     user_dir, input_dir, output_dir)
                
                return True
                
        except Exception as e:
            print(f"Error syncing playlist: {e}")
            return False
    
    def _process_track(self, session: Session, track_data: Dict[str, Any], 
                      playlist: Playlist, position: int, user_dir: str, 
                      input_dir: str, output_dir: str):
        """处理单个track的同步"""
        
        track = session.query(Track).filter_by(netease_id=track_data['id']).first()
        
        artists = [artist['name'] for artist in track_data.get('ar', [])]
        artist_names = ', '.join(artists)
        
        if not track:
            track = Track(
                netease_id=track_data['id'],
                name=track_data.get('name', ''),
                duration=track_data.get('duration', 0),
                artist_names=artist_names
            )
            session.add(track)
            session.flush()
        else:
            track.name = track_data.get('name', track.name)
            track.duration = track_data.get('duration', track.duration)
            track.artist_names = artist_names
        
        base_filename = FileMatcher.generate_filename(track_data)
        
        file_found = False
        bitrate = None
        file_hash = None
        file_path = None
        
        # 优先级1: 在用户目录中查找
        user_file = FileMatcher.find_file_in_user_dir(user_dir, base_filename)
        if user_file:
            bitrate, file_hash = AudioInfoExtractor.get_audio_info(user_file)
            file_path = user_file
            file_found = True
            # print(f"Found in user dir: {user_file}")
        
        # 优先级2: 在输出目录中查找（避免重复复制）
        elif FileMatcher.find_file_in_user_dir(output_dir, base_filename):
            output_file = FileMatcher.find_file_in_user_dir(output_dir, base_filename)
            bitrate, file_hash = AudioInfoExtractor.get_audio_info(output_file)
            file_path = output_file
            file_found = True
            try:
                track_name = track_data.get('name', 'Unknown')
                artist_names = ', '.join([a['name'] for a in track_data.get('ar', [])])
                print(f"已存在输出目录: {track_name} - {artist_names}")
            except UnicodeEncodeError:
                print(f"已存在输出目录: Track ID {track_data['id']}")
        
        # 优先级3: 从输入目录解密复制到输出目录
        else:
            input_file_result = FileMatcher.find_file_in_input_dir(input_dir, track_data['id'])
            if input_file_result:
                source_file, extracted_bitrate = input_file_result
                dest_file = FileMatcher.copy_and_rename_file(source_file, output_dir, base_filename)
                
                bitrate, file_hash = AudioInfoExtractor.get_audio_info(dest_file)
                file_path = dest_file
                file_found = True
                # 避免路径中的特殊字符导致编码问题，简化输出
                try:
                    track_name = track_data.get('name', 'Unknown')
                    artist_names = ', '.join([a['name'] for a in track_data.get('ar', [])])
                    print(f"已从缓存解密: {track_name} - {artist_names}")
                except UnicodeEncodeError:
                    print(f"已从缓存解密: Track ID {track_data['id']}")  # 如果特殊字符无法显示，只显示ID
        
        track.bitrate = bitrate
        track.file_hash = file_hash
        track.file_path = file_path
        track.file_exists = file_found
        
        session.execute(
            playlist_track_association.insert().values(
                playlist_id=playlist.id,
                track_id=track.id,
                position=position
            )
        )
    
    def get_playlist_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        with self.get_session() as session:
            total_playlists = session.query(Playlist).count()
            total_tracks = session.query(Track).count()
            tracks_with_files = session.query(Track).filter(Track.file_exists == True).count()
            tracks_without_files = total_tracks - tracks_with_files
            
            return {
                'total_playlists': total_playlists,
                'total_tracks': total_tracks,
                'tracks_with_files': tracks_with_files,
                'tracks_without_files': tracks_without_files
            }