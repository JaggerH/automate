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
import logging
import signal
from pathlib import Path
from typing import List, Dict
from datetime import datetime

# Windows控制台编码设置
if os.name == 'nt':
    import locale
    # 设置环境变量
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# 添加src到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from src.core.csv_manager import CSVStatusManager
from src.utils.config_loader import config_loader
from src.utils.process_monitor import ProcessMonitor

# 配置日志
def setup_logging(silent_mode=False):
    """设置日志配置"""
    level = logging.WARNING if silent_mode else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )

# 全局监控器实例
monitor = None

def get_target_processes_config() -> Dict[str, List[str]]:
    """获取目标进程配置"""
    return {
        'netease': ['cloudmusic.exe', 'CloudMusic.exe'],
        'quark': ['QuarkCloudDrive.exe', 'quark.exe']
    }

def get_service_processes() -> Dict[str, List[int]]:
    """检测所有目标服务进程"""
    target_processes = get_target_processes_config()
    
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

def signal_handler(signum, frame):
    """信号处理器"""
    global monitor
    print(f"\n收到信号 {signum}，正在停止...")
    if monitor:
        monitor.stop()
    sys.exit(0)

def start_process_injection(replay_file=None):
    """启动进程注入提取器"""
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    print("Process Injection Extractor")
    print("=" * 60)
    
    # 如果是replay模式
    if replay_file:
        print(f"回放模式: {replay_file}")
        
        if not os.path.exists(replay_file):
            print(f"错误: 回放文件不存在: {replay_file}")
            return 1
            
        cmd = [
            "mitmdump",
            "-s", "src/core/process_inject.py",
            "-r", replay_file,
            "--set", "confdir=temp_certs",
            "--quiet"
        ]
    else:
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
        
        # 检查debug配置并添加输出文件
        services_config = config_loader.get_services_config()
        debug_config = services_config.get('debug', {})
        cmd = [
            "mitmdump",
            "-s", "src/core/process_inject.py",
            "--mode", f"local:{pid_list}",
            "--set", "confdir=temp_certs",
            "--quiet"  # 静默模式，不显示连接日志
        ]
        
        if debug_config.get('enable', False):
            # 创建debug目录
            debug_dir = Path(debug_config.get('output_dir', 'data/debug'))
            debug_dir.mkdir(parents=True, exist_ok=True)
            
            # 生成时间戳文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            outfile = debug_dir / f"{timestamp}.flows"
            
            cmd.extend(["-w", str(outfile)])
            print(f"调试模式已启用，流量将保存到: {outfile}")
    
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

def start_daemon_mode(silent_mode=False):
    """启动守护模式 - 持续监控进程"""
    global monitor
    
    setup_logging(silent_mode)
    
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    if not silent_mode:
        print("Process Injection Daemon Mode")
        print("=" * 60)
        print("守护模式启动 - 持续监控目标进程")
        print("当检测到目标进程时自动启动注入")
        print("当目标进程关闭时自动停止注入")
        print("按 Ctrl+C 停止守护进程")
        print("=" * 60)
    
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 创建并启动监控器
    target_processes = get_target_processes_config()
    monitor = ProcessMonitor(target_processes, check_interval=10)
    monitor.set_silent_mode(silent_mode)
    
    try:
        monitor.start()
        
        if not silent_mode:
            print("守护进程已启动，开始监控...")
        
        # 主线程等待
        while monitor.is_running():
            try:
                import time
                time.sleep(1)
            except KeyboardInterrupt:
                break
        
    except KeyboardInterrupt:
        if not silent_mode:
            print("\n接收到停止信号")
    except Exception as e:
        logging.error(f"守护模式出错: {e}")
        return 1
    finally:
        if monitor:
            monitor.stop()
        if not silent_mode:
            print("守护进程已停止")
    
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
  python main.py              启动进程注入提取器（一次性模式）
  python main.py --daemon     启动守护模式，持续监控进程
  python main.py --daemon --silent   静默守护模式
  python main.py --replay flows.dump  回放流量文件进行分析
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
        '--daemon',
        action='store_true',
        help='启动守护模式 - 持续监控进程并自动注入'
    )
    
    parser.add_argument(
        '--silent',
        action='store_true',
        help='静默模式 - 减少输出信息'
    )
    
    parser.add_argument(
        '--replay',
        type=str,
        help='回放指定的流量文件进行调试分析'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='Automate v2.1.0 - Process Injection with Daemon Mode'
    )
    
    args = parser.parse_args()
    
    if args.status:
        show_status()
    elif args.cleanup:
        cleanup_data()
    elif args.replay:
        # 回放模式
        if args.silent:
            setup_logging(silent_mode=True)
        sys.exit(start_process_injection(replay_file=args.replay))
    elif args.daemon:
        # 守护模式
        sys.exit(start_daemon_mode(silent_mode=args.silent))
    else:
        # 默认启动进程注入提取器（一次性模式）
        if args.silent:
            setup_logging(silent_mode=True)
        sys.exit(start_process_injection())

if __name__ == "__main__":
    main()