"""
网易云音乐EAPI加密解密工具
基于NeteaseCloudMusicApi的crypto.js实现
"""
import json
import hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import binascii

class NeteaseCrypto:
    """网易云音乐加密解密工具类"""
    
    def __init__(self):
        self.eapi_key = b'e82ckenh8dichen8'  # EAPI密钥
        self.preset_key = b'0CoJUm6Qyw8W8jud'  # WEAPI预设密钥
        self.iv = b'0102030405060708'  # 初始化向量
    
    def eapi_decrypt(self, encrypted_hex: str) -> dict:
        """
        解密EAPI响应数据
        
        Args:
            encrypted_hex: 十六进制加密字符串
            
        Returns:
            解密后的数据字典
        """
        try:
            # 十六进制转bytes
            encrypted_data = binascii.unhexlify(encrypted_hex)
            
            # AES-ECB解密
            cipher = AES.new(self.eapi_key, AES.MODE_ECB)
            decrypted = cipher.decrypt(encrypted_data)
            
            # 去除PKCS7填充
            unpadded = unpad(decrypted, 16)
            
            # 转为字符串
            decrypted_text = unpadded.decode('utf-8')
            
            # 解析EAPI数据格式: url-36cd479b6b5-data-36cd479b6b5-md5
            parts = decrypted_text.split('-36cd479b6b5-')
            if len(parts) >= 3:
                url = parts[0]
                data = parts[1]
                
                # 尝试解析JSON数据
                try:
                    json_data = json.loads(data)
                    return {
                        'success': True,
                        'url': url,
                        'data': json_data,
                        'raw_data': data
                    }
                except json.JSONDecodeError:
                    return {
                        'success': True,
                        'url': url,
                        'data': data,
                        'raw_data': data
                    }
            else:
                return {
                    'success': True,
                    'data': decrypted_text,
                    'raw_data': decrypted_text
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'raw_hex': encrypted_hex[:100] + '...' if len(encrypted_hex) > 100 else encrypted_hex
            }
    
    def extract_playlist_id_from_decrypted(self, decrypted_result: dict) -> str:
        """
        从解密结果中提取播放列表ID
        
        Args:
            decrypted_result: 解密结果字典
            
        Returns:
            播放列表ID或None
        """
        if not decrypted_result.get('success'):
            return None
            
        data = decrypted_result.get('data')
        
        # 方法1: 从JSON数据中提取
        if isinstance(data, dict):
            if 'id' in data:
                return str(data['id'])
            if 'playlist' in data and isinstance(data['playlist'], dict):
                return str(data['playlist'].get('id', ''))
        
        # 方法2: 从原始数据字符串中提取
        raw_data = decrypted_result.get('raw_data', '')
        if isinstance(raw_data, str):
            import re
            # 查找id字段
            id_match = re.search(r'"id"\s*:\s*(\d+)', raw_data)
            if id_match:
                return id_match.group(1)
        
        return None
    
    def decrypt_request_payload(self, payload: str) -> dict:
        """
        解密请求载荷 (params=xxx格式)
        
        Args:
            payload: 请求载荷字符串
            
        Returns:
            解密结果
        """
        if payload.startswith('params='):
            encrypted_hex = payload[7:]  # 去掉'params='
            return self.eapi_decrypt(encrypted_hex)
        else:
            return {'success': False, 'error': 'Invalid payload format'}
    
    def decrypt_response_content(self, content: str) -> dict:
        """
        解密响应内容
        
        Args:
            content: 响应内容字符串
            
        Returns:
            解密结果
        """
        # 响应内容通常直接是十六进制加密数据
        return self.eapi_decrypt(content)
    
    def analyze_debug_data(self, debug_data: dict, target_playlist_ids: list) -> dict:
        """
        分析调试数据，尝试提取播放列表信息
        
        Args:
            debug_data: 调试JSON数据
            target_playlist_ids: 目标播放列表ID列表
            
        Returns:
            分析结果
        """
        result = {
            'found_playlist_id': None,
            'is_target_playlist': False,
            'decrypted_request': None,
            'decrypted_response': None,
            'errors': []
        }
        
        try:
            # 解密请求载荷
            payload = debug_data.get('payload', '')
            if payload and isinstance(payload, str):
                request_result = self.decrypt_request_payload(payload)
                result['decrypted_request'] = request_result
                
                if request_result.get('success'):
                    playlist_id = self.extract_playlist_id_from_decrypted(request_result)
                    if playlist_id:
                        result['found_playlist_id'] = playlist_id
                        result['is_target_playlist'] = playlist_id in [str(pid) for pid in target_playlist_ids]
            
            # 解密响应内容
            response = debug_data.get('response', {})
            if response:
                content = response.get('content', '')
                if content and isinstance(content, str) and content not in ['[无法解码]', '[二进制响应]']:
                    response_result = self.decrypt_response_content(content)
                    result['decrypted_response'] = response_result
                    
                    if response_result.get('success') and not result['found_playlist_id']:
                        playlist_id = self.extract_playlist_id_from_decrypted(response_result)
                        if playlist_id:
                            result['found_playlist_id'] = playlist_id
                            result['is_target_playlist'] = playlist_id in [str(pid) for pid in target_playlist_ids]
                            
        except Exception as e:
            result['errors'].append(f"分析过程出错: {e}")
        
        return result

def test_decrypt():
    """测试解密功能"""
    crypto = NeteaseCrypto()
    
    # 测试样例 (你可以用实际的加密数据替换)
    test_hex = "9E44C61C7604F33F328DE9633B8B0E69"  # 示例数据
    
    result = crypto.eapi_decrypt(test_hex)
    print("解密测试结果:")
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    test_decrypt()