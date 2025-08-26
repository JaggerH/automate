"""
网易云音乐EAPI加密解密工具
基于NeteaseCloudMusicApi的crypto.js实现
"""
import json
import hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import binascii

from mitmproxy.http import HTTPFlow

class NeteaseCrypto:
    """网易云音乐加密解密工具类"""
    
    def __init__(self):
        self.eapi_key = b'e82ckenh8dichen8'  # EAPI密钥
        self.preset_key = b'0CoJUm6Qyw8W8jud'  # WEAPI预设密钥
        self.iv = b'0102030405060708'  # 初始化向量
    
    def eapi_decrypt(self, encrypted_hex: str|bytes) -> dict:
        """
        解密EAPI响应数据
        
        Args:
            encrypted_hex: 十六进制加密字符串 or binary hex
            
        Returns:
            解密后的数据字典
        """
        if isinstance(encrypted_hex, bytes):
            encrypted_hex = binascii.hexlify(encrypted_hex).decode('ascii') # binary to hex
        encrypted_data = binascii.unhexlify(encrypted_hex) # 十六进制转bytes
        
        # AES-ECB解密
        cipher = AES.new(self.eapi_key, AES.MODE_ECB)
        decrypted = cipher.decrypt(encrypted_data)
        
        # 去除PKCS7填充
        unpadded = unpad(decrypted, 16)
        
        # 转为字符串
        decrypted_text = unpadded.decode('utf-8')
        
        # 解析EAPI数据格式: url-36cd479b6b5-data-36cd479b6b5-md5
        parts = decrypted_text.split('-36cd479b6b5-')
        if len(parts) == 1:
            return json.loads(parts[0])
        else:
            raise ValueError("NeteaseCrypto.content has salt, undefined situation")
            
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
            raise("netease request.content is not match the known pattern")
    
    def decrypt_response_content(self, flow: HTTPFlow) -> dict:
        """
        解密响应内容
        
        Args:
            content: 响应内容字符串
            
        Returns:
            解密结果
        """
        # 响应内容通常直接是十六进制加密数据
        if not flow.response:
            raise ValueError("must use in response, flow does not have a attribute response")
        if not flow.response.content:
            raise ValueError("flow.response does not have a content attribute.")
            
        return self.eapi_decrypt(flow.response.content)
    
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