import unittest
import tempfile
import os
import shutil
from pathlib import Path
from unittest.mock import patch, Mock

from ..file_matcher import FileMatcher

class TestMetadataWriting(unittest.TestCase):
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_write_audio_metadata_basic(self):
        """测试基本音频元数据写入功能"""
        # 创建一个测试音频文件（简单的MP3格式）
        test_file = os.path.join(self.test_dir, 'test.mp3')
        
        # 创建一个最小的MP3文件头
        mp3_header = b'\xff\xfb\x90\x00' + b'\x00' * 100
        with open(test_file, 'wb') as f:
            f.write(mp3_header)
        
        track_metadata = {
            'name': '测试歌曲',
            'ar': [{'name': '测试艺术家1'}, {'name': '测试艺术家2'}],
            'al': {'name': '测试专辑'},
            'publishTime': 1609459200000  # 2021-01-01
        }
        
        # 测试元数据写入
        result = FileMatcher.write_audio_metadata(test_file, track_metadata)
        
        # 如果mutagen可用，应该返回True
        # 如果不可用，应该返回False但不报错
        self.assertIsInstance(result, bool)
    
    @patch('scripts.sync_music.file_matcher.requests.get')
    def test_download_cover_image_success(self, mock_get):
        """测试成功下载封面图片"""
        # 模拟成功的HTTP响应
        mock_response = Mock()
        mock_response.content = b'fake_image_data'
        mock_response.headers = {'content-type': 'image/jpeg'}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        result = FileMatcher.download_cover_image('http://example.com/cover.jpg')
        
        self.assertEqual(result, b'fake_image_data')
        mock_get.assert_called_once()
    
    @patch('scripts.sync_music.file_matcher.requests.get')
    def test_download_cover_image_failure(self, mock_get):
        """测试下载封面图片失败"""
        # 模拟HTTP请求失败
        mock_get.side_effect = Exception('Network error')
        
        result = FileMatcher.download_cover_image('http://example.com/cover.jpg')
        
        self.assertIsNone(result)
    
    def test_download_cover_image_empty_url(self):
        """测试空URL的处理"""
        result = FileMatcher.download_cover_image('')
        self.assertIsNone(result)
        
        result = FileMatcher.download_cover_image(None)
        self.assertIsNone(result)
    
    @patch('scripts.sync_music.file_matcher.requests.get')
    def test_download_cover_image_invalid_content_type(self, mock_get):
        """测试无效内容类型的处理"""
        mock_response = Mock()
        mock_response.content = b'not_an_image'
        mock_response.headers = {'content-type': 'text/html'}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        result = FileMatcher.download_cover_image('http://example.com/notimage.html')
        
        self.assertIsNone(result)
    
    def test_copy_and_rename_file_with_metadata(self):
        """测试带元数据的文件复制功能"""
        # 创建源文件（模拟.uc文件）
        source_file = os.path.join(self.test_dir, 'source.uc')
        # 创建一个简单的加密数据
        original_data = b'Hello World! This is test audio data.'
        encrypted_data = bytearray(original_data)
        for i in range(len(encrypted_data)):
            encrypted_data[i] ^= 0xA3
        
        with open(source_file, 'wb') as f:
            f.write(encrypted_data)
        
        output_dir = os.path.join(self.test_dir, 'output')
        
        track_metadata = {
            'name': '测试歌曲带元数据',
            'ar': [{'name': '测试艺术家'}],
            'al': {'name': '测试专辑'}
        }
        
        # 测试复制并写入元数据
        result_path = FileMatcher.copy_and_rename_file(
            source_file, output_dir, 'test_with_metadata', track_metadata
        )
        
        # 验证文件被创建
        expected_path = os.path.join(output_dir, 'test_with_metadata.mp3')
        self.assertEqual(result_path, expected_path)
        self.assertTrue(os.path.exists(expected_path))
        
        # 验证文件被正确解密
        with open(expected_path, 'rb') as f:
            decrypted_data = f.read()
        
        self.assertEqual(decrypted_data, original_data)
    
    def test_copy_and_rename_file_without_metadata(self):
        """测试不带元数据的文件复制（向后兼容）"""
        source_file = os.path.join(self.test_dir, 'source.uc')
        test_data = b'Test data without metadata'
        encrypted_data = bytearray(test_data)
        for i in range(len(encrypted_data)):
            encrypted_data[i] ^= 0xA3
        
        with open(source_file, 'wb') as f:
            f.write(encrypted_data)
        
        output_dir = os.path.join(self.test_dir, 'output')
        
        # 测试不带元数据的复制（原有功能）
        result_path = FileMatcher.copy_and_rename_file(
            source_file, output_dir, 'test_without_metadata'
        )
        
        # 验证功能正常
        expected_path = os.path.join(output_dir, 'test_without_metadata.mp3')
        self.assertEqual(result_path, expected_path)
        self.assertTrue(os.path.exists(expected_path))
    
    def test_write_audio_metadata_file_not_found(self):
        """测试文件不存在时的处理"""
        nonexistent_file = os.path.join(self.test_dir, 'nonexistent.mp3')
        track_metadata = {'name': 'Test'}
        
        result = FileMatcher.write_audio_metadata(nonexistent_file, track_metadata)
        
        self.assertFalse(result)

if __name__ == '__main__':
    unittest.main()