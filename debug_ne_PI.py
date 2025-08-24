#!/usr/bin/env python3
"""
NetEase Cloud Music EAPI Decryptor
网易云音乐EAPI解密工具

使用mitmproxy的PID注入模式监控网易云音乐，
自动解密EAPI请求/响应，提取播放列表数据。

核心功能：
- 自动检测网易云音乐进程
- 使用PID注入模式无需代理配置
- 解密EAPI请求和响应数据
- 保存完整的播放列表信息到JSON文件
- 支持目标播放列表ID匹配

使用方法:
1. 启动网易云音乐客户端
2. 运行 python debug_proxy.py
3. 在网易云中浏览目标播放列表
4. 解密结果保存在 data/debug/ 目录
"""
import subprocess
import sys
import os
import psutil
from pathlib import Path
from typing import List

# Windows控制台编码设置
if os.name == 'nt':
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# 添加src到Python路径
sys.path.insert(0, str(Path(__file__).parent))

def get_netease_pids() -> List[int]:
    """检测网易云音乐进程"""
    pids = []
    target_names = ['cloudmusic.exe', 'CloudMusic.exe']
    
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if proc.info['name'].lower() in [name.lower() for name in target_names]:
                pids.append(proc.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    
    return pids

def main():
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    print("NetEase Cloud Music EAPI Decryptor")
    print("=" * 60)
    
    # 检测网易云音乐进程
    netease_pids = get_netease_pids()
    
    if not netease_pids:
        print("未检测到网易云音乐进程")
        print("请先启动网易云音乐，然后重新运行此脚本")
        print("支持的进程名: cloudmusic.exe, CloudMusic.exe")
        return 1
    
    print(f"检测到网易云音乐进程: {netease_pids}")
    
    # 显示进程信息
    for pid in netease_pids:
        try:
            proc = psutil.Process(pid)
            print(f"   PID {pid}: {proc.name()}")
        except psutil.NoSuchProcess:
            continue
    
    # 生成调试命令
    pid_list = ','.join(map(str, netease_pids))
    
    cmd = [
        "mitmdump",
        "-s", "src/core/debug_ne_addon.py", 
        "--mode", f"local:{pid_list}",
        "--set", "confdir=temp_certs",
        "--quiet"  # 静默模式，不显示连接日志
    ]
    
    print(f"\n启动EAPI解密代理 (PID注入模式)")
    print(f"命令: {' '.join(cmd)}")
    print("=" * 60)
    print("使用说明:")
    print("1. 现在在网易云音乐中浏览播放列表")
    print("2. 观察终端输出，查看解密结果") 
    print("3. 解密的数据将保存在 data/debug/ 目录")
    print("4. 按 Ctrl+C 停止解密")
    print("=" * 60)
    
    try:
        # 设置环境变量告诉mitmproxy我们在PID模式
        env = os.environ.copy()
        env['AUTOMATE_PID_MODE'] = 'true'
        
        subprocess.run(cmd, cwd=project_root, env=env)
    except KeyboardInterrupt:
        print("\n调试已停止")
    except Exception as e:
        print(f"启动失败: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())