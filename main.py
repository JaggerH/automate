#!/usr/bin/env python3
"""
Automate - Process Injection Extractor
进程注入模式提取器，自动提取Cookie和播放列表数据

使用方法:
  python main.py              # 启动进程注入提取器
  python main.py --status     # 查看状态
  python main.py --cleanup    # 清理旧数据
"""

import sys
import argparse
import os
import subprocess
import psutil
from pathlib import Path
from typing import List, Dict

# Windows控制台编码设置
if os.name == 'nt':
    import locale
    # 设置环境变量
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# 添加src到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from src.core.csv_manager import CSVStatusManager
from src.utils.config_loader import config_loader

def get_service_processes() -> Dict[str, List[int]]:
    """检测所有目标服务进程"""
    target_processes = {
        'netease': ['cloudmusic.exe', 'CloudMusic.exe'],
        'quark': ['QuarkCloudDrive.exe', 'quark.exe']
    }
    
    found_processes = {}
    
    for service, process_names in target_processes.items():
        pids = []
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] in process_names:
                    pids.append(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        if pids:
            found_processes[service] = pids
    
    return found_processes

def start_process_injection():
    """启动进程注入提取器"""
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    print("Process Injection Extractor")
    print("=" * 60)
    
    # 检测目标进程
    found_processes = get_service_processes()
    
    if not found_processes:
        print("未检测到任何目标进程")
        print("支持的进程:")
        print("  网易云音乐: cloudmusic.exe, CloudMusic.exe")
        print("  夸克网盘: QuarkCloudDrive.exe, quark.exe")
        print("\n请先启动相应的客户端程序")
        return 1
    
    print("检测到以下进程:")
    all_pids = []
    for service, pids in found_processes.items():
        print(f"  {service}: {pids}")
        all_pids.extend(pids)
        
        # 显示进程详情
        for pid in pids:
            try:
                proc = psutil.Process(pid)
                print(f"    PID {pid}: {proc.name()}")
            except psutil.NoSuchProcess:
                continue
    
    # 生成mitmproxy命令
    pid_list = ','.join(map(str, all_pids))
    
    cmd = [
        "mitmdump",
        "-s", "src/core/process_inject.py",
        "--mode", f"local:{pid_list}",
        "--set", "confdir=temp_certs",
        "--quiet"  # 静默模式，不显示连接日志
    ]
    
    print(f"\n启动进程注入提取器")
    print(f"命令: {' '.join(cmd)}")
    print("=" * 60)
    print("功能说明:")
    print("1. 自动提取Cookie并保存到配置的输出路径")
    print("2. 监控目标播放列表并自动解密保存") 
    print("3. 数据保存在 data/outputs/ 目录下")
    print("4. 按 Ctrl+C 停止提取")
    print("=" * 60)
    
    try:
        # 设置环境变量
        env = os.environ.copy()
        env['AUTOMATE_INJECT_MODE'] = 'true'
        
        subprocess.run(cmd, cwd=project_root, env=env)
    except KeyboardInterrupt:
        print("\n进程注入提取器已停止")
    except Exception as e:
        print(f"启动失败: {e}")
        return 1
    
    return 0

def show_status():
    """显示状态信息"""
    print("Process Injection Extractor 状态报告")
    print("=" * 50)
    
    try:
        # 服务配置
        services = config_loader.get_enabled_services()
        print(f"\n配置的服务 ({len(services)}个):")
        for service, config in services.items():
            status = "[启用]" if config.get('enabled', True) else "[禁用]"
            print(f"   * {config['name']}: {status}")
            print(f"     域名: {', '.join(config['domains'][:2])}")
            
            # 显示功能配置
            features = config.get('features', {})
            if features.get('extract_cookie', {}).get('enabled'):
                cookie_file = features['extract_cookie']['output_file']
                print(f"     Cookie输出: {cookie_file}")
            
            if features.get('extract_playlist', {}).get('enabled'):
                playlist_dir = features['extract_playlist']['output_dir'] 
                target_ids = features['extract_playlist'].get('target_ids', [])
                print(f"     播放列表输出: {playlist_dir}")
                print(f"     目标播放列表: {target_ids}")
        
        # 进程检测
        found_processes = get_service_processes()
        print(f"\n当前进程状态:")
        if found_processes:
            for service, pids in found_processes.items():
                print(f"   * {service}: {len(pids)}个进程 {pids}")
        else:
            print("   未检测到目标进程")
        
        # 历史统计
        csv_manager = CSVStatusManager()
        stats = csv_manager.get_service_stats()
        
        if stats:
            print(f"\n提取统计:")
            for service, info in stats.items():
                print(f"   * {service.upper()}:")
                print(f"     最后提取: {info['last_extract']}")
                print(f"     提取次数: {info['extract_count']}")
                print(f"     状态: {info['status']}")
        else:
            print("\n暂无提取记录")
    
    except Exception as e:
        print(f"获取状态失败: {e}")

def cleanup_data():
    """清理旧数据"""
    print("清理旧数据...")
    
    try:
        csv_manager = CSVStatusManager()
        csv_manager.cleanup_old_sessions(days=7)
        print("清理完成")
    except Exception as e:
        print(f"清理失败: {e}")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="Automate - Process Injection Extractor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py              启动进程注入提取器
  python main.py --status     查看状态信息
  python main.py --cleanup    清理7天前的旧数据
        """
    )
    
    parser.add_argument(
        '--status', 
        action='store_true', 
        help='显示当前状态'
    )
    
    parser.add_argument(
        '--cleanup',
        action='store_true',
        help='清理旧的会话数据'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='Automate v2.0.0 - Process Injection'
    )
    
    args = parser.parse_args()
    
    if args.status:
        show_status()
    elif args.cleanup:
        cleanup_data()
    else:
        # 默认启动进程注入提取器
        sys.exit(start_process_injection())

if __name__ == "__main__":
    main()