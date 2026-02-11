"""
数据模型定义
"""
import sqlite3
import json
from datetime import datetime
from typing import Optional, Dict, Any


class Database:
    """SQLite 数据库管理"""
    
    def __init__(self, db_path: str = "gdrive_sync.db"):
        self.db_path = db_path
        self.init_database()
    
    def get_connection(self):
        """获取数据库连接"""
        return sqlite3.connect(self.db_path)
    
    def init_database(self):
        """初始化数据库表"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 任务配置表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                gdrive_folder_id TEXT NOT NULL,
                local_folder TEXT NOT NULL,
                filters TEXT,
                bandwidth_limit INTEGER DEFAULT 0,
                schedule TEXT,
                thread_count INTEGER DEFAULT 3,
                retry_count INTEGER DEFAULT 3,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 下载进度表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS download_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER,
                file_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                local_path TEXT NOT NULL,
                total_size INTEGER DEFAULT 0,
                downloaded_size INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                md5_checksum TEXT,
                error_count INTEGER DEFAULT 0,
                last_error TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES sync_tasks (id)
            )
        """)
        
        # 错误日志表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS error_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER,
                file_path TEXT NOT NULL,
                error_type TEXT NOT NULL,
                error_message TEXT,
                retry_count INTEGER DEFAULT 0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES sync_tasks (id)
            )
        """)
        
        conn.commit()
        conn.close()


class SyncTask:
    """同步任务模型"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def create(self, name: str, gdrive_folder_id: str, local_folder: str, 
               filters: Optional[Dict] = None,
               bandwidth_limit: int = 0,
               schedule: Optional[str] = None,
               thread_count: int = 3,
               retry_count: int = 3) -> int:
        """创建新任务"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        filters_json = json.dumps(filters) if filters else None
        
        cursor.execute("""
            INSERT INTO sync_tasks (name, gdrive_folder_id, local_folder, filters, 
                                   bandwidth_limit, schedule, thread_count, retry_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, gdrive_folder_id, local_folder, filters_json, 
              bandwidth_limit, schedule, thread_count, retry_count))
        
        task_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return task_id
    
    def get(self, task_id: int) -> Optional[Dict[str, Any]]:
        """获取任务详情"""
        conn = self.db.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM sync_tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            task = dict(row)
            if task['filters']:
                task['filters'] = json.loads(task['filters'])
            return task
        return None
    
    def get_all(self):
        """获取所有任务"""
        conn = self.db.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM sync_tasks ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()
        
        tasks = []
        for row in rows:
            task = dict(row)
            if task['filters']:
                task['filters'] = json.loads(task['filters'])
            tasks.append(task)
        return tasks
    
    def update(self, task_id: int, **kwargs):
        """更新任务配置"""
        if 'filters' in kwargs and kwargs['filters']:
            kwargs['filters'] = json.dumps(kwargs['filters'])
        
        set_clause = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values()) + [task_id]
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(f"UPDATE sync_tasks SET {set_clause} WHERE id = ?", values)
        conn.commit()
        conn.close()
    
    def delete(self, task_id: int):
        """删除任务"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sync_tasks WHERE id = ?", (task_id,))
        cursor.execute("DELETE FROM download_progress WHERE task_id = ?", (task_id,))
        cursor.execute("DELETE FROM error_logs WHERE task_id = ?", (task_id,))
        conn.commit()
        conn.close()


class DownloadProgress:
    """下载进度模型"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def create(self, task_id: int, file_id: str, file_path: str, 
               local_path: str, total_size: int, md5_checksum: str) -> int:
        """创建下载记录"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO download_progress 
            (task_id, file_id, file_path, local_path, total_size, md5_checksum)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (task_id, file_id, file_path, local_path, total_size, md5_checksum))
        
        record_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return record_id
    
    def update_progress(self, record_id: int, downloaded_size: int, status: str = 'downloading'):
        """更新下载进度"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE download_progress 
            SET downloaded_size = ?, status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (downloaded_size, status, record_id))
        
        conn.commit()
        conn.close()
    
    def mark_completed(self, record_id: int):
        """标记为已完成"""
        self.update_progress(record_id, -1, 'completed')
    
    def mark_failed(self, record_id: int, error_msg: str):
        """标记为失败"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE download_progress 
            SET status = 'failed', last_error = ?, error_count = error_count + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (error_msg, record_id))
        
        conn.commit()
        conn.close()
    
    def get_by_file_id(self, task_id: int, file_id: str) -> Optional[Dict]:
        """根据文件ID获取进度"""
        conn = self.db.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM download_progress 
            WHERE task_id = ? AND file_id = ?
        """, (task_id, file_id))
        
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def get_pending(self, task_id: int):
        """获取待下载/未完成的文件"""
        conn = self.db.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM download_progress 
            WHERE task_id = ? AND status IN ('pending', 'downloading')
            ORDER BY id
        """, (task_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_stats(self, task_id: int) -> Dict[str, int]:
        """获取任务统计信息"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status IN ('pending', 'downloading') THEN 1 ELSE 0 END) as pending
            FROM download_progress 
            WHERE task_id = ?
        """, (task_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        return {
            'total': row[0] or 0,
            'completed': row[1] or 0,
            'failed': row[2] or 0,
            'pending': row[3] or 0
        }


class ErrorLog:
    """错误日志模型"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def create(self, task_id: int, file_path: str, error_type: str, 
               error_message: str, retry_count: int = 0):
        """记录错误"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO error_logs (task_id, file_path, error_type, error_message, retry_count)
            VALUES (?, ?, ?, ?, ?)
        """, (task_id, file_path, error_type, error_message, retry_count))
        
        conn.commit()
        conn.close()
    
    def get_by_task(self, task_id: int):
        """获取任务的所有错误日志"""
        conn = self.db.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM error_logs 
            WHERE task_id = ?
            ORDER BY timestamp DESC
        """, (task_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def export_to_csv(self, task_id: int, output_path: str):
        """导出错误日志为CSV"""
        import csv
        
        logs = self.get_by_task(task_id)
        
        with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
            if logs:
                writer = csv.DictWriter(f, fieldnames=logs[0].keys())
                writer.writeheader()
                writer.writerows(logs)
