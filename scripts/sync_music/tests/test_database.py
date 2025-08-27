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
    
    def test_frequency_control_skip_unchanged_playlist(self):
        """测试频率控制：跳过未变化的播放列表"""
        # 第一次同步
        json_data = {
            'id': 888,
            'name': 'Frequency Test',
            'tracks': [
                {'id': 101, 'name': 'Song1', 'ar': [{'name': 'Artist1'}]},
                {'id': 102, 'name': 'Song2', 'ar': [{'name': 'Artist2'}]}
            ]
        }
        
        result1 = self.db_manager.sync_playlist_from_json(
            json_data, self.user_dir, self.input_dir, self.output_dir, check_frequency=True
        )
        self.assertTrue(result1)
        
        # 第二次同步相同数据，应该被跳过
        result2 = self.db_manager.sync_playlist_from_json(
            json_data, self.user_dir, self.input_dir, self.output_dir, check_frequency=True
        )
        self.assertTrue(result2)  # 返回True但实际跳过了
        
        # 验证playlist确实存在且有track_ids_hash
        with self.db_manager.get_session() as session:
            playlist = session.query(Playlist).filter_by(netease_id=888).first()
            self.assertIsNotNone(playlist)
            self.assertIsNotNone(playlist.track_ids_hash)
    
    def test_frequency_control_sync_changed_playlist(self):
        """测试频率控制：同步变化的播放列表"""
        # 第一次同步
        json_data_v1 = {
            'id': 777,
            'name': 'Change Test',
            'tracks': [
                {'id': 201, 'name': 'Song1', 'ar': [{'name': 'Artist1'}]},
                {'id': 202, 'name': 'Song2', 'ar': [{'name': 'Artist2'}]}
            ]
        }
        
        result1 = self.db_manager.sync_playlist_from_json(
            json_data_v1, self.user_dir, self.input_dir, self.output_dir, check_frequency=True
        )
        self.assertTrue(result1)
        
        # 获取第一次同步后的hash
        with self.db_manager.get_session() as session:
            playlist = session.query(Playlist).filter_by(netease_id=777).first()
            original_hash = playlist.track_ids_hash
        
        # 第二次同步修改的数据（添加了一首歌）
        json_data_v2 = {
            'id': 777,
            'name': 'Change Test',
            'tracks': [
                {'id': 201, 'name': 'Song1', 'ar': [{'name': 'Artist1'}]},
                {'id': 202, 'name': 'Song2', 'ar': [{'name': 'Artist2'}]},
                {'id': 203, 'name': 'Song3', 'ar': [{'name': 'Artist3'}]}  # 新增歌曲
            ]
        }
        
        result2 = self.db_manager.sync_playlist_from_json(
            json_data_v2, self.user_dir, self.input_dir, self.output_dir, check_frequency=True
        )
        self.assertTrue(result2)
        
        # 验证hash已变化
        with self.db_manager.get_session() as session:
            playlist = session.query(Playlist).filter_by(netease_id=777).first()
            new_hash = playlist.track_ids_hash
            self.assertNotEqual(original_hash, new_hash)
            
            # 验证新增的歌曲
            track3 = session.query(Track).filter_by(netease_id=203).first()
            self.assertIsNotNone(track3)
            self.assertEqual(track3.name, 'Song3')
    
    def test_calculate_track_ids_hash(self):
        """测试trackIds hash计算"""
        track_ids_1 = [101, 102, 103]
        track_ids_2 = [103, 101, 102]  # 相同歌曲，不同顺序
        track_ids_3 = [101, 102, 104]  # 不同歌曲
        
        hash_1 = self.db_manager._calculate_track_ids_hash(track_ids_1)
        hash_2 = self.db_manager._calculate_track_ids_hash(track_ids_2)
        hash_3 = self.db_manager._calculate_track_ids_hash(track_ids_3)
        
        # 相同歌曲不同顺序应该产生相同hash（因为内部会排序）
        self.assertEqual(hash_1, hash_2)
        
        # 不同歌曲应该产生不同hash
        self.assertNotEqual(hash_1, hash_3)
        
        # hash应该是32位十六进制字符串
        self.assertEqual(len(hash_1), 32)
        self.assertTrue(all(c in '0123456789abcdef' for c in hash_1))

if __name__ == '__main__':
    unittest.main()