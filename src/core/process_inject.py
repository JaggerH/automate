#!/usr/bin/env python3
"""
Process Injection Mode Extractor
进程注入模式提取器

基于mitmproxy PID注入，提供Cookie和播放列表提取功能
参考smart_proxy架构，专注于进程注入模式
"""
import subprocess
import sys
import os
import psutil
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from src.utils.config_loader import config_loader
from src.core.csv_manager import CSVStatusManager
from src.extractors.netease_extractor import NeteaseExtractor
from src.extractors.quark_extractor import QuarkExtractor

# 设置日志
logger = logging.getLogger(__name__)

class ProcessInject:
    """进程注入模式提取器"""
    
    def __init__(self):
        self.services_config = None
        self.csv_manager = None
        self.extractors = {}
        self.session_id = f"{int(time.time())}_inject"
        self.request_count = 0
        self.extract_count = 0
        
        # 目标进程映射 - 将从配置加载
        self.target_processes = {}
        
        # 检查是否为守护模式（通过环境变量）
        self.is_daemon_mode = os.environ.get('AUTOMATE_DAEMON_MODE') == 'true'
    
    def load(self, loader):
        """mitmproxy加载时初始化"""
        try:
            # 配置子进程的logging
            self._setup_child_logging()
            
            logger.info("初始化进程注入提取器...")
            
            # 加载服务配置
            self.services_config = config_loader.get_enabled_services()
            
            # 从配置加载进程映射
            self._load_process_config()
            
            # 初始化CSV管理器
            self.csv_manager = CSVStatusManager()
            
            # 初始化提取器
            self._init_extractors()
            
            # 开始会话
            self.csv_manager.start_session(self.session_id, "PID_Injection")
            
            if not self.is_daemon_mode:
                logger.info(f"已加载服务: {list(self.services_config.keys())}")
            
        except (ImportError, AttributeError) as e:
            logger.error(f"配置加载失败: {e}")
            raise
        except Exception as e:
            logger.exception("初始化过程中发生未知错误")
            raise
    
    def _init_extractors(self):
        """初始化提取器"""
        for service_name, service_config in self.services_config.items():
            if service_name == 'netease':
                self.extractors[service_name] = NeteaseExtractor(service_config)
            elif service_name == 'quark':
                self.extractors[service_name] = QuarkExtractor(service_config)
            
            if not self.is_daemon_mode:
                logger.info(f"已初始化 {service_name} 提取器")
    
    def _load_process_config(self):
        """从配置加载进程映射"""
        # 默认进程映射
        default_processes = {
            'netease': ['cloudmusic.exe', 'CloudMusic.exe'],
            'quark': ['QuarkCloudDrive.exe', 'quark.exe']
        }
        
        # 从服务配置中加载进程名 (如果存在)
        for service_name, service_config in self.services_config.items():
            process_names = service_config.get('process_names', default_processes.get(service_name, []))
            if process_names:
                self.target_processes[service_name] = process_names
                logger.debug(f"加载 {service_name} 进程映射: {process_names}")
            else:
                logger.warning(f"服务 {service_name} 未配置进程名，将无法进行进程检测")
    
    def _setup_child_logging(self):
        """设置子进程的logging配置"""
        log_level_str = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING')
        log_level = getattr(logging, log_level_str, logging.WARNING)
        
        # 配置根logger
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S',
            force=True  # 强制重新配置
        )
        
        # 在守护模式下屏蔽mitmproxy的冗余日志
        if self.is_daemon_mode:
            # 完全屏蔽proxy.server的连接日志
            logging.getLogger('mitmproxy.proxy.server').setLevel(logging.ERROR)
            
            # 其他mitmproxy日志保持WARNING级别（显示错误但不显示INFO）
            other_mitmproxy_loggers = [
                'mitmproxy.proxy.events', 
                'mitmproxy.http',
                'mitmproxy.flow',
                'mitmproxy.proxy'
            ]
            
            for logger_name in other_mitmproxy_loggers:
                logging.getLogger(logger_name).setLevel(logging.WARNING)
    
    def detect_processes(self, service: str) -> List[int]:
        """检测指定服务的目标进程"""
        pids = []
        target_names = self.target_processes.get(service, [])
        
        if not target_names:
            return pids
        
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] in target_names:
                    pids.append(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        return pids
    
    def get_all_target_pids(self) -> Dict[str, List[int]]:
        """获取所有启用服务的目标进程PID"""
        all_pids = {}
        
        for service_name in self.services_config.keys():
            pids = self.detect_processes(service_name)
            if pids:
                all_pids[service_name] = pids
        
        return all_pids
    
    def request(self, flow):
        """处理HTTP请求"""
        self.request_count += 1
        
        # 检查是否为目标服务域名
        target_service = self._identify_service(flow.request.pretty_host)
        if not target_service:
            return
        
        # 获取对应的提取器
        extractor = self.extractors.get(target_service)
        if not extractor:
            return
        
        # 设置服务信息到flow元数据，避免提取器重复检查
        flow.metadata['identified_service'] = target_service
        flow.metadata['service_config'] = self.services_config[target_service]
        flow.metadata['csv_manager'] = self.csv_manager
        
        # 委托给提取器处理
        try:
            extractor.handle_request(flow)
        except (AttributeError, KeyError) as e:
            logger.error(f"处理请求时出错 ({target_service}): {e}")
        except Exception as e:
            logger.exception(f"处理请求时发生未知错误 ({target_service})")
    
    def response(self, flow):
        """处理HTTP响应"""
        # 使用已识别的服务信息（避免重复域名检查）
        target_service = flow.metadata.get('identified_service')
        if not target_service:
            # 兼容性：如果没有预设服务信息，进行域名检查
            target_service = self._identify_service(flow.request.pretty_host)
            if not target_service:
                return
        
        # 获取对应的提取器
        extractor = self.extractors.get(target_service)
        if not extractor:
            return
        
        # 委托给提取器处理
        try:
            result = extractor.handle_response(flow)
            if result:
                self.extract_count += 1
                # 使用logger替代print
                extract_type = result.get('type', '数据')
                logger.info(f"成功提取 {target_service} {extract_type}")
        except (AttributeError, KeyError) as e:
            logger.error(f"处理响应时出错 ({target_service}): {e}")
        except Exception as e:
            logger.exception(f"处理响应时发生未知错误 ({target_service})")
    
    def _identify_service(self, host: str) -> Optional[str]:
        """识别主机属于哪个服务"""
        for service_name, service_config in self.services_config.items():
            domains = service_config.get('domains', [])
            if any(domain in host.lower() for domain in domains):
                return service_name
        return None
    
    def done(self):
        """代理关闭时的统计和资源清理"""
        try:
            # 清理所有提取器资源
            for service_name, extractor in self.extractors.items():
                if hasattr(extractor, 'cleanup'):
                    extractor.cleanup()
                    logger.debug(f"已清理 {service_name} 提取器资源")
            
            # 会话统计
            if self.csv_manager:
                self.csv_manager.end_session(self.session_id, self.request_count, self.extract_count)
            
            logger.info("进程注入会话结束")
            logger.info(f"总请求: {self.request_count}")
            logger.info(f"成功提取: {self.extract_count}")
            print("=" * 60)  # 保留分隔符便于用户识别会话结束
            
        except Exception as e:
            logger.error(f"会话清理时出错: {e}")

# mitmproxy插件入口
addons = [ProcessInject()]