#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NetEase Extractor 测试模块

测试分步获取playlist数据的合并逻辑：
1. 从 data/debug/ 中读取已解密的实际数据
2. 模拟 playlist 和 songs 的分步处理流程
3. 验证合并逻辑的正确性

测试数据来源：
- post_request_5_*.json - playlist/v4/detail API (获取播放列表基本信息)
- post_request_7_*.json - v3/song/detail API (获取歌曲详情列表)
"""

import sys
import json
import unittest
from pathlib import Path
from unittest.mock import Mock, MagicMock

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 导入被测试的模块
try:
    from src.extractors.netease_extractor import NeteaseExtractor
except ImportError as e:
    print(f"导入失败: {e}")
    sys.exit(1)


class MockFlow:
    """模拟 mitmproxy 的 flow 对象"""
    def __init__(self, data=None):
        self.request = Mock()
        self.response = Mock()
        self.metadata = {}  # 添加metadata属性
        
        if data:
            self._load_data(data)
    
    def _load_data(self, data):
        """从测试数据加载到flow对象中"""
        # 设置 request 属性
        self.request.pretty_url = data.get('url', '')
        self.request.method = data.get('method', 'POST')
        self.request.host = data.get('domain', '')
        self.request.path = data.get('path', '')
        
        # 设置 request headers
        headers = data.get('headers', {})
        self.request.headers = headers
        
        # 设置 request content (payload)
        payload = data.get('payload', '')
        if isinstance(payload, str):
            self.request.content = payload.encode('utf-8')
        else:
            self.request.content = str(payload).encode('utf-8')
        
        # 设置 response 属性
        response_data = data.get('response', {})
        self.response.status_code = response_data.get('status_code', 200)
        self.response.headers = response_data.get('headers', {})
        
        # 设置 response content
        response_content = response_data.get('content', '')
        if isinstance(response_content, str):
            self.response.content = response_content.encode('utf-8')
        elif isinstance(response_content, dict):
            # 如果是dict，转换为JSON字符串
            import json
            self.response.content = json.dumps(response_content, ensure_ascii=False).encode('utf-8')
        else:
            self.response.content = str(response_content).encode('utf-8')
    
    @classmethod
    def create_playlist_flow(cls, test_data):
        """创建播放列表请求的flow对象"""
        playlist_data = test_data.get('playlist_step')
        if playlist_data:
            return cls(playlist_data)
        return None
    
    @classmethod  
    def create_songs_flow(cls, test_data):
        """创建歌曲请求的flow对象"""
        songs_data = test_data.get('songs_step')
        if songs_data:
            return cls(songs_data)
        return None


class TestNeteaseExtractor(unittest.TestCase):
    """NetEase提取器集成测试"""
    
    @classmethod
    def setUpClass(cls):
        """测试类初始化 - 加载测试数据"""
        cls.mock_data_dir = project_root / "tests" / "extractors" / "mock_data"
        cls.test_data = cls._load_test_data()
        
    @classmethod
    def _load_test_data(cls):
        """加载并解析测试数据"""
        # 定义测试文件路径
        files = {
            'playlist_step': cls.mock_data_dir / "post_ne_playlist_step_1.json",
            'songs_step': cls.mock_data_dir / "post_ne_playlist_step_2.json"
        }
        
        result = {}
        for key, file in files.items():
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 恢复原始字段结构：将解密的payload和response.content保存到_raw字段，原始加密数据恢复到主字段
                if 'payload_raw' in data and 'payload' in data:
                    # 保存解密的payload为payload_decrypted
                    data['payload_decrypted'] = data['payload']
                    # 恢复原始加密的payload
                    data['payload'] = data['payload_raw']
                
                if 'response' in data and isinstance(data['response'], dict):
                    response = data['response']
                    if 'content_raw' in response and 'content' in response:
                        # 保存解密的content为content_decrypted
                        response['content_decrypted'] = response['content']
                        # 恢复原始加密的content
                        response['content'] = response['content_raw']
                
                result[key] = data
                
            except Exception as e:
                print(f"ERROR: 加载 {key} 数据失败: {e}")
                result[key] = None
                
        return result
    
    def test_flow_mock_data(self):
        """测试MockFlow能像真实flow一样使用"""
        # 创建 playlist flow 对象
        playlist_flow = MockFlow.create_playlist_flow(self.test_data)
        self.assertIsNotNone(playlist_flow, "应该能创建playlist flow对象")
        
        # 测试 flow.request.pretty_url
        playlist_url = playlist_flow.request.pretty_url
        self.assertIsNotNone(playlist_url, "flow.request.pretty_url应该可用")
        self.assertIn("/eapi/playlist/v4/detail", playlist_url, "应该是播放列表详情API")
        
        # 测试 flow.response.content
        playlist_response_content = playlist_flow.response.content
        self.assertIsNotNone(playlist_response_content, "flow.response.content应该可用")
        self.assertIsInstance(playlist_response_content, bytes, "flow.response.content应该是bytes类型")
        
        # 创建 songs flow 对象
        songs_flow = MockFlow.create_songs_flow(self.test_data)
        self.assertIsNotNone(songs_flow, "应该能创建songs flow对象")
        
        # 测试 flow.request.pretty_url
        songs_url = songs_flow.request.pretty_url
        self.assertIsNotNone(songs_url, "flow.request.pretty_url应该可用")
        self.assertIn("/eapi/v3/song/detail", songs_url, "应该是歌曲详情API")
        
        # 测试 flow.response.content
        songs_response_content = songs_flow.response.content
        self.assertIsNotNone(songs_response_content, "flow.response.content应该可用")
        self.assertIsInstance(songs_response_content, bytes, "flow.response.content应该是bytes类型")
        
    def test_step_playlist_load(self):
        """测试分步播放列表数据加载"""
        # 创建 flow 对象
        playlist_flow = MockFlow.create_playlist_flow(self.test_data)
        songs_flow = MockFlow.create_songs_flow(self.test_data)
        
        self.assertIsNotNone(playlist_flow, "playlist_flow 应该创建成功")
        self.assertIsNotNone(songs_flow, "songs_flow 应该创建成功")
        
        # 配置 NetEase extractor - 禁用 cookie 提取，启用播放列表功能
        extractor_config = {
            'domains': [
                "music.163.com",
                "interface.music.163.com",
                "interface3.music.163.com",
                "api.music.163.com",
                "mam.netease.com",
                "clientlog.music.163.com",
                "httpdns.n.netease.com",
                "163.com"
            ],
            'features': {
                'extract_cookies': {
                    'enabled': False  # 禁用 cookie 提取器
                },
                'extract_playlist': {
                    'enabled': True,  # 启用播放列表提取
                    'target_ids': ['60567077'],  # 测试播放列表ID
                    'output_dir': str(project_root / 'tests' / 'extractors' / 'outputs' / 'playlists')
                }
            }
        }
        
        # 初始化 NetEase extractor 实例
        extractor = NeteaseExtractor(extractor_config)
        
        # 配置Mock crypto来模拟解密行为
        mock_crypto = Mock()
        
        # 配置解密返回 - 根据不同调用返回不同数据
        def mock_decrypt(hex_content):
            # 根据调用次数或内容返回不同的解密结果
            if not hasattr(mock_decrypt, 'call_count'):
                mock_decrypt.call_count = 0
            
            mock_decrypt.call_count += 1
            
            if mock_decrypt.call_count == 1:
                # 第一次调用：返回playlist数据
                playlist_content = self.test_data['playlist_step'].get('response', {}).get('content_decrypted')
                if playlist_content:
                    return {
                        'success': True,
                        'data': json.dumps(playlist_content, ensure_ascii=False)
                    }
            else:
                # 后续调用：返回songs数据
                songs_content = self.test_data['songs_step'].get('response', {}).get('content_decrypted')
                if songs_content:
                    return {
                        'success': True,
                        'data': json.dumps(songs_content, ensure_ascii=False)
                    }
            
            return {'success': False, 'error': 'Mock解密失败'}
        
        mock_crypto.eapi_decrypt.side_effect = mock_decrypt
        
        extractor.crypto = mock_crypto
        
        # 第1步：处理playlist响应（V4分步模式）
        print("\n=== 第1步：处理播放列表响应 ===")
        playlist_result = extractor._extract_playlist_from_response(playlist_flow)
        self.assertIsNotNone(playlist_result, "播放列表响应提取结果不应为空")
        self.assertIn("60567077", extractor.playlist_state.track_ids_cache, "应该保存播放列表的trackIds")
        self.assertIn("60567077", extractor.playlist_state.pending_data, "应该保存等待合并的播放列表数据")
        print(f"SUCCESS: 播放列表trackIds已保存，共{len(extractor.playlist_state.track_ids_cache['60567077'])}个ID")
        playlist_ids = extractor.playlist_state.track_ids_cache['60567077'][:5]  # 前5个ID用于调试
        print(f"         前5个playlist trackIDs: {playlist_ids}")
        
        # 第2步：处理songs响应（V4分步模式 - 合并）
        print("\n=== 第2步：处理歌曲响应并合并 ===")
        
        # 模拟songs请求中的song_ids（从songs flow的解密数据中提取）
        songs_payload_decrypted = self.test_data['songs_step'].get('payload_decrypted', {})
        if 'c' in songs_payload_decrypted:
            c_raw = songs_payload_decrypted['c']
            try:
                c_data = json.loads(c_raw) if isinstance(c_raw, str) else c_raw
                # 统一转换为整数类型，与playlist的trackIds保持一致
                song_ids = []
                for item in c_data:
                    if isinstance(item, dict) and 'id' in item:
                        song_id = item['id']
                        if isinstance(song_id, str) and song_id.isdigit():
                            song_ids.append(int(song_id))
                        elif isinstance(song_id, int):
                            song_ids.append(song_id)
                songs_flow.metadata['song_ids'] = song_ids
                print(f"模拟songs请求包含{len(song_ids)}个歌曲ID")
                print(f"         前5个songs IDs: {song_ids[:5]}")  # 前5个ID用于调试
            except:
                songs_flow.metadata['song_ids'] = []
        
        songs_result = extractor._extract_playlist_from_response(songs_flow)
        self.assertIsNotNone(songs_result, "歌曲响应提取结果不应为空")
        
        # 验证合并是否成功
        if songs_result and 'playlist' in songs_result:
            merged_tracks = songs_result['playlist'].get('tracks', [])
            print(f"SUCCESS: 合并完成，最终包含{len(merged_tracks)}首歌曲")
        else:
            print("INFO: songs数据处理完成，等待进一步处理")
            
        # 验证清理状态
        print(f"待合并状态: pending_data有{len(extractor.playlist_state.pending_data)}项")
        print(f"trackIds状态: track_ids_cache有{len(extractor.playlist_state.track_ids_cache)}项")
        
        # 验证文件输出
        print("\n=== 验证文件输出 ===")
        
        # 从配置中获取实际的输出目录
        playlist_config = extractor.playlist_config
        output_dir = Path(playlist_config.get('output_dir', ''))
        playlist_id = "60567077"
        expected_output_file = output_dir / f"playlist_{playlist_id}.json"
        
        print(f"配置的输出目录: {output_dir}")
        print(f"预期输出文件: {expected_output_file}")
        
        # 验证输出目录存在
        self.assertTrue(output_dir.exists(), f"输出目录应该存在: {output_dir}")
        print(f"SUCCESS: 输出目录存在")
        
        # 验证输出文件存在
        self.assertTrue(expected_output_file.exists(), f"播放列表文件应该存在: {expected_output_file}")
        print(f"SUCCESS: 播放列表文件存在")
        
        # 验证文件内容
        with open(expected_output_file, 'r', encoding='utf-8') as f:
            saved_data = json.load(f)
        
        self.assertIn('playlist', saved_data, "文件应该包含playlist数据")
        
        saved_tracks = saved_data.get('playlist', {}).get('tracks', [])
        saved_playlist_id = str(saved_data.get('playlist', {}).get('id', ''))
        saved_name = saved_data.get('playlist', {}).get('name', 'N/A')
        
        print(f"SUCCESS: 文件内容验证通过")
        print(f"         播放列表: {saved_name} (ID: {saved_playlist_id})")
        print(f"         包含{len(saved_tracks)}首歌曲")
        
        # 验证数据完整性
        self.assertEqual(saved_playlist_id, playlist_id, "保存的播放列表ID应该匹配")
        self.assertGreater(len(saved_tracks), 0, "保存的播放列表应该包含歌曲")
        
        if len(saved_tracks) > 0:
            first_track = saved_tracks[0]
            print(f"         第一首歌: {first_track.get('name', 'N/A')} (ID: {first_track.get('id', 'N/A')})")
            self.assertIn('name', first_track, "歌曲应该包含name字段")
            self.assertIn('id', first_track, "歌曲应该包含id字段")

def run_tests():
    """运行测试"""
    print("NetEase Extractor 集成测试")
    print("=" * 60)
    
    # 创建测试套件
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestNeteaseExtractor)
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 输出结果
    print(f"\n" + "=" * 60)
    print(f"测试完成")
    print(f"运行: {result.testsRun}")
    print(f"失败: {len(result.failures)}")
    print(f"错误: {len(result.errors)}")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)