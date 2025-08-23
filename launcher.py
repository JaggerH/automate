import sys
import time
import signal
import subprocess
import threading
import os
from pathlib import Path
from typing import Optional
import socket

# Windows控制台编码设置
if os.name == 'nt':
    import locale
    # 设置环境变量
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# 添加src到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from src.utils.config_loader import config_loader
from src.utils.port_scanner import PortScanner
from src.core.csv_manager import CSVStatusManager

class AutomateLauncher:
    def __init__(self):
        self.proxy_process: Optional[subprocess.Popen] = None
        self.running = False
        self.port = None
        self.scanner = PortScanner()
        
    def start(self):
        """启动Automate"""
        try:
            self._print_banner()
            
            # 检查环境
            self._check_environment()
            
            # 找到可用端口
            self.port = self._find_available_port()
            print(f"使用端口: {self.port}")
            
            # 启动代理
            self._start_proxy(self.port)
            
            # 显示状态
            self._show_startup_info()
            
            # 保持运行
            self._keep_alive()
            
        except KeyboardInterrupt:
            print("\n收到中断信号...")
            self.stop()
        except Exception as e:
            print(f"启动失败: {e}")
            self.stop()
    
    def _print_banner(self):
        """打印启动横幅"""
        banner = """
============================================
            Automate 启动中...
         Cookie 自动提取代理服务
============================================
        """
        print(banner)
    
    def _check_environment(self):
        """检查运行环境"""
        print("检查运行环境...")
        
        # 检查Python版本
        if sys.version_info < (3, 8):
            raise RuntimeError("需要Python 3.8+版本")
        
        # 检查依赖
        try:
            import mitmproxy
            # 尝试获取版本信息，不同版本的mitmproxy版本获取方式可能不同
            try:
                version = mitmproxy.__version__
            except AttributeError:
                try:
                    from mitmproxy import version
                    version = version.VERSION
                except:
                    version = "未知版本"
            print(f"[OK] mitmproxy版本: {version}")
        except ImportError:
            raise RuntimeError("未找到mitmproxy，请先安装: pip install mitmproxy")
        
        # 检查配置文件
        try:
            config_loader.get_proxy_config()
            config_loader.get_services_config()
            print("[OK] 配置文件加载成功")
        except Exception as e:
            raise RuntimeError(f"配置文件加载失败: {e}")
    
    def _find_available_port(self) -> int:
        """寻找可用端口"""
        proxy_config = config_loader.get_proxy_config()['proxy']
        preferred_port = proxy_config['listen']['port']
        backup_ports = proxy_config['listen']['backup_ports']
        
        # 先尝试首选端口
        if not self.scanner.is_port_open('127.0.0.1', preferred_port):
            return preferred_port
        
        # 尝试备用端口
        for port in backup_ports:
            if not self.scanner.is_port_open('127.0.0.1', port):
                return port
        
        # 自动寻找端口
        available_port = self.scanner.find_available_port('127.0.0.1', 8090)
        if available_port:
            return available_port
            
        raise RuntimeError("无法找到可用端口")
    
    def _start_proxy(self, port: int):
        """启动mitmproxy"""
        print("启动代理服务...")
        
        # 确保证书目录存在
        cert_dir = Path("temp_certs")
        cert_dir.mkdir(exist_ok=True)
        
        # 构建启动命令
        proxy_script = Path(__file__).parent / "src" / "core" / "smart_proxy.py"
        
        cmd = [
            'mitmdump',
            '-s', str(proxy_script),
            '-p', str(port),
            '--set', f'confdir={cert_dir}',
            '--set', 'stream_large_bodies=1',
            '--set', 'connection_strategy=lazy',  # 懒加载连接
        ]
        
        # 启动进程
        self.proxy_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        # 等待启动并检查状态
        time.sleep(3)
        if self.proxy_process.poll() is not None:
            # 获取错误输出
            stdout, stderr = self.proxy_process.communicate()
            raise Exception(f"mitmproxy启动失败:{stdout}")
        
        print("[OK] 代理服务启动成功")
    
    def _show_startup_info(self):
        """显示启动信息"""
        print("="*50)
        print("Automate 已成功启动!")
        print("="*50)
        
        # 代理信息
        print(f"代理地址: http://127.0.0.1:{self.port}")
        print(f"设置方法:")
        print(f"   * Windows系统代理: 控制面板 → 网络 → 代理设置")
        print(f"   * 浏览器代理: 127.0.0.1:{self.port}")
        
        # 监控服务信息
        services = config_loader.get_enabled_services()
        print(f"监控的服务:")
        for service, config in services.items():
            print(f"   * {config['name']}: {', '.join(config['domains'][:2])}")
        
        # 状态信息
        csv_manager = CSVStatusManager()
        stats = csv_manager.get_service_stats()
        if stats:
            print(f"历史统计:")
            for service, info in stats.items():
                print(f"   * {service}: 提取{info['extract_count']}次, 最后提取: {info['last_extract']}")
        
        print("提示:")
        print("   * 正常使用网易云、夸克等应用，系统会自动提取Cookie")
        print("   * Cookie将自动保存到对应的输出文件")
        print("   * 按 Ctrl+C 停止服务")
        print("="*50)
    
    def _keep_alive(self):
        """保持程序运行"""
        self.running = True
        
        # 注册信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # 启动监控线程
        monitor_thread = threading.Thread(target=self._monitor_proxy, daemon=True)
        monitor_thread.start()
        
        # 主循环
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    
    def _monitor_proxy(self):
        """监控代理进程状态"""
        while self.running and self.proxy_process:
            if self.proxy_process.poll() is not None:
                print("[WARNING] 代理进程意外退出")
                self.running = False
                break
            time.sleep(5)
    
    def _signal_handler(self, signum, frame):
        """处理停止信号"""
        self.stop()
    
    def stop(self):
        """停止服务"""
        print("正在停止服务...")
        self.running = False
        
        if self.proxy_process:
            try:
                self.proxy_process.terminate()
                self.proxy_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proxy_process.kill()
            except Exception as e:
                print(f"停止代理进程时出错: {e}")
        
        print("Automate已停止")
        sys.exit(0)

def main():
    """主函数"""
    launcher = AutomateLauncher()
    launcher.start()

if __name__ == "__main__":
    main()