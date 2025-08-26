#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NetEase Extractor 测试模块

测试分步获取playlist数据的合并逻辑：
1. 从 data/debug/ 中读取已解密的实际数据
2. 模拟 playlist 和 songs 的分步处理流程
3. 验证合并逻辑的正确性

测试数据来源：
- playlist/v4/detail API (获取播放列表基本信息)
- v3/song/detail API (获取歌曲详情列表)
"""

import sys
import json
import unittest
from pathlib import Path
from unittest.mock import Mock, MagicMock

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
playlist_output_dir = str(project_root) + "/src/tests/extractors/outputs/playlists"
cookie_output_dir = str(project_root) + "/src/tests/extractors/outputs/cookies"
mock_data_dir = str(project_root) + "/src/tests/extractors/mock_data"
sys.path.insert(0, str(project_root))

from src.utils.flow_reproducer import FlowReproducer
from src.extractors.netease_extractor import NeteaseExtractor
from src.utils.config_loader import config_loader

class StepPlaylistFlowReproducer(FlowReproducer):
    def create_extractor(self):
        # 获取netease服务的默认配置
        services_config = config_loader.get_services_config()
        netease_config = services_config['services']['netease'].copy()
        
        # 配置参数
        netease_config['features']['extract_cookie']['enabled'] = False  # 禁用 cookie 提取
        netease_config['features']['extract_playlist']['enabled'] = True  # 启用播放列表提取
        netease_config['features']['extract_playlist']['target_ids'] = ['60567077']  # 测试播放列表ID
        netease_config['features']['extract_playlist']['output_dir'] = playlist_output_dir
        
        extractor_config = netease_config
        
        # 初始化 NetEase extractor 实例
        extractor = NeteaseExtractor(extractor_config)
        
        return extractor
    
class CookieFlowReproducer(FlowReproducer):
    def create_extractor(self):
        # 获取netease服务的默认配置
        services_config = config_loader.get_services_config()
        netease_config = services_config['services']['netease'].copy()
        
        # 配置参数
        netease_config['features']['extract_cookie']['enabled'] = True  # 禁用 cookie 提取
        netease_config['features']['extract_cookie']['output_dir'] = cookie_output_dir
        netease_config['features']['extract_playlist']['enabled'] = False  # 禁用播放列表提取
        
        extractor_config = netease_config
        
        # 初始化 NetEase extractor 实例
        extractor = NeteaseExtractor(extractor_config)
        
        return extractor

class TestNeteaseExtractor(unittest.TestCase):
    """NetEase提取器集成测试"""
    
    def test_step_playlist_extract(self):
        """测试分步播放列表数据抽取"""
        output_file = Path(playlist_output_dir) / 'playlist_60567077.json'
        try:
            netease_fr = StepPlaylistFlowReproducer(mock_data_dir + "/step_playlist")
            netease_fr.reproduce_all_flows()
            self.assertTrue(output_file.exists(), f"输出文件不存在: {output_file}")
        finally:
            if output_file.exists():
                output_file.unlink()
            dirpath = Path(playlist_output_dir)
            if dirpath.exists() and dirpath.is_dir():
                dirpath.rmdir()
                
    def test_cookie_extract(self):
        output_file = Path(cookie_output_dir) / 'cookie.json'
        try:
            netease_fr = CookieFlowReproducer(mock_data_dir + "/step_playlist")
            netease_fr.reproduce_all_flows()
            self.assertTrue(output_file.exists(), f"输出文件不存在: {output_file}")
        finally:
            if output_file.exists():
                output_file.unlink()
            dirpath = Path(cookie_output_dir)
            if dirpath.exists() and dirpath.is_dir():
                dirpath.rmdir()
        
if __name__ == "__main__":
    unittest.main()