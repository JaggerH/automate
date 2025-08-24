import yaml
import os
import logging
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class ConfigLoader:
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self._configs = {}
    
    def load_config(self, config_name: str) -> Dict[str, Any]:
        """加载指定的配置文件"""
        if config_name in self._configs:
            return self._configs[config_name]
        
        config_file = self.config_dir / f"{config_name}.yaml"
        
        if not config_file.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_file}")
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            self._configs[config_name] = config
            return config
            
        except yaml.YAMLError as e:
            raise ValueError(f"配置文件格式错误: {config_file}, 错误: {e}")
    
    def get_proxy_config(self) -> Dict[str, Any]:
        """获取代理配置"""
        return self.load_config('proxy_config')
    
    def get_services_config(self) -> Dict[str, Any]:
        """获取服务配置"""
        return self.load_config('services')
    
    def get_logging_config(self) -> Dict[str, Any]:
        """获取日志配置"""
        return self.load_config('logging')
    
    def reload_configs(self):
        """重新加载所有配置"""
        self._configs.clear()
        
    def get_enabled_services(self) -> Dict[str, Dict]:
        """获取启用的服务列表"""
        services = self.get_services_config()['services']
        enabled_services = {name: config for name, config in services.items() if config.get('enabled', True)}
        
        # 验证启用的服务配置
        for service_name, service_config in enabled_services.items():
            self._validate_service_config(service_name, service_config)
        
        return enabled_services
    
    def _validate_service_config(self, service_name: str, config: Dict[str, Any]):
        """验证单个服务配置"""
        required_fields = ['name', 'domains']
        missing_fields = []
        
        for field in required_fields:
            if field not in config:
                missing_fields.append(field)
        
        if missing_fields:
            raise ValueError(f"服务 {service_name} 缺少必需字段: {missing_fields}")
        
        # 验证domains不为空
        if not config['domains'] or not isinstance(config['domains'], list):
            raise ValueError(f"服务 {service_name} 的domains必须是非空列表")
        
        # 验证features配置
        features = config.get('features', {})
        
        # 验证cookie提取配置
        if features.get('extract_cookie', {}).get('enabled'):
            cookie_config = features['extract_cookie']
            if not cookie_config.get('output_file'):
                raise ValueError(f"服务 {service_name} 启用了cookie提取但未指定output_file")
            
            # 验证interval是数字且大于0
            interval = cookie_config.get('interval', 300)
            if not isinstance(interval, (int, float)) or interval <= 0:
                raise ValueError(f"服务 {service_name} 的cookie提取间隔必须是大于0的数字")
        
        # 验证播放列表提取配置
        if features.get('extract_playlist', {}).get('enabled'):
            playlist_config = features['extract_playlist']
            if not playlist_config.get('output_dir'):
                raise ValueError(f"服务 {service_name} 启用了播放列表提取但未指定output_dir")
            
            # 验证target_ids存在且不为空
            target_ids = playlist_config.get('target_ids')
            if not target_ids or not isinstance(target_ids, list):
                raise ValueError(f"服务 {service_name} 启用了播放列表提取但target_ids为空或非列表")
        
        logger.debug(f"服务 {service_name} 配置验证通过")

# 全局配置加载器实例
config_loader = ConfigLoader()