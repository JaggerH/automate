import unittest
import tempfile
import os
import shutil
import json
from datetime import datetime

from ..database import DatabaseManager
from ..models import Base, Playlist, Track

class TestDatabaseManager(unittest.TestCase):
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, 'test.db')
        self.db_manager = DatabaseManager(f'sqlite:///{self.db_path}')
        
        self.user_dir = os.path.join(self.test_dir, 'user')
        self.input_dir = os.path.join(self.test_dir, 'input')
        self.output_dir = os.path.join(self.test_dir, 'output')
        
        os.makedirs(self.user_dir, exist_ok=True)
        os.makedirs(self.input_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)
    
    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_database_creation(self):
        """测试数据库创建功能"""
        self.assertTrue(os.path.exists(self.db_path))
    
    def test_get_session_context_manager(self):
        """测试数据库会话上下文管理器"""
        with self.db_manager.get_session() as session:
            self.assertIsNotNone(session)
            
            playlist = Playlist(
                netease_id=12345,
                name='Test Playlist',
                description='Test Description'
            )
            session.add(playlist)
        
        with self.db_manager.get_session() as session:
            found_playlist = session.query(Playlist).filter_by(netease_id=12345).first()
            self.assertIsNotNone(found_playlist)
            self.assertEqual(found_playlist.name, 'Test Playlist')
    
    def test_sync_playlist_from_json_new_playlist(self):
        """测试从JSON同步新播放列表"""
        json_data = {
            'id': 60567077,
            'name': 'Test Playlist',
            'description': 'Test Description',
            'trackCount': 2,
            'createTime': 1427113590980,
            'coverImgUrl': 'http://example.com/cover.jpg',
            'creator': {
                'userId': 59940490,
                'nickname': 'TestUser'
            },
            'tracks': [
                {
                    'id': 2084366052,
                    'name': '测试歌曲1',
                    'duration': 164000,
                    'ar': [{'name': 'TestArtist1'}]
                },
                {
                    'id': 2084366053,
                    'name': '测试歌曲2',
                    'duration': 200000,
                    'ar': [{'name': 'TestArtist2'}]
                }
            ]
        }
        
        result = self.db_manager.sync_playlist_from_json(
            json_data, self.user_dir, self.input_dir, self.output_dir
        )
        
        self.assertTrue(result)
        
        with self.db_manager.get_session() as session:
            playlist = session.query(Playlist).filter_by(netease_id=60567077).first()
            self.assertIsNotNone(playlist)
            self.assertEqual(playlist.name, 'Test Playlist')
            self.assertEqual(playlist.creator_name, 'TestUser')
            
            tracks = session.query(Track).all()
            self.assertEqual(len(tracks), 2)
            
            track1 = session.query(Track).filter_by(netease_id=2084366052).first()
            self.assertIsNotNone(track1)
            self.assertEqual(track1.name, '测试歌曲1')
            self.assertEqual(track1.artist_names, 'TestArtist1')
    
    def test_get_playlist_stats(self):
        """测试获取数据库统计信息"""
        json_data = {
            'id': 123,
            'name': 'Stats Test',
            'tracks': [
                {'id': 1, 'name': 'Song1', 'ar': [{'name': 'Artist1'}]},
                {'id': 2, 'name': 'Song2', 'ar': [{'name': 'Artist2'}]}
            ]
        }
        
        self.db_manager.sync_playlist_from_json(
            json_data, self.user_dir, self.input_dir, self.output_dir
        )
        
        stats = self.db_manager.get_playlist_stats()
        
        self.assertEqual(stats['total_playlists'], 1)
        self.assertEqual(stats['total_tracks'], 2)
        self.assertEqual(stats['tracks_without_files'], 2)
        self.assertEqual(stats['tracks_with_files'], 0)
    
    def test_sync_playlist_existing_playlist_update(self):
        """测试更新现有播放列表"""
        with self.db_manager.get_session() as session:
            existing_playlist = Playlist(
                netease_id=999,
                name='Old Name',
                description='Old Description'
            )
            session.add(existing_playlist)
        
        json_data = {
            'id': 999,
            'name': 'Updated Name',
            'description': 'Updated Description',
            'trackCount': 1,
            'tracks': [
                {'id': 100, 'name': 'New Song', 'ar': [{'name': 'New Artist'}]}
            ]
        }
        
        result = self.db_manager.sync_playlist_from_json(
            json_data, self.user_dir, self.input_dir, self.output_dir
        )
        
        self.assertTrue(result)
        
        with self.db_manager.get_session() as session:
            playlist = session.query(Playlist).filter_by(netease_id=999).first()
            self.assertEqual(playlist.name, 'Updated Name')
            self.assertEqual(playlist.description, 'Updated Description')

if __name__ == '__main__':
    unittest.main()