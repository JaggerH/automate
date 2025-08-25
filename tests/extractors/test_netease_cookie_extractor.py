#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NetEase Cookie Extractor 测试模块

测试NetEase cookie提取功能：
1. 从模拟请求/响应中提取关键cookies
2. 验证cookie格式化输出为JSON
3. 验证多用户cookie分别保存
4. 验证JSON文件结构和内容正确性

测试数据包含：
- MUSIC_U: 用户身份标识（Base64编码的JSON）
- __csrf: CSRF令牌
- NMTID: 设备ID
- WEVNSM: 会话标识
"""

import sys
import json
import unittest
import tempfile
import base64
from pathlib import Path
from unittest.mock import Mock, patch

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
    def __init__(self, cookies=None, response_cookies=None, url="https://music.163.com/eapi/user/level"):
        self.request = Mock()
        self.response = Mock()
        self.metadata = {}
        
        # 设置请求属性
        self.request.pretty_url = url
        self.request.path = "/eapi/user/level"
        self.request.host = "music.163.com"
        self.request.method = "POST"
        
        # 设置cookies
        if cookies:
            # 模拟cookies字典
            cookie_items = MockCookieDict(cookies)
            self.request.cookies = cookie_items
        else:
            self.request.cookies = MockCookieDict({})
            
        if response_cookies:
            response_cookie_items = MockCookieDict(response_cookies)
            self.response.cookies = response_cookie_items
        else:
            self.response.cookies = MockCookieDict({})
        
        # 设置headers
        self.request.headers = {}
        self.response.headers = {}


class MockCookieDict:
    """模拟 mitmproxy 的 cookie 字典"""
    def __init__(self, cookies):
        self._cookies = cookies
    
    def items(self):
        return self._cookies.items()
    
    def get(self, key, default=None):
        return self._cookies.get(key, default)
    
    def __contains__(self, key):
        return key in self._cookies
    
    def __getitem__(self, key):
        return self._cookies[key]


class TestNeteaseCookieExtractor(unittest.TestCase):
    """NetEase Cookie提取器测试"""
    
    def setUp(self):
        """测试初始化"""
        # 创建临时目录用于输出测试
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        
        # 配置NetEase extractor - 启用cookie提取，禁用播放列表功能
        self.extractor_config = {
            'domains': [
                "music.163.com",
                "interface.music.163.com", 
                "interface3.music.163.com"
            ],
            'features': {
                'extract_cookie': {
                    'enabled': True,
                    'interval': 0,  # 测试时禁用频率限制
                    'output_file': str(self.temp_path / 'auto_cookie.json')
                },
                'extract_playlist': {
                    'enabled': False  # 禁用播放列表提取
                }
            }
        }
        
        # 创建提取器实例
        self.extractor = NeteaseExtractor(self.extractor_config)
        
        # 创建测试用的cookie数据
        self.test_user_data = {
            "userId": 123456789,
            "exp": 1640995200  # 2022-01-01
        }
        
        # Base64编码用户数据作为MUSIC_U
        user_data_json = json.dumps(self.test_user_data)
        self.music_u_value = base64.b64encode(user_data_json.encode('utf-8')).decode('utf-8')
        
        self.test_cookies = {
            'MUSIC_U': self.music_u_value,
            '__csrf': 'csrf_token_123456',
            'NMTID': 'device_id_abcdef',
            'WEVNSM': 'session_id_xyz789',
            '__remember_me': 'true',
            'other_cookie': 'should_be_filtered_out'
        }
    
    def tearDown(self):
        """测试清理"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_cookie_extraction_from_request(self):
        """测试从请求中提取cookie"""
        # 创建包含cookies的mock flow
        flow = MockFlow(cookies=self.test_cookies)
        
        # 提取cookie
        cookies = {k: str(v) for k, v in flow.request.cookies.items()}
        headers = {}
        
        extracted_cookies = self.extractor.extract_from_request(cookies, headers, flow.request.pretty_url)
        
        # 验证提取结果
        self.assertIsNotNone(extracted_cookies, "应该成功提取cookie")
        self.assertIn('MUSIC_U', extracted_cookies, "应该包含MUSIC_U")
        self.assertIn('__csrf', extracted_cookies, "应该包含__csrf")
        self.assertNotIn('other_cookie', extracted_cookies, "不应该包含无关cookie")
        
        print(f"成功从请求提取 {len(extracted_cookies)} 个关键cookie")
    
    def test_cookie_extraction_from_response(self):
        """测试从响应中提取cookie"""
        # 创建包含response cookies的mock flow
        flow = MockFlow(response_cookies=self.test_cookies)
        
        # 提取cookie
        cookies = {k: str(v) for k, v in flow.response.cookies.items()}
        headers = {}
        
        extracted_cookies = self.extractor.extract_from_response(cookies, headers, flow.request.pretty_url)
        
        # 验证提取结果
        self.assertIsNotNone(extracted_cookies, "应该成功提取cookie")
        self.assertIn('MUSIC_U', extracted_cookies, "应该包含MUSIC_U")
        
        print(f"成功从响应提取 {len(extracted_cookies)} 个关键cookie")
    
    def test_user_id_extraction_from_music_u(self):
        """测试从MUSIC_U中提取用户ID"""
        user_id = self.extractor._extract_user_id_from_music_u(self.music_u_value)
        
        self.assertEqual(user_id, str(self.test_user_data['userId']), "应该正确解析用户ID")
        print(f"成功从MUSIC_U解析用户ID: {user_id}")
    
    def test_cookie_format_output(self):
        """测试cookie格式化输出"""
        formatted = self.extractor.format_cookie_output(self.test_cookies)
        
        # 验证输出结构
        required_fields = ['cookie', 'timestamp', 'profile', 'account', 'user_id', 'loginTime']
        for field in required_fields:
            self.assertIn(field, formatted, f"输出应该包含{field}字段")
        
        # 验证cookie字符串格式
        cookie_string = formatted['cookie']
        self.assertIsInstance(cookie_string, str, "cookie应该是字符串")
        self.assertIn('MUSIC_U=', cookie_string, "cookie字符串应该包含MUSIC_U")
        self.assertIn('; ', cookie_string, "cookie字符串应该用分号分隔")
        
        # 验证用户ID
        self.assertEqual(formatted['user_id'], str(self.test_user_data['userId']), "用户ID应该匹配")
        self.assertEqual(str(formatted['account']['id']), str(self.test_user_data['userId']), "账户ID应该匹配")
        
        print(f"Cookie格式化输出验证通过，包含用户ID: {formatted['user_id']}")
    
    def test_cookie_json_file_output(self):
        """测试cookie保存为JSON文件"""
        # 模拟cookie提取和保存过程
        flow = MockFlow(cookies=self.test_cookies)
        
        # 手动触发提取和保存
        cookies = {k: str(v) for k, v in flow.request.cookies.items()}
        headers = {}
        
        extracted_cookies = self.extractor.extract_from_request(cookies, headers, flow.request.pretty_url)
        self.assertIsNotNone(extracted_cookies, "cookie提取应该成功")
        
        # 保存cookie
        self.extractor._save_cookie_data(extracted_cookies)
        
        # 验证多用户模式文件（因为提供了user_id）
        expected_file = self.temp_path / f"cookie_{self.test_user_data['userId']}.json"
        self.assertTrue(expected_file.exists(), f"多用户cookie文件应该存在: {expected_file}")
        
        # 验证JSON文件内容
        with open(expected_file, 'r', encoding='utf-8') as f:
            saved_data = json.load(f)
        
        # 验证JSON结构
        required_fields = ['cookie', 'timestamp', 'profile', 'account', 'user_id', 'loginTime']
        for field in required_fields:
            self.assertIn(field, saved_data, f"JSON应该包含{field}字段")
        
        # 验证数据类型
        self.assertIsInstance(saved_data['cookie'], str, "cookie字段应该是字符串")
        self.assertIsInstance(saved_data['timestamp'], int, "timestamp字段应该是整数")
        self.assertIsInstance(saved_data['loginTime'], int, "loginTime字段应该是整数")
        self.assertIsInstance(saved_data['profile'], dict, "profile字段应该是字典")
        self.assertIsInstance(saved_data['account'], dict, "account字段应该是字典")
        
        # 验证cookie内容
        cookie_string = saved_data['cookie']
        self.assertIn('MUSIC_U=', cookie_string, "保存的cookie应该包含MUSIC_U")
        self.assertIn('__csrf=', cookie_string, "保存的cookie应该包含__csrf")
        
        # 验证用户信息
        self.assertEqual(saved_data['user_id'], str(self.test_user_data['userId']), "保存的用户ID应该匹配")
        self.assertEqual(str(saved_data['account']['id']), str(self.test_user_data['userId']), "保存的账户ID应该匹配")
        
        print(f"JSON文件输出验证通过: {expected_file}")
        print(f"保存的cookie长度: {len(cookie_string)} 字符")
        print(f"用户ID: {saved_data['user_id']}")
    
    def test_cookie_validation(self):
        """测试cookie有效性验证"""
        # 测试有效cookie
        valid_cookies = {'MUSIC_U': 'valid_token'}
        self.assertTrue(self.extractor.is_valid_cookie(valid_cookies), "有效cookie应该通过验证")
        
        # 测试无效cookie
        invalid_cookies_list = [
            {},  # 空cookie
            {'other': 'value'},  # 没有MUSIC_U
            {'MUSIC_U': ''},  # MUSIC_U为空
            {'MUSIC_U': None}  # MUSIC_U为None
        ]
        
        for invalid_cookies in invalid_cookies_list:
            self.assertFalse(self.extractor.is_valid_cookie(invalid_cookies), 
                           f"无效cookie应该被拒绝: {invalid_cookies}")
        
        print("Cookie有效性验证通过")
    
    def test_key_cookie_filtering(self):
        """测试关键cookie过滤"""
        mixed_cookies = {
            'MUSIC_U': 'user_token',
            '__csrf': 'csrf_token',
            'NMTID': 'device_id',
            'irrelevant_cookie': 'should_be_filtered',
            'tracking_pixel': 'also_filtered',
            'MUSIC_A': 'another_music_cookie',  # 以MUSIC_开头的应该保留
            '__session': 'session_token'  # 以__开头的应该保留
        }
        
        extracted = self.extractor._extract_netease_cookies(mixed_cookies, 'test', 'test_url')
        
        # 验证保留的cookie
        expected_cookies = ['MUSIC_U', '__csrf', 'NMTID', 'MUSIC_A', '__session']
        for cookie in expected_cookies:
            self.assertIn(cookie, extracted, f"应该保留关键cookie: {cookie}")
        
        # 验证过滤的cookie
        filtered_cookies = ['irrelevant_cookie', 'tracking_pixel']
        for cookie in filtered_cookies:
            self.assertNotIn(cookie, extracted, f"应该过滤无关cookie: {cookie}")
        
        print(f"Cookie过滤验证通过，保留 {len(extracted)} 个关键cookie")
    
    def test_malformed_music_u_handling(self):
        """测试处理格式错误的MUSIC_U"""
        malformed_values = [
            'invalid_base64',
            'dGVzdA==',  # 有效base64但不是JSON
            base64.b64encode(b'{"invalid": "json"').decode(),  # 无效JSON
            base64.b64encode(b'{"no_userId": 123}').decode()  # 缺少userId字段
        ]
        
        for malformed_value in malformed_values:
            user_id = self.extractor._extract_user_id_from_music_u(malformed_value)
            self.assertIsNone(user_id, f"格式错误的MUSIC_U应该返回None: {malformed_value}")
        
        print("格式错误MUSIC_U处理验证通过")
    
    def test_single_user_mode_fallback(self):
        """测试单用户模式回退（当无法解析用户ID时）"""
        # 创建不包含有效MUSIC_U的cookies
        cookies_without_user_id = {
            '__csrf': 'csrf_token',
            'NMTID': 'device_id',
            'MUSIC_U': 'invalid_music_u'  # 无效的MUSIC_U
        }
        
        # 保存这些cookies应该使用默认文件名
        self.extractor._save_cookie_data(cookies_without_user_id)
        
        # 验证默认文件被创建
        default_file = self.temp_path / 'auto_cookie.json'
        self.assertTrue(default_file.exists(), "应该创建默认cookie文件")
        
        # 验证文件内容
        with open(default_file, 'r', encoding='utf-8') as f:
            saved_data = json.load(f)
        
        # 用户ID应该为None
        self.assertIsNone(saved_data['user_id'], "无法解析用户ID时应该为None")
        
        print("单用户模式回退验证通过")


def run_tests():
    """运行测试"""
    print("NetEase Cookie Extractor 测试")
    print("=" * 60)
    
    # 创建测试套件
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestNeteaseCookieExtractor)
    
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