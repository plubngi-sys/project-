"""เก็บผล AI ที่รอส่งในเครื่อง โดยยืนยันลงดิสก์ก่อนเริ่มส่งไป PostgreSQL"""
import json
import sqlite3
from pathlib import Path
from uuid import uuid4


class SummaryOutbox:
    def __init__(self, path, scope):
        self.path = Path(path)
        self.scope = scope
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._execute('''CREATE TABLE IF NOT EXISTS pending (
                request_id TEXT PRIMARY KEY, scope TEXT NOT NULL,
                document_id INTEGER NOT NULL, file_hash TEXT NOT NULL,
                page_number INTEGER NOT NULL, model_name TEXT NOT NULL,
                content TEXT NOT NULL)''')

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA synchronous=FULL')
        return conn

    def _execute(self, sql, args=(), fetch=False):
        conn = self.connect()
        try:
            with conn:
                cursor = conn.execute(sql, args)
                return [dict(row) for row in cursor.fetchall()] if fetch else None
        finally:
            conn.close()

    def enqueue(self, document_id, file_hash, page_number, model_name, content):
        request_id = str(uuid4())
        self._execute('INSERT INTO pending VALUES (?, ?, ?, ?, ?, ?, ?)',
                      (request_id, self.scope, document_id, file_hash,
                       page_number, model_name, content))
        return request_id

    def items(self):
        return self._execute('SELECT * FROM pending WHERE scope=? ORDER BY rowid',
                             (self.scope,), fetch=True)

    def acknowledge(self, request_id):
        self._execute('DELETE FROM pending WHERE scope=? AND request_id=?',
                      (self.scope, request_id))

    def export(self, path):
        # ส่งออกเฉพาะผลที่รอส่งของฐานข้อมูลนี้ ไม่มี URL หรือรหัสผ่าน
        Path(path).write_text(json.dumps(self.items(), ensure_ascii=False, indent=2),
                              encoding='utf-8')
