#!/usr/bin/env python3
"""
Automate - Cookie自动提取器
智能代理服务，自动提取和管理各种服务的Cookie

使用方法:
  python main.py              # 启动代理服务
  python main.py --status     # 查看状态
  python main.py --cleanup    # 清理旧数据
"""

import sys
import argparse
import os
from pathlib import Path

# Windows控制台编码设置
if os.name == 'nt':
    import locale
    # 设置环境变量
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# 添加src到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from launcher import AutomateLauncher
from src.core.csv_manager import CSVStatusManager
from src.utils.config_loader import config_loader

def show_status():
    """显示状态信息"""
    print("Automate 状态报告")
    print("=" * 50)
    
    try:
        # 服务配置
        services = config_loader.get_enabled_services()
        print(f"\n配置的服务 ({len(services)}个):")
        for service, config in services.items():
            status = "[启用]" if config.get('enabled', True) else "[禁用]"
            print(f"   * {config['name']}: {status}")
            print(f"     域名: {', '.join(config['domains'][:2])}")
            print(f"     输出: {config['output_file']}")
        
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
        
        # 代理配置
        proxy_config = config_loader.get_proxy_config()['proxy']
        print(f"\n代理配置:")
        print(f"   监听端口: {proxy_config['listen']['port']}")
        print(f"   上游代理: {'启用' if proxy_config['upstream']['enabled'] else '禁用'}")
        
        if proxy_config['upstream']['enabled']:
            ports = proxy_config['upstream']['clash_detection']['ports']
            print(f"   检测端口: {', '.join(map(str, ports))}")
    
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
        description="Automate - Cookie自动提取器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py              启动代理服务
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
        version='Automate v1.0.0'
    )
    
    args = parser.parse_args()
    
    if args.status:
        show_status()
    elif args.cleanup:
        cleanup_data()
    else:
        # 默认启动代理服务
        launcher = AutomateLauncher()
        launcher.start()

if __name__ == "__main__":
    main()