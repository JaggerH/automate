#!/usr/bin/env python3

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

from .database import DatabaseManager
from .models import Base
from .config import ConfigLoader, SyncConfig

def load_playlist_json(file_path: str) -> Optional[dict]:
    """加载播放列表JSON文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"错误: 找不到文件 {file_path}")
        return None
    except json.JSONDecodeError as e:
        print(f"错误: JSON格式不正确 - {e}")
        return None
    except Exception as e:
        print(f"错误: 读取文件失败 - {e}")
        return None

def sync_single_playlist(db_manager: DatabaseManager, json_file: str, 
                        config: SyncConfig) -> bool:
    """同步单个播放列表"""
    print(f"正在同步播放列表: {json_file}")
    
    playlist_data = load_playlist_json(json_file)
    if not playlist_data:
        return False
    
    success = db_manager.sync_playlist_from_json(
        playlist_data, config.user_dir, config.input_dir, config.output_dir
    )
    
    if success:
        playlist_name = playlist_data.get('name', '未知播放列表')
        track_count = playlist_data.get('trackCount', 0)
        print(f"[成功] 同步播放列表 '{playlist_name}' ({track_count} 首歌曲)")
    else:
        print(f"[失败] 同步播放列表失败: {json_file}")
    
    return success

def sync_multiple_playlists(db_manager: DatabaseManager, json_dir: str,
                           config: SyncConfig) -> int:
    """同步目录中的所有播放列表JSON文件"""
    json_files = list(Path(json_dir).glob("*.json"))
    
    if not json_files:
        print(f"在目录 {json_dir} 中未找到JSON文件")
        return 0
    
    success_count = 0
    total_count = len(json_files)
    
    print(f"找到 {total_count} 个JSON文件，开始同步...")
    
    for json_file in json_files:
        if sync_single_playlist(db_manager, str(json_file), config):
            success_count += 1
    
    print(f"\n同步完成: {success_count}/{total_count} 个播放列表同步成功")
    return success_count

def print_stats(db_manager: DatabaseManager):
    """打印数据库统计信息"""
    stats = db_manager.get_playlist_stats()
    
    print("\n=== 数据库统计信息 ===")
    print(f"总播放列表数: {stats['total_playlists']}")
    print(f"总歌曲数: {stats['total_tracks']}")
    print(f"已找到文件的歌曲: {stats['tracks_with_files']}")
    print(f"未找到文件的歌曲: {stats['tracks_without_files']}")
    
    if stats['total_tracks'] > 0:
        found_percentage = (stats['tracks_with_files'] / stats['total_tracks']) * 100
        print(f"文件匹配率: {found_percentage:.1f}%")

def main():
    parser = argparse.ArgumentParser(description='音乐播放列表同步工具')
    parser.add_argument('--config', '-c', help='配置文件路径')
    parser.add_argument('--json-file', '-f', help='单个播放列表JSON文件路径')
    parser.add_argument('--json-dir', '-d', help='包含多个JSON文件的目录路径')
    parser.add_argument('--user-dir', '-u', help='用户音乐目录路径')
    parser.add_argument('--input-dir', '-i', help='输入音乐目录路径')
    parser.add_argument('--output-dir', '-o', help='输出音乐目录路径')
    parser.add_argument('--database', '--db', help='数据库文件路径')
    parser.add_argument('--stats', action='store_true', help='显示数据库统计信息')
    parser.add_argument('--create-config', help='创建默认配置文件到指定路径')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细输出模式')
    
    args = parser.parse_args()
    
    # 创建默认配置文件
    if args.create_config:
        ConfigLoader.create_default_config(args.create_config)
        return
    
    # 加载配置
    try:
        config = ConfigLoader.load_config(args.config)
        config = ConfigLoader.merge_config_with_args(config, args)
    except Exception as e:
        print(f"配置加载失败: {e}")
        sys.exit(1)
    
    # 验证参数
    if not args.json_file and not args.json_dir and not args.stats:
        if not config.json_file and not config.json_dir:
            print("错误: 请指定 --json-file、--json-dir 或使用 --stats 选项，或在配置文件中设置")
            parser.print_help()
            sys.exit(1)
    
    # 验证目录
    # 验证用户目录（支持列表格式）
    if not config.user_dir:
        print("错误: 未配置用户目录")
        sys.exit(1)
    
    if isinstance(config.user_dir, list):
        valid_user_dirs = []
        for user_dir in config.user_dir:
            if os.path.exists(user_dir):
                valid_user_dirs.append(user_dir)
            else:
                print(f"警告: 用户目录不存在，将跳过 - {user_dir}")
        
        if not valid_user_dirs:
            print("错误: 没有有效的用户目录")
            sys.exit(1)
        
        # 更新配置为有效的目录列表
        config.user_dir = valid_user_dirs
    else:
        if not os.path.exists(config.user_dir):
            print(f"错误: 用户目录不存在 - {config.user_dir}")
            sys.exit(1)
    
    # 验证输入目录
    if not config.input_dir:
        print("错误: 未配置输入目录")
        sys.exit(1)
    if not os.path.exists(config.input_dir):
        print(f"错误: 输入目录不存在 - {config.input_dir}")
        sys.exit(1)
    
    # 创建输出目录
    if not config.output_dir:
        print("错误: 未配置输出目录")
        sys.exit(1)
    
    if not os.path.exists(config.output_dir):
        os.makedirs(config.output_dir, exist_ok=True)
        if config.verbose:
            print(f"创建输出目录: {config.output_dir}")
    
    # 初始化数据库
    database_url = ConfigLoader.get_database_url(config)
    if config.verbose:
        print(f"使用数据库: {database_url}")
    
    db_manager = DatabaseManager(database_url)
    
    # 仅显示统计信息
    if args.stats:
        print_stats(db_manager)
        return
    
    try:
        json_file = args.json_file or config.json_file
        json_dir = args.json_dir or config.json_dir
        
        if json_file:
            success = sync_single_playlist(db_manager, json_file, config)
            if not success:
                sys.exit(1)
        
        elif json_dir:
            success_count = sync_multiple_playlists(db_manager, json_dir, config)
            if success_count == 0:
                sys.exit(1)
        
        if config.verbose:
            print_stats(db_manager)
        
    except KeyboardInterrupt:
        print("\n用户中断操作")
        sys.exit(1)
    except Exception as e:
        print(f"发生未知错误: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()