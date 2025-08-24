#!/usr/bin/env python3
"""
Process Monitor - 进程监控器
监控目标进程的启动和关闭，自动进行进程注入
"""
import psutil
import time
import logging
import subprocess
import threading
import os
from typing import Dict, List, Set, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class ProcessMonitor:
    """进程监控器 - 监控目标进程并自动注入"""
    
    def __init__(self, target_processes: Dict[str, List[str]], check_interval: int = 10):
        self.target_processes = target_processes
        self.check_interval = check_interval
        self.running = False
        self.current_pids = set()
        self.current_processes = {}  # 记录当前进程信息 {pid: process_name}
        self.mitm_process = None
        self.monitor_thread = None
        
        # 静默模式配置
        self.silent_mode = False
        
    def set_silent_mode(self, silent: bool = True):
        """设置静默模式"""
        self.silent_mode = silent
        
    def get_all_target_pids(self) -> tuple[Set[int], Dict[int, str]]:
        """获取所有目标进程的PID和进程信息"""
        found_pids = set()
        process_info = {}  # {pid: process_name}
        
        for service, process_names in self.target_processes.items():
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'] in process_names:
                        pid = proc.info['pid']
                        name = proc.info['name']
                        found_pids.add(pid)
                        process_info[pid] = name
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        
        return found_pids, process_info
    
    def start_mitm_injection(self, pids: Set[int]) -> bool:
        """启动mitmproxy进程注入"""
        if self.mitm_process and self.mitm_process.poll() is None:
            logger.warning("mitmproxy进程已在运行")
            return False
        
        try:
            pid_list = ','.join(map(str, pids))
            cmd = [
                "mitmdump",
                "-s", "src/core/process_inject.py",
                "--mode", f"local:{pid_list}",
                "--set", "confdir=temp_certs",
                "--quiet"  # 总是使用quiet模式减少日志输出
            ]
            
            # 静默模式下完全禁用输出
            if self.silent_mode:
                cmd.extend([
                    "--set", "stream_large_bodies=1",
                    "--set", "connection_strategy=lazy"
                ])
            
            if not self.silent_mode:
                logger.info(f"启动进程注入: PID={pid_list}")
            
            # 启动mitmproxy进程
            # 配置环境变量和日志
            env = os.environ.copy()
            env['AUTOMATE_DAEMON_MODE'] = 'true'  # 告知process_inject这是守护模式
            
            # 配置子进程的日志级别
            if not self.silent_mode:
                env['PYTHON_LOG_LEVEL'] = 'INFO'
            else:
                env['PYTHON_LOG_LEVEL'] = 'WARNING'
            
            # 让子进程继承父进程的stderr，这样logger能正常输出
            self.mitm_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,  # 只屏蔽mitmproxy的stdout冗余日志  
                stderr=None,  # 继承父进程stderr，让logger正常输出
                env=env
            )
            
            # 等待一小段时间确保启动成功
            time.sleep(2)
            
            if self.mitm_process.poll() is None:
                return True
            else:
                logger.error("mitmproxy进程启动失败")
                return False
                
        except Exception as e:
            logger.error(f"启动mitmproxy失败: {e}")
            return False
    
    def stop_mitm_injection(self):
        """停止mitmproxy进程注入"""
        if self.mitm_process and self.mitm_process.poll() is None:
            try:
                self.mitm_process.terminate()
                # 等待进程结束
                try:
                    self.mitm_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    logger.warning("进程未在规定时间内结束，强制杀死")
                    self.mitm_process.kill()
                    self.mitm_process.wait()
                
                pass  # 静默停止，不输出日志
                    
            except Exception as e:
                logger.error(f"停止mitmproxy进程失败: {e}")
            finally:
                self.mitm_process = None
    
    def _get_process_names_summary(self, process_info: Dict[int, str]) -> str:
        """获取进程名称摘要（合并重复名称）"""
        if not process_info:
            return "无"
        
        # 统计每个进程名的数量
        name_counts = {}
        for name in process_info.values():
            name_counts[name] = name_counts.get(name, 0) + 1
        
        # 格式化输出
        parts = []
        for name, count in name_counts.items():
            if count > 1:
                parts.append(f"{name}({count}个)")
            else:
                parts.append(name)
        
        return ", ".join(parts)
    
    def _monitor_loop(self):
        """监控循环"""
        logger.info("开始进程监控...")
        
        while self.running:
            try:
                # 获取当前所有目标进程PID和进程信息
                current_pids, current_process_info = self.get_all_target_pids()
                
                # 检查PIDs是否发生变化
                if current_pids != self.current_pids:
                    # 分析变化
                    new_pids = current_pids - self.current_pids
                    closed_pids = self.current_pids - current_pids
                    
                    # 处理进程关闭
                    if closed_pids:
                        closed_names = [self.current_processes.get(pid, "未知") for pid in closed_pids]
                        closed_summary = self._get_process_names_summary({pid: name for pid, name in zip(closed_pids, closed_names)})
                        logger.info(f"程序关闭: {closed_summary}")
                    
                    # 处理新进程
                    if new_pids:
                        new_process_info = {pid: current_process_info[pid] for pid in new_pids}
                        new_summary = self._get_process_names_summary(new_process_info)
                        logger.info(f"检测到新程序: {new_summary}")
                    
                    # 停止旧的注入
                    if self.mitm_process:
                        self.stop_mitm_injection()
                    
                    # 如果有目标进程，启动新的注入
                    if current_pids:
                        success = self.start_mitm_injection(current_pids)
                        if success:
                            self.current_pids = current_pids
                            self.current_processes = current_process_info
                            if not self.silent_mode:
                                process_summary = self._get_process_names_summary(current_process_info)
                                logger.info(f"已注入进程: {process_summary}")
                        else:
                            self.current_pids = set()
                            self.current_processes = {}
                    else:
                        self.current_pids = set()
                        self.current_processes = {}
                        # 只在从有进程变为无进程时提示
                        if closed_pids:
                            logger.info("等待目标进程启动...")
                
                # 检查mitmproxy进程是否异常退出（PIDs没变但mitmproxy退出了）
                elif self.mitm_process and self.mitm_process.poll() is not None:
                    logger.warning("检测到mitmproxy进程异常退出，尝试重启")
                    self.mitm_process = None
                    if current_pids:
                        self.start_mitm_injection(current_pids)
                
                # PIDs没有变化时完全静默，不输出任何信息
                
                time.sleep(self.check_interval)
                
            except KeyboardInterrupt:
                logger.info("收到停止信号，退出监控")
                break
            except Exception as e:
                logger.error(f"监控循环出错: {e}")
                time.sleep(self.check_interval)
        
        # 清理
        self.stop_mitm_injection()
        logger.info("进程监控已停止")
    
    def start(self):
        """启动监控"""
        if self.running:
            logger.warning("监控器已在运行")
            return
        
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        if not self.silent_mode:
            logger.info("进程监控器已启动")
    
    def stop(self):
        """停止监控"""
        if not self.running:
            return
        
        self.running = False
        
        # 等待监控线程结束
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=10)
        
        # 清理资源
        self.stop_mitm_injection()
        
        if not self.silent_mode:
            logger.info("进程监控器已停止")
    
    def is_running(self) -> bool:
        """检查监控器是否在运行"""
        return self.running and self.monitor_thread and self.monitor_thread.is_alive()
    
    def get_status(self) -> Dict:
        """获取当前状态"""
        return {
            'monitor_running': self.is_running(),
            'mitm_running': self.mitm_process is not None and self.mitm_process.poll() is None,
            'target_pids': list(self.current_pids),
            'silent_mode': self.silent_mode
        }