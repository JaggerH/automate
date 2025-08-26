from abc import ABC, abstractmethod
from typing import Dict, Optional, Any
import json
import time
from pathlib import Path

class BaseExtractor(ABC):
    """Cookie提取器基类"""
    
    def __init__(self, service_name: str, config: dict):
        self.service_name = service_name
        self.config = config
        self.output_file = config.get('output_file', f'data/outputs/{service_name}_cookie.json')
