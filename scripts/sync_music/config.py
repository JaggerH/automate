import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Union, List
from dataclasses import dataclass, field

@dataclass
class SyncConfig:
    """同步配置类"""
    
    # 目录配置
    user_dir: Union[str, List[str]] = ""
    input_dir: str = ""  
    output_dir: str = ""
    
    # JSON文件配置
    json_file: Optional[str] = None
    json_dir: Optional[str] = None
    
    # 数据库配置
    database_path: str = "music_sync.db"
    database_url: Optional[str] = None
    
    # 文件处理配置
    supported_extensions: list = field(default_factory=lambda: ['.mp3', '.flac'])
    max_bitrate_preference: bool = True
    copy_files: bool = True
    overwrite_existing: bool = False
    
    # 输出配置
    verbose: bool = True
    show_progress: bool = True
    log_level: str = "INFO"
    
    # 高级配置
    enable_file_hash: bool = True
    enable_bitrate_extraction: bool = True
    batch_size: int = 100
    max_workers: int = 4

class ConfigLoader:
    """配置加载器"""
    
    DEFAULT_CONFIG_PATHS = [
        "config.yaml",
        "sync_music_config.yaml", 
        os.path.expanduser("~/.sync_music/config.yaml"),
        "/etc/sync_music/config.yaml"
    ]
    
    @staticmethod
    def load_config(config_path: Optional[str] = None) -> SyncConfig:
        """加载配置文件"""
        if config_path:
            # 使用指定的配置文件
            if not os.path.exists(config_path):
                raise FileNotFoundError(f"配置文件不存在: {config_path}")
            return ConfigLoader._load_from_file(config_path)
        
        # 按优先级查找配置文件
        for path in ConfigLoader.DEFAULT_CONFIG_PATHS:
            if os.path.exists(path):
                return ConfigLoader._load_from_file(path)
        
        # 如果没有找到配置文件，返回默认配置
        return SyncConfig()
    
    @staticmethod
    def _load_from_file(config_path: str) -> SyncConfig:
        """从文件加载配置"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f) or {}
            
            # 展开环境变量
            config_data = ConfigLoader._expand_env_vars(config_data)
            
            # 验证必要的目录
            ConfigLoader._validate_config(config_data)
            
            return SyncConfig(**config_data)
            
        except yaml.YAMLError as e:
            raise ValueError(f"YAML格式错误: {e}")
        except TypeError as e:
            raise ValueError(f"配置参数错误: {e}")
    
    @staticmethod
    def _expand_env_vars(config_data: Dict[str, Any]) -> Dict[str, Any]:
        """展开环境变量"""
        expanded = {}
        
        for key, value in config_data.items():
            if isinstance(value, str):
                expanded[key] = os.path.expandvars(value)
            elif isinstance(value, dict):
                expanded[key] = ConfigLoader._expand_env_vars(value)
            else:
                expanded[key] = value
                
        return expanded
    
    @staticmethod
    def _validate_config(config_data: Dict[str, Any]):
        """验证配置"""
        required_dirs = ['user_dir', 'input_dir', 'output_dir']
        
        for dir_key in required_dirs:
            if dir_key in config_data and config_data[dir_key]:
                dir_value = config_data[dir_key]
                
                # output_dir 可以不存在（会自动创建）
                if dir_key == 'output_dir':
                    continue
                
                # 处理user_dir的列表格式
                if dir_key == 'user_dir':
                    if isinstance(dir_value, list):
                        for i, dir_path in enumerate(dir_value):
                            if not os.path.exists(dir_path):
                                print(f"警告: 用户目录[{i}]不存在 - {dir_path}")
                    else:
                        if not os.path.exists(dir_value):
                            print(f"警告: 目录不存在 - {dir_key}: {dir_value}")
                else:
                    if not os.path.exists(dir_value):
                        print(f"警告: 目录不存在 - {dir_key}: {dir_value}")
    
    @staticmethod
    def create_default_config(config_path: str = "config.yaml"):
        """创建默认配置文件"""
        default_config = {
            'user_dir': [
                os.path.expanduser("~/Music"),
                os.path.expanduser("~/Documents/Music")
            ],
            'input_dir': "./input_music",
            'output_dir': "./output_music",
            'json_dir': "./playlists",
            'database_path': "music_sync.db",
            'supported_extensions': ['.mp3', '.flac'],
            'max_bitrate_preference': True,
            'copy_files': True,
            'overwrite_existing': False,
            'verbose': True,
            'show_progress': True,
            'log_level': "INFO",
            'enable_file_hash': True,
            'enable_bitrate_extraction': True,
            'batch_size': 100,
            'max_workers': 4
        }
        
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)
        
        print(f"已创建默认配置文件: {config_path}")
    
    @staticmethod
    def merge_config_with_args(config: SyncConfig, args) -> SyncConfig:
        """合并配置文件和命令行参数（命令行参数优先）"""
        if args.user_dir:
            config.user_dir = args.user_dir
        if args.input_dir:
            config.input_dir = args.input_dir
        if args.output_dir:
            config.output_dir = args.output_dir
        if args.json_file:
            config.json_file = args.json_file
        if args.json_dir:
            config.json_dir = args.json_dir
        if args.database:
            config.database_path = args.database
        if hasattr(args, 'verbose') and args.verbose is not None:
            config.verbose = args.verbose
            
        return config
    
    @staticmethod
    def get_database_url(config: SyncConfig) -> str:
        """获取数据库URL"""
        if config.database_url:
            return config.database_url
        else:
            return f"sqlite:///{config.database_path}"