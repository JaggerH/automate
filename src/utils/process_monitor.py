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
from typing import Dict, List, Set, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class ProcessMonitor:
    """进程监控器 - 监控目标进程并自动注入"""
    
    def __init__(self, target_processes: Dict[str, List[str]], check_interval: int = 5):
        self.target_processes = target_processes
        self.check_interval = check_interval
        self.running = False
        self.current_pids = set()
        self.mitm_process = None
        self.monitor_thread = None
        
        # 静默模式配置
        self.silent_mode = False
        
    def set_silent_mode(self, silent: bool = True):
        """设置静默模式"""
        self.silent_mode = silent
        
    def get_all_target_pids(self) -> Set[int]:
        """获取所有目标进程的PID"""
        found_pids = set()
        
        for service, process_names in self.target_processes.items():
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'] in process_names:
                        found_pids.add(proc.info['pid'])
                        if not self.silent_mode:
                            logger.info(f"发现目标进程: {proc.info['name']} (PID: {proc.info['pid']})")
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        
        return found_pids
    
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
                "--set", "confdir=temp_certs"
            ]
            
            if self.silent_mode:
                cmd.append("--quiet")
            
            if not self.silent_mode:
                logger.info(f"启动进程注入: PID={pid_list}")
                logger.info(f"命令: {' '.join(cmd)}")
            
            # 启动mitmproxy进程
            self.mitm_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL if self.silent_mode else None,
                stderr=subprocess.DEVNULL if self.silent_mode else None
            )
            
            # 等待一小段时间确保启动成功
            time.sleep(2)
            
            if self.mitm_process.poll() is None:
                if not self.silent_mode:
                    logger.info("mitmproxy进程注入启动成功")
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
                
                if not self.silent_mode:
                    logger.info("mitmproxy进程注入已停止")
                    
            except Exception as e:
                logger.error(f"停止mitmproxy进程失败: {e}")
            finally:
                self.mitm_process = None
    
    def _monitor_loop(self):
        """监控循环"""
        logger.info("开始进程监控...")
        
        while self.running:
            try:
                # 获取当前所有目标进程PID
                current_pids = self.get_all_target_pids()
                
                # 检查进程变化
                if current_pids != self.current_pids:
                    if not self.silent_mode:
                        logger.info(f"进程状态变化: {len(self.current_pids)} -> {len(current_pids)}")
                    
                    # 停止旧的注入
                    if self.mitm_process:
                        self.stop_mitm_injection()
                    
                    # 如果有目标进程，启动新的注入
                    if current_pids:
                        success = self.start_mitm_injection(current_pids)
                        if success:
                            self.current_pids = current_pids
                        else:
                            self.current_pids = set()
                    else:
                        self.current_pids = set()
                        if not self.silent_mode:
                            logger.info("无目标进程，等待进程启动...")
                
                # 检查mitmproxy进程是否异常退出
                elif self.mitm_process and self.mitm_process.poll() is not None:
                    logger.warning("检测到mitmproxy进程异常退出，尝试重启")
                    self.mitm_process = None
                    if current_pids:
                        self.start_mitm_injection(current_pids)
                
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