#!/usr/bin/env python3
"""
NetEase Cloud Music EAPI Debug Addon
网易云音乐EAPI调试插件

专门用于PID注入模式，监控并解密EAPI请求/响应
自动保存解密后的播放列表数据到JSON文件
"""
from mitmproxy import http
import time
import sys
import os
import json
import re
from pathlib import Path

# Windows控制台编码设置
if os.name == 'nt':
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

# 延迟导入EAPI解密工具
NeteaseCrypto = None
try:
    from src.utils.netease_crypto import NeteaseCrypto
except ImportError as e:
    print(f"Warning: Could not import NeteaseCrypto: {e}")
    print("EAPI decryption will be disabled")

class DebugAddon:
    def __init__(self):
        self.request_count = 0
        self.playlist_request_count = 0
        self.post_request_count = 0
        
        # 目标域名
        self.target_domains = [
            'music.163.com',
            'interface.music.163.com', 
            'interface3.music.163.com',
            'api.music.163.com'
        ]
        
        # 创建调试输出目录
        self.debug_path = Path(project_root) / "data" / "debug"
        self.debug_path.mkdir(parents=True, exist_ok=True)
        
        # 初始化EAPI解密工具
        self.crypto = NeteaseCrypto() if NeteaseCrypto else None
        
    def load(self, loader):
        """mitmproxy加载时初始化"""
        import logging
        logging.getLogger().setLevel(logging.WARNING)
        
    def _is_target_domain(self, host: str) -> bool:
        """检查是否为目标域名"""
        return any(domain in host.lower() for domain in self.target_domains)
    
    def _is_image_request(self, path: str) -> bool:
        """检查是否为图片请求"""
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.ico']
        return any(path.lower().endswith(ext) for ext in image_extensions)
    
    def _is_eapi_request(self, path: str) -> bool:
        """检查是否为EAPI请求"""
        return '/eapi/' in path.lower()
    
    def request(self, flow: http.HTTPFlow):
        """处理HTTP请求"""
        self.request_count += 1
        
        # 只处理目标域名
        if not self._is_target_domain(flow.request.pretty_host):
            return
        
        # 过滤GET图片请求
        if flow.request.method == 'GET' and self._is_image_request(flow.request.path):
            return
        
        # 检查是否为播放列表API
        is_playlist_api = 'playlist' in flow.request.path.lower()
        if is_playlist_api:
            self.playlist_request_count += 1
        
        # 处理POST请求
        if flow.request.method == 'POST':
            self.post_request_count += 1
            self._save_post_request(flow)
            
            # EAPI播放列表API特殊处理
            if is_playlist_api and self._is_eapi_request(flow.request.path):
                print(f"🎯 [EAPI播放列表] {flow.request.path}")
                
                # 尝试解密请求内容获取播放列表ID
                if flow.request.content and self.crypto:
                    try:
                        content = flow.request.content.decode('utf-8')
                        if content.startswith('params='):
                            encrypted_hex = content[7:]  # 去掉'params='
                            result = self.crypto.eapi_decrypt(encrypted_hex)
                            
                            if result.get('success'):
                                data = result.get('data')
                                if isinstance(data, dict) and 'id' in data:
                                    playlist_id = data['id']
                                    print(f"🎵 检测到播放列表ID: {playlist_id}")
                                    flow.metadata['target_playlist_id'] = str(playlist_id)
                    except Exception as e:
                        print(f"⚠️ 解密请求失败: {e}")
    
    def response(self, flow: http.HTTPFlow):
        """处理HTTP响应"""
        # 保存POST响应到JSON文件
        debug_save_path = flow.metadata.get('debug_save_path')
        debug_request_data = flow.metadata.get('debug_request_data')
        
        if debug_save_path and debug_request_data and flow.response:
            self._save_post_response(debug_save_path, debug_request_data, flow)
    
    def _save_post_request(self, flow: http.HTTPFlow):
        """保存POST请求数据到JSON文件"""
        try:
            timestamp = int(time.time() * 1000)  # 毫秒时间戳
            filename = f"post_request_{self.post_request_count}_{timestamp}.json"
            filepath = self.debug_path / filename
            
            # 构建请求数据
            request_data = {
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'url': flow.request.pretty_url,
                'method': flow.request.method,
                'domain': flow.request.pretty_host,
                'path': flow.request.path,
                'headers': {k: v for k, v in flow.request.headers.items()},
                'cookies': {k: str(v) for k, v in flow.request.cookies.items()} if flow.request.cookies else {},
                'payload': None,
                'response': None
            }
            
            # 处理请求载荷
            if flow.request.content:
                try:
                    content = flow.request.content.decode('utf-8')
                    # 尝试解析为JSON
                    try:
                        request_data['payload'] = json.loads(content)
                        request_data['payload_type'] = 'json'
                    except json.JSONDecodeError:
                        # 保存原始字符串，可能是加密数据
                        request_data['payload'] = content
                        if content.startswith('params='):
                            request_data['payload_type'] = 'encrypted_form'
                        else:
                            request_data['payload_type'] = 'form_data'
                except UnicodeDecodeError:
                    request_data['payload'] = "[二进制数据]"
                    request_data['payload_type'] = 'binary'
                except Exception as e:
                    request_data['payload'] = f"[解码错误: {e}]"
                    request_data['payload_type'] = 'error'
            
            # 标记为等待响应
            flow.metadata['debug_save_path'] = str(filepath)
            flow.metadata['debug_request_data'] = request_data
            
        except Exception as e:
            print(f"❌ 保存POST请求时出错: {e}")
    
    def _save_post_response(self, filepath: str, request_data: dict, flow: http.HTTPFlow):
        """保存POST响应数据"""
        try:
            # 添加响应数据
            request_data['response'] = {
                'status_code': flow.response.status_code,
                'headers': {k: v for k, v in flow.response.headers.items()},
                'cookies': {k: str(v) for k, v in flow.response.cookies.items()} if flow.response.cookies else {},
                'content': None
            }
            
            # 处理响应内容
            if flow.response.content:
                try:
                    content = flow.response.content.decode('utf-8')
                    # 尝试解析为JSON
                    try:
                        request_data['response']['content'] = json.loads(content)
                        request_data['response']['content_type'] = 'json'
                    except json.JSONDecodeError:
                        # 可能是加密响应
                        request_data['response']['content'] = content
                        request_data['response']['content_type'] = 'encrypted'
                except UnicodeDecodeError:
                    # 对于EAPI二进制响应，转换为hex字符串
                    if 'eapi' in flow.request.path.lower():
                        import binascii
                        hex_content = binascii.hexlify(flow.response.content).decode('ascii')
                        request_data['response']['content'] = hex_content
                        request_data['response']['content_type'] = 'eapi_hex'
                        print(f"📦 EAPI二进制响应已转换为hex (长度: {len(hex_content)})")
                        
                        # 如果这是播放列表响应，尝试解密
                        if flow.metadata.get('target_playlist_id') and self.crypto:
                            playlist_id = flow.metadata['target_playlist_id']
                            print(f"🔓 尝试解密播放列表 {playlist_id} 的响应...")
                            
                            decrypt_result = self.crypto.eapi_decrypt(hex_content)
                            if decrypt_result.get('success'):
                                # 解密成功，尝试解析JSON
                                decrypted_data = decrypt_result.get('data')
                                if isinstance(decrypted_data, str):
                                    try:
                                        playlist_data = json.loads(decrypted_data)
                                        if isinstance(playlist_data, dict) and 'playlist' in playlist_data:
                                            playlist = playlist_data['playlist']
                                            track_count = playlist.get('trackCount', 0)
                                            playlist_name = playlist.get('name', 'N/A')
                                            print(f"✅ 播放列表解密成功: {playlist_name} ({track_count}首歌)")
                                    except json.JSONDecodeError:
                                        print(f"⚠️ 解密成功但JSON解析失败")
                            else:
                                print(f"❌ 响应解密失败: {decrypt_result.get('error', 'Unknown')}")
                    else:
                        request_data['response']['content'] = "[二进制响应]"
                        request_data['response']['content_type'] = 'binary'
                except Exception as e:
                    request_data['response']['content'] = f"[解码错误: {e}]"
                    request_data['response']['content_type'] = 'error'
            
            # 保存到文件
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(request_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"❌ 保存POST响应时出错: {e}")
    
    def done(self):
        """代理关闭时的统计"""
        print(f"\n📊 EAPI解密会话结束")
        print(f"总请求: {self.request_count}")
        print(f"POST请求: {self.post_request_count}")
        print(f"播放列表API: {self.playlist_request_count}")
        print(f"JSON文件保存至: {self.debug_path}")
        print("=" * 60)

# mitmproxy插件入口
addons = [DebugAddon()]