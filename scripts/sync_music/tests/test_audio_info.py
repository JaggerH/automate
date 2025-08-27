import unittest
import tempfile
import os
import shutil
from pathlib import Path

from ..audio_info import AudioInfoExtractor

class TestAudioInfoExtractor(unittest.TestCase):
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.test_dir, 'test.mp3')
        
        with open(self.test_file, 'wb') as f:
            f.write(b'fake mp3 content for testing hash')
    
    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_get_file_hash(self):
        """测试文件hash计算功能"""
        result = AudioInfoExtractor.get_file_hash(self.test_file)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 32)
        
        result2 = AudioInfoExtractor.get_file_hash(self.test_file)
        self.assertEqual(result, result2)
    
    def test_get_file_hash_nonexistent(self):
        """测试不存在文件的hash计算"""
        result = AudioInfoExtractor.get_file_hash('/nonexistent/file.mp3')
        self.assertIsNone(result)
    
    def test_get_audio_bitrate_no_mutagen(self):
        """测试没有mutagen库时的码率获取"""
        original_available = AudioInfoExtractor.__dict__.get('MUTAGEN_AVAILABLE')
        
        import sys
        from unittest.mock import patch
        
        with patch.dict(sys.modules, {'mutagen': None}):
            from ..audio_info import AudioInfoExtractor
            result = AudioInfoExtractor.get_audio_bitrate(self.test_file)
            self.assertIsNone(result)
    
    def test_extract_bitrate_from_filename(self):
        """测试从文件名提取码率"""
        test_cases = [
            ('123-320-hash.mp3', 320),
            ('456-128-abcdef.mp3', 128),
            ('invalid-filename.mp3', None),
            ('123-abc-hash.mp3', None),
            ('no-dashes.mp3', None)
        ]
        
        for filename, expected in test_cases:
            with self.subTest(filename=filename):
                result = AudioInfoExtractor.extract_bitrate_from_filename(filename)
                self.assertEqual(result, expected)
    
    def test_get_audio_info(self):
        """测试音频信息获取功能"""
        bitrate, file_hash = AudioInfoExtractor.get_audio_info(self.test_file)
        
        self.assertIsNotNone(file_hash)
        self.assertEqual(len(file_hash), 32)
        
if __name__ == '__main__':
    unittest.main()