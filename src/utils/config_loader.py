import yaml
import os
from pathlib import Path
from typing import Dict, Any

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
        return {name: config for name, config in services.items() if config.get('enabled', True)}

# 全局配置加载器实例
config_loader = ConfigLoader()