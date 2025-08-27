import unittest
import tempfile
import os
import shutil
from pathlib import Path

from ..file_matcher import FileMatcher

class TestFileMatcher(unittest.TestCase):
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.user_dir = os.path.join(self.test_dir, 'user')
        self.input_dir = os.path.join(self.test_dir, 'input')
        self.output_dir = os.path.join(self.test_dir, 'output')
        
        os.makedirs(self.user_dir, exist_ok=True)
        os.makedirs(self.input_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)
    
    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_clean_filename(self):
        """测试文件名清理功能"""
        test_cases = [
            ('test<>:"/\\|?*file', 'test_________file'),
            ('normal_file', 'normal_file'),
            ('中文歌名', '中文歌名'),
            ('  spaced  ', 'spaced'),
        ]
        
        for input_name, expected in test_cases:
            with self.subTest(input_name=input_name):
                result = FileMatcher.clean_filename(input_name)
                self.assertEqual(result, expected)
    
    def test_generate_filename(self):
        """测试文件名生成功能"""
        track = {
            'name': '测试歌曲',
            'ar': [
                {'name': '艺术家1'},
                {'name': '艺术家2'}
            ]
        }
        
        result = FileMatcher.generate_filename(track)
        expected = '艺术家1, 艺术家2 - 测试歌曲'
        self.assertEqual(result, expected)
    
    def test_generate_filename_no_artist(self):
        """测试无艺术家信息的文件名生成"""
        track = {
            'name': '测试歌曲',
            'ar': []
        }
        
        result = FileMatcher.generate_filename(track)
        expected = 'Unknown Artist - 测试歌曲'
        self.assertEqual(result, expected)
    
    def test_find_file_in_user_dir_single_match(self):
        """测试在用户目录中查找单个匹配文件"""
        test_file = os.path.join(self.user_dir, 'test_song.mp3')
        Path(test_file).touch()
        
        result = FileMatcher.find_file_in_user_dir(self.user_dir, 'test_song')
        self.assertEqual(result, test_file)
    
    def test_find_file_in_user_dir_no_match(self):
        """测试在用户目录中查找不存在的文件"""
        result = FileMatcher.find_file_in_user_dir(self.user_dir, 'nonexistent')
        self.assertIsNone(result)
    
    def test_find_file_in_multiple_user_dirs(self):
        """测试在多个用户目录中查找文件"""
        user_dir2 = os.path.join(self.test_dir, 'user2')
        os.makedirs(user_dir2, exist_ok=True)
        
        # 在第一个目录中创建文件
        test_file1 = os.path.join(self.user_dir, 'song1.mp3')
        Path(test_file1).touch()
        
        # 在第二个目录中创建文件
        test_file2 = os.path.join(user_dir2, 'song2.flac')
        Path(test_file2).touch()
        
        user_dirs = [self.user_dir, user_dir2]
        
        # 测试在第一个目录找到文件
        result1 = FileMatcher.find_file_in_user_dir(user_dirs, 'song1')
        self.assertEqual(result1, test_file1)
        
        # 测试在第二个目录找到文件
        result2 = FileMatcher.find_file_in_user_dir(user_dirs, 'song2')
        self.assertEqual(result2, test_file2)
        
        # 测试找不到文件
        result3 = FileMatcher.find_file_in_user_dir(user_dirs, 'nonexistent')
        self.assertIsNone(result3)
    
    def test_find_file_in_user_dir_with_nonexistent_dirs(self):
        """测试当某些用户目录不存在时的处理"""
        user_dirs = [self.user_dir, '/nonexistent/path']
        
        test_file = os.path.join(self.user_dir, 'test_song.mp3')
        Path(test_file).touch()
        
        result = FileMatcher.find_file_in_user_dir(user_dirs, 'test_song')
        self.assertEqual(result, test_file)
    
    def test_find_file_in_input_dir_highest_bitrate(self):
        """测试在input目录中查找最高码率文件"""
        files = [
            '123-128-hash1.mp3',
            '123-320-hash2.mp3',
            '123-192-hash3.mp3'
        ]
        
        for filename in files:
            Path(os.path.join(self.input_dir, filename)).touch()
        
        result = FileMatcher.find_file_in_input_dir(self.input_dir, 123)
        
        self.assertIsNotNone(result)
        file_path, bitrate = result
        self.assertTrue(file_path.endswith('123-320-hash2.mp3'))
        self.assertEqual(bitrate, 320)
    
    def test_find_file_in_input_dir_no_match(self):
        """测试在input目录中查找不存在的文件"""
        result = FileMatcher.find_file_in_input_dir(self.input_dir, 999)
        self.assertIsNone(result)
    
    def test_copy_and_rename_file(self):
        """测试文件复制和重命名功能"""
        source_file = os.path.join(self.input_dir, 'source.mp3')
        with open(source_file, 'w') as f:
            f.write('test content')
        
        result = FileMatcher.copy_and_rename_file(
            source_file, self.output_dir, 'renamed_file'
        )
        
        expected_path = os.path.join(self.output_dir, 'renamed_file.mp3')
        self.assertEqual(result, expected_path)
        self.assertTrue(os.path.exists(expected_path))
        
        with open(expected_path, 'r') as f:
            content = f.read()
        self.assertEqual(content, 'test content')
    
    def test_file_matcher_instance_initialization(self):
        """测试FileMatcher实例初始化和文件索引构建"""
        # 创建测试文件
        test_files = {
            'user': ['song1.mp3', 'song2.flac'],
            'output': ['song3.mp3'],
            'input': ['100-320-hash1.uc', '101-128-hash2.uc']
        }
        
        for file_type, files in test_files.items():
            dir_path = getattr(self, f'{file_type}_dir')
            for filename in files:
                if file_type == 'input':
                    # 创建.uc文件
                    file_path = os.path.join(dir_path, filename)
                    with open(file_path, 'wb') as f:
                        f.write(b'test binary data')
                else:
                    Path(os.path.join(dir_path, filename)).touch()
        
        # 初始化FileMatcher实例
        matcher = FileMatcher(self.user_dir, self.input_dir, self.output_dir)
        
        # 验证用户目录索引
        self.assertIn('song1', matcher.user_files_index)
        self.assertIn('song2', matcher.user_files_index)
        self.assertEqual(len(matcher.user_files_index), 2)
        
        # 验证输出目录索引
        self.assertIn('song3', matcher.output_files_index)
        self.assertEqual(len(matcher.output_files_index), 1)
        
        # 验证输入目录索引
        self.assertIn('100', matcher.input_files_index)
        self.assertIn('101', matcher.input_files_index)
        self.assertEqual(matcher.input_files_index['100'][1], 320)  # bitrate
        self.assertEqual(matcher.input_files_index['101'][1], 128)  # bitrate
    
    def test_find_file_by_filename_priority(self):
        """测试按文件名查找的优先级逻辑"""
        # 在用户目录创建文件
        user_file = os.path.join(self.user_dir, 'test_song.mp3')
        Path(user_file).touch()
        
        # 在输出目录也创建同名文件
        output_file = os.path.join(self.output_dir, 'test_song.mp3')
        Path(output_file).touch()
        
        matcher = FileMatcher(self.user_dir, self.input_dir, self.output_dir)
        
        result = matcher.find_file_by_filename('test_song')
        
        # 应该返回用户目录的文件（优先级更高）
        self.assertIsNotNone(result)
        file_path, source_type = result
        self.assertEqual(file_path, user_file)
        self.assertEqual(source_type, 'user')
    
    def test_find_file_by_filename_output_only(self):
        """测试仅在输出目录找到文件的情况"""
        output_file = os.path.join(self.output_dir, 'output_only.flac')
        Path(output_file).touch()
        
        matcher = FileMatcher(self.user_dir, self.input_dir, self.output_dir)
        
        result = matcher.find_file_by_filename('output_only')
        
        self.assertIsNotNone(result)
        file_path, source_type = result
        self.assertEqual(file_path, output_file)
        self.assertEqual(source_type, 'output')
    
    def test_find_file_by_track_id(self):
        """测试按track_id查找文件"""
        # 创建输入目录文件
        input_files = ['123-320-hash1.uc', '123-128-hash2.uc', '456-192-hash3.uc']
        for filename in input_files:
            file_path = os.path.join(self.input_dir, filename)
            with open(file_path, 'wb') as f:
                f.write(b'encrypted data')
        
        matcher = FileMatcher(self.user_dir, self.input_dir, self.output_dir)
        
        # 测试找到track_id 123的最高码率文件
        result = matcher.find_file_by_track_id(123)
        self.assertIsNotNone(result)
        file_path, bitrate, source_type = result
        self.assertTrue(file_path.endswith('123-320-hash1.uc'))
        self.assertEqual(bitrate, 320)
        self.assertEqual(source_type, 'input')
        
        # 测试找到track_id 456的文件
        result2 = matcher.find_file_by_track_id(456)
        self.assertIsNotNone(result2)
        file_path2, bitrate2, source_type2 = result2
        self.assertTrue(file_path2.endswith('456-192-hash3.uc'))
        self.assertEqual(bitrate2, 192)
        
        # 测试找不到的track_id
        result3 = matcher.find_file_by_track_id(999)
        self.assertIsNone(result3)
    
    def test_multiple_user_dirs_initialization(self):
        """测试多用户目录的初始化"""
        user_dir2 = os.path.join(self.test_dir, 'user2')
        os.makedirs(user_dir2, exist_ok=True)
        
        # 在不同目录创建文件
        Path(os.path.join(self.user_dir, 'song1.mp3')).touch()
        Path(os.path.join(user_dir2, 'song2.flac')).touch()
        
        matcher = FileMatcher([self.user_dir, user_dir2], self.input_dir, self.output_dir)
        
        # 验证两个目录的文件都被索引
        self.assertIn('song1', matcher.user_files_index)
        self.assertIn('song2', matcher.user_files_index)
        self.assertEqual(len(matcher.user_files_index), 2)

if __name__ == '__main__':
    unittest.main()