import unittest
import tempfile
import os
import shutil
import yaml
from unittest.mock import patch, Mock

from ..config import ConfigLoader, SyncConfig

class TestSyncConfig(unittest.TestCase):
    
    def test_default_config(self):
        """测试默认配置"""
        config = SyncConfig()
        
        self.assertEqual(config.database_path, "music_sync.db")
        self.assertEqual(config.supported_extensions, ['.mp3', '.flac'])
        self.assertTrue(config.max_bitrate_preference)
        self.assertTrue(config.verbose)
        self.assertEqual(config.batch_size, 100)

class TestConfigLoader(unittest.TestCase):
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_file = os.path.join(self.test_dir, 'test_config.yaml')
    
    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_load_config_from_file(self):
        """测试从文件加载配置"""
        config_data = {
            'user_dir': '/test/user',
            'input_dir': '/test/input',
            'output_dir': '/test/output',
            'database_path': 'test.db',
            'verbose': False,
            'batch_size': 50
        }
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            yaml.dump(config_data, f)
        
        config = ConfigLoader.load_config(self.config_file)
        
        self.assertEqual(config.user_dir, '/test/user')
        self.assertEqual(config.input_dir, '/test/input')
        self.assertEqual(config.output_dir, '/test/output')
        self.assertEqual(config.database_path, 'test.db')
        self.assertFalse(config.verbose)
        self.assertEqual(config.batch_size, 50)
    
    def test_load_config_with_multiple_user_dirs(self):
        """测试加载包含多个用户目录的配置"""
        config_data = {
            'user_dir': ['/test/user1', '/test/user2', '/test/user3'],
            'input_dir': '/test/input',
            'output_dir': '/test/output',
            'database_path': 'test.db'
        }
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            yaml.dump(config_data, f)
        
        config = ConfigLoader.load_config(self.config_file)
        
        self.assertIsInstance(config.user_dir, list)
        self.assertEqual(len(config.user_dir), 3)
        self.assertEqual(config.user_dir[0], '/test/user1')
        self.assertEqual(config.user_dir[1], '/test/user2')
        self.assertEqual(config.user_dir[2], '/test/user3')
    
    def test_load_config_nonexistent_file(self):
        """测试加载不存在的配置文件"""
        with self.assertRaises(FileNotFoundError):
            ConfigLoader.load_config('/nonexistent/config.yaml')
    
    def test_load_config_invalid_yaml(self):
        """测试加载无效的YAML文件"""
        with open(self.config_file, 'w') as f:
            f.write("invalid: yaml: content:\n  - broken")
        
        with self.assertRaises(ValueError):
            ConfigLoader.load_config(self.config_file)
    
    def test_expand_env_vars(self):
        """测试环境变量展开"""
        config_data = {
            'user_dir': '$HOME/Music',
            'database_path': '${HOME}/music.db'
        }
        
        with patch.dict(os.environ, {'HOME': '/home/testuser'}):
            expanded = ConfigLoader._expand_env_vars(config_data)
            
            self.assertEqual(expanded['user_dir'], '/home/testuser/Music')
            self.assertEqual(expanded['database_path'], '/home/testuser/music.db')
    
    def test_create_default_config(self):
        """测试创建默认配置文件"""
        config_path = os.path.join(self.test_dir, 'default_config.yaml')
        
        ConfigLoader.create_default_config(config_path)
        
        self.assertTrue(os.path.exists(config_path))
        
        # 验证创建的配置文件可以正常加载
        with open(config_path, 'r', encoding='utf-8') as f:
            loaded_data = yaml.safe_load(f)
        
        self.assertIn('user_dir', loaded_data)
        self.assertIn('input_dir', loaded_data)
        self.assertIn('output_dir', loaded_data)
        self.assertIn('supported_extensions', loaded_data)
    
    def test_merge_config_with_args(self):
        """测试配置与命令行参数合并"""
        config = SyncConfig(
            user_dir='/config/user',
            input_dir='/config/input',
            database_path='config.db'
        )
        
        # 模拟命令行参数
        args = Mock()
        args.user_dir = '/args/user'
        args.input_dir = None
        args.output_dir = '/args/output'
        args.json_file = 'args.json'
        args.json_dir = None
        args.database = 'args.db'
        args.verbose = True
        
        merged_config = ConfigLoader.merge_config_with_args(config, args)
        
        # 命令行参数应该覆盖配置文件
        self.assertEqual(merged_config.user_dir, '/args/user')
        self.assertEqual(merged_config.input_dir, '/config/input')  # 保持原值
        self.assertEqual(merged_config.output_dir, '/args/output')
        self.assertEqual(merged_config.json_file, 'args.json')
        self.assertEqual(merged_config.database_path, 'args.db')
        self.assertTrue(merged_config.verbose)
    
    def test_get_database_url(self):
        """测试获取数据库URL"""
        # 测试使用database_path
        config1 = SyncConfig(database_path='test.db')
        url1 = ConfigLoader.get_database_url(config1)
        self.assertEqual(url1, 'sqlite:///test.db')
        
        # 测试使用database_url
        config2 = SyncConfig(
            database_path='test.db',
            database_url='postgresql://user:pass@localhost/db'
        )
        url2 = ConfigLoader.get_database_url(config2)
        self.assertEqual(url2, 'postgresql://user:pass@localhost/db')
    
    def test_load_config_default_paths(self):
        """测试默认路径加载配置"""
        # 模拟没有找到任何配置文件的情况
        with patch('os.path.exists', return_value=False):
            config = ConfigLoader.load_config()
            
            # 应该返回默认配置
            self.assertEqual(config.database_path, "music_sync.db")
            self.assertTrue(config.verbose)
    
    def test_validate_config_warnings(self):
        """测试配置验证警告"""
        config_data = {
            'user_dir': '/nonexistent/user',
            'input_dir': '/nonexistent/input',
            'output_dir': '/test/output'
        }
        
        with patch('os.path.exists', return_value=False):
            with patch('builtins.print') as mock_print:
                ConfigLoader._validate_config(config_data)
                
                # 应该有警告信息
                mock_print.assert_called()
                
if __name__ == '__main__':
    unittest.main()