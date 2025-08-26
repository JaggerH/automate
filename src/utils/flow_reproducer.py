#!/usr/bin/env python3
"""
HTTPFlow 重建器
从debug JSON数据重建mitmproxy.http.HTTPFlow对象并复现提取过程
"""

import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
from mitmproxy.http import HTTPFlow, Request, Response, Headers
from mitmproxy.connection import Client, Server
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)

class FlowReproducer:
    """HTTPFlow重建器 - 处理整个文件夹的调试数据"""
    
    def __init__(self, debug_data_dir: str):
        """
        初始化Flow重建器
        
        Args:
            debug_data_dir: 包含调试JSON文件的目录路径
        """
        self.debug_data_dir = Path(debug_data_dir)
        if not self.debug_data_dir.exists():
            raise FileNotFoundError(f"调试数据目录不存在: {debug_data_dir}")
    
    def load_json_data(self, json_file: str) -> Dict[str, Any]:
        """加载JSON调试数据"""
        filepath = self.debug_data_dir / json_file
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def create_mock_client(self) -> Client:
        """创建模拟客户端连接"""
        return Client(
            peername=("127.0.0.1", 12345),
            sockname=("127.0.0.1", 8080),
            timestamp_start=time.time(),
            timestamp_tls_setup=None,
            sni=None,
            cipher=None,
            alpn=None,
            certificate_list=[]
        )
    
    def create_mock_server(self, original_domain: str, url: str) -> Server:
        """根据原始域名创建模拟服务器连接 - 保持原始域名"""
        parsed = urlparse(url)
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        
        return Server(
            address=(original_domain, port),  # 使用原始域名
            peername=("127.0.0.1", port),     # mock的实际连接IP
            sockname=None,
            timestamp_start=time.time(),
            timestamp_tls_setup=time.time() if parsed.scheme == 'https' else None,
            sni=original_domain if parsed.scheme == 'https' else None,
            cipher=None,
            alpn=b'http/1.1',
            certificate_list=[]
        )
    
    def json_to_headers(self, headers_dict: Dict[str, str]) -> Headers:
        """将JSON headers转换为mitmproxy Headers"""
        return Headers([(k.encode() if isinstance(k, str) else k, 
                        v.encode() if isinstance(v, str) else v) 
                       for k, v in headers_dict.items()])
    
    def recreate_request(self, data: Dict[str, Any]) -> Request:
        """从JSON数据重建HTTPRequest - 保持原始Host信息"""
        parsed_url = urlparse(data['url'])
        original_domain = data['domain']
        
        # 构建请求内容 - 优先使用原始数据
        # content = b''
        # if 'payload_raw' in data:
        #     content = data['payload_raw'].encode('utf-8')
        # elif data.get('payload'):
        #     if data.get('payload_type') == 'json':
        #         content = json.dumps(data['payload'], ensure_ascii=False).encode('utf-8')
        #     elif isinstance(data['payload'], str):
        #         content = data['payload'].encode('utf-8')
        content = data['payload_raw'].encode('utf-8')
        
        return Request(
            host=original_domain,  # 保持原始域名
            port=parsed_url.port or (443 if parsed_url.scheme == 'https' else 80),
            method=data['method'].encode(),
            scheme=parsed_url.scheme.encode(),
            authority=original_domain.encode(),
            path=data['path'].encode(),
            http_version=b"HTTP/1.1",
            headers=self.json_to_headers(data['headers']),
            content=content,
            trailers=None,
            timestamp_start=time.time(),
            timestamp_end=time.time()
        )
    
    def recreate_response(self, data: Dict[str, Any]) -> Optional[Response]:
        """从JSON数据重建HTTPResponse"""
        response_data = data.get('response')
        if not response_data:
            return None
        
        # 构建响应内容 - 优先使用原始数据
        content = response_data['content_raw'].encode('utf-8')
        
        return Response(
            http_version=b"HTTP/1.1",
            status_code=response_data['status_code'],
            reason=b"OK",
            headers=self.json_to_headers(response_data['headers']),
            content=content,
            trailers=None,
            timestamp_start=time.time(),
            timestamp_end=time.time()
        )
    
    def recreate_flow(self, json_file: str) -> HTTPFlow:
        """从JSON文件重建完整的HTTPFlow"""
        data = self.load_json_data(json_file)
        
        # 创建连接对象
        client = self.create_mock_client()
        server = self.create_mock_server(data['domain'], data['url'])
        
        # 创建Flow对象
        flow = HTTPFlow(client, server)
        flow.request = self.recreate_request(data)
        flow.response = self.recreate_response(data)
        
        return flow
    
    def reproduce_all_flows(self, file_pattern: str = "post_*.json") -> Dict[str, Any]:
        """重现文件夹中所有匹配的Flow"""
        logger.info(f"开始批量重现Flow，目录: {self.debug_data_dir}")
        
        # 查找匹配的文件
        json_files = list(self.debug_data_dir.glob(file_pattern))
        if not json_files:
            logger.warning(f"未找到匹配文件: {file_pattern}")
            return {}
        
        logger.info(f"找到 {len(json_files)} 个文件")
        
        # 创建提取器
        extractor = self.create_extractor()
        
        # 批量处理
        all_results = {}
        success_count = 0
        error_count = 0
        
        for json_file in json_files:
            file_key = json_file.name
            result = self.reproduce_single_flow(file_key, extractor)
            
            if result:
                all_results[file_key] = result
                success_count += 1
            else:
                error_count += 1
        
        # 统计信息
        summary = {
            'total_files': len(json_files),
            'success_count': success_count,
            'error_count': error_count,
            'results': all_results
        }
        
        logger.info(f"批量重现完成: 成功 {success_count}, 失败 {error_count}")
        return summary
    
    def get_file_summary(self) -> Dict[str, Any]:
        """获取文件夹中调试文件的摘要信息"""
        json_files = list(self.debug_data_dir.glob("post_*.json"))
        
        summary = {
            'total_files': len(json_files),
            'files': []
        }
        
        for json_file in json_files:
            try:
                data = self.load_json_data(json_file.name)
                file_info = {
                    'filename': json_file.name,
                    'domain': data.get('domain', 'N/A'),
                    'path': data.get('path', 'N/A'),
                    'method': data.get('method', 'N/A'),
                    'timestamp': data.get('timestamp', 'N/A'),
                    'has_response': bool(data.get('response'))
                }
                summary['files'].append(file_info)
            except Exception as e:
                logger.warning(f"读取文件信息失败 ({json_file.name}): {e}")
        
        return summary
    
    def reproduce_single_flow(self, json_file: str, extractor=None) -> Optional[dict]:
        """重现单个Flow的提取过程"""
        try:
            logger.info(f"重现Flow: {json_file}")
            
            # 重建Flow对象
            flow = self.recreate_flow(json_file)
            
            # 创建提取器
            if extractor is None:
                extractor = self.create_extractor()
            
            results = {}
            
            # 处理请求
            if hasattr(extractor, 'handle_request'):
                try:
                    request_result = extractor.handle_request(flow)
                    if request_result:
                        results['request'] = request_result
                        logger.info(f"Request处理成功: {json_file}")
                except Exception as e:
                    logger.error(f"Request处理失败 ({json_file}): {e}")
            
            # 处理响应
            if flow.response and hasattr(extractor, 'handle_response'):
                try:
                    response_result = extractor.handle_response(flow)
                    if response_result:
                        results['response'] = response_result
                        logger.info(f"Response处理成功: {json_file}")
                except Exception as e:
                    import traceback
                    logger.error(f"Response处理失败 ({json_file}): {e}")
                    print(traceback.format_exc())
                    
            
            return results if results else None
            
        except Exception as e:
            logger.error(f"重现Flow失败 ({json_file}): {e}")
            return None
        
    def create_extractor(self):
        """创建默认的NetEase提取器（待实现）"""
        raise NotImplementedError("refactor_flow_reproducer.py: create_extractor 需要实现")