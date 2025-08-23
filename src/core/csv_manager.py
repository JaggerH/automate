import csv
import time
import os
from pathlib import Path
from typing import Optional, Dict, List
import json

class CSVStatusManager:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        
        # 确保logs目录存在
        (self.data_dir / "logs").mkdir(exist_ok=True)
        
        self.status_file = self.data_dir / "extraction_status.csv"
        self.sessions_file = self.data_dir / "proxy_sessions.csv" 
        
        self._init_files()
    
    def _init_files(self):
        """初始化CSV文件"""
        # 状态文件
        if not self.status_file.exists():
            with open(self.status_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'service', 'last_extract_time', 'extract_count', 
                    'current_status', 'next_check_time', 'output_file'
                ])
        
        # 会话文件  
        if not self.sessions_file.exists():
            with open(self.sessions_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'session_id', 'start_time', 'end_time', 'upstream_proxy',
                    'total_requests', 'extracts_made', 'status'
                ])
    
    def get_last_extract_time(self, service: str) -> Optional[float]:
        """获取服务最后提取时间"""
        try:
            with open(self.status_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['service'] == service:
                        return float(row['last_extract_time']) if row['last_extract_time'] else None
        except Exception as e:
            print(f"读取提取时间失败: {e}")
        return None
    
    def should_extract(self, service: str, interval: int = 7200) -> bool:
        """判断是否应该提取Cookie"""
        last_time = self.get_last_extract_time(service)
        if not last_time:
            return True
        
        return time.time() - last_time > interval
    
    def update_extract_status(self, service: str, extract_time: float, output_file: str):
        """更新提取状态"""
        # 读取现有数据
        rows = []
        service_found = False
        
        try:
            with open(self.status_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['service'] == service:
                        # 更新现有服务记录
                        row['last_extract_time'] = str(int(extract_time))
                        row['extract_count'] = str(int(row['extract_count']) + 1 if row['extract_count'] else 1)
                        row['current_status'] = 'active'
                        row['next_check_time'] = str(int(extract_time + 7200))  # 2小时后
                        row['output_file'] = output_file
                        service_found = True
                    rows.append(row)
        except Exception:
            pass
        
        # 如果是新服务，添加记录
        if not service_found:
            rows.append({
                'service': service,
                'last_extract_time': str(int(extract_time)),
                'extract_count': '1', 
                'current_status': 'active',
                'next_check_time': str(int(extract_time + 7200)),
                'output_file': output_file
            })
        
        # 写回文件
        try:
            with open(self.status_file, 'w', newline='', encoding='utf-8') as f:
                if rows:
                    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(rows)
                    
            print(f"更新状态: {service} -> {time.ctime(extract_time)}")
        except Exception as e:
            print(f"更新状态失败: {e}")
    
    def start_session(self, session_id: str, upstream_proxy: str = None) -> None:
        """开始新会话"""
        try:
            with open(self.sessions_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    session_id,
                    int(time.time()),
                    '',  # end_time为空
                    upstream_proxy or 'direct',
                    0,   # total_requests
                    0,   # extracts_made  
                    'running'
                ])
        except Exception as e:
            print(f"开始会话失败: {e}")
    
    def end_session(self, session_id: str, total_requests: int, extracts_made: int):
        """结束会话"""
        # 读取所有会话记录
        rows = []
        try:
            with open(self.sessions_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['session_id'] == session_id:
                        row['end_time'] = str(int(time.time()))
                        row['total_requests'] = str(total_requests)
                        row['extracts_made'] = str(extracts_made)
                        row['status'] = 'completed'
                    rows.append(row)
        except Exception as e:
            print(f"读取会话记录失败: {e}")
            return
        
        # 写回文件
        try:
            with open(self.sessions_file, 'w', newline='', encoding='utf-8') as f:
                if rows:
                    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                    writer.writeheader() 
                    writer.writerows(rows)
        except Exception as e:
            print(f"结束会话失败: {e}")
    
    def get_service_stats(self) -> Dict:
        """获取服务统计信息"""
        stats = {}
        try:
            with open(self.status_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    service = row['service']
                    stats[service] = {
                        'last_extract': time.ctime(float(row['last_extract_time'])) if row['last_extract_time'] else 'Never',
                        'extract_count': int(row['extract_count']) if row['extract_count'] else 0,
                        'status': row['current_status'],
                        'output_file': row['output_file']
                    }
        except Exception as e:
            print(f"获取统计信息失败: {e}")
        return stats
    
    def cleanup_old_sessions(self, days: int = 7):
        """清理旧会话记录"""
        cutoff_time = time.time() - (days * 24 * 3600)
        
        rows = []
        try:
            with open(self.sessions_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    start_time = float(row['start_time']) if row['start_time'] else 0
                    if start_time > cutoff_time:
                        rows.append(row)
        except Exception as e:
            print(f"清理会话记录失败: {e}")
            return
        
        # 重写文件
        try:
            with open(self.sessions_file, 'w', newline='', encoding='utf-8') as f:
                if rows:
                    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(rows)
            
            print(f"清理了 {days} 天前的会话记录")
        except Exception as e:
            print(f"写入清理后的会话记录失败: {e}")