"""แต่ละคำสั่งทำงานในธุรกรรมของตนเอง ห้ามใช้การเชื่อมต่อร่วมกันระหว่างหน้าต่างโปรแกรมกับเธรด AI"""
import hashlib
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


class Database:
    def __init__(self, dsn=None):
        self.dsn = dsn or os.environ.get('DATABASE_URL')
        if not self.dsn:
            raise ValueError('Set DATABASE_URL before connecting to PostgreSQL')

    def connect(self):
        return psycopg.connect(self.dsn, connect_timeout=5, row_factory=dict_row)

    def register_document(self, path, total_pages):
        if total_pages < 1:
            raise ValueError('Document must contain at least one page')
        path = Path(path).resolve()
        digest = hashlib.sha256()
        with path.open('rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(chunk)
        with self.connect() as conn:
            row = conn.execute('''
                INSERT INTO documents(file_name, file_path, file_hash, total_pages)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (file_hash) DO UPDATE SET
                    file_name = EXCLUDED.file_name, file_path = EXCLUDED.file_path
                RETURNING id, total_pages
            ''', (path.name, str(path), digest.hexdigest(), total_pages)).fetchone()
            if row['total_pages'] != total_pages:
                raise ValueError('Page count differs for identical file contents')
            conn.execute('''
                INSERT INTO document_pages(document_id, page_number)
                SELECT %s, generate_series(1, %s) ON CONFLICT DO NOTHING
            ''', (row['id'], total_pages))
            return row['id']

    def list_documents(self):
        with self.connect() as conn:
            return conn.execute('SELECT * FROM documents ORDER BY id DESC').fetchall()

    def get_note(self, document_id, page_number):
        with self.connect() as conn:
            row = conn.execute('SELECT content FROM notes WHERE document_id=%s AND page_number=%s',
                               (document_id, page_number)).fetchone()
            return row['content'] if row else ''

    def save_note(self, document_id, page_number, content):
        with self.connect() as conn:
            conn.execute('''
                INSERT INTO notes(document_id, page_number, content) VALUES (%s, %s, %s)
                ON CONFLICT (document_id, page_number) DO UPDATE
                SET content=EXCLUDED.content, updated_at=CURRENT_TIMESTAMP
            ''', (document_id, page_number, content))

    def add_summary(self, document_id, page_number, model_name, content):
        with self.connect() as conn:
            return conn.execute('''
                INSERT INTO ai_summaries(document_id, page_number, model_name, content)
                VALUES (%s, %s, %s, %s) RETURNING id
            ''', (document_id, page_number, model_name, content)).fetchone()['id']

    def list_summaries(self, document_id, page_number):
        with self.connect() as conn:
            return conn.execute('''SELECT * FROM ai_summaries
                WHERE document_id=%s AND page_number=%s ORDER BY id DESC''',
                (document_id, page_number)).fetchall()

    def delete_note(self, document_id, page_number):
        with self.connect() as conn:
            conn.execute('DELETE FROM notes WHERE document_id=%s AND page_number=%s',
                         (document_id, page_number))

    def delete_document(self, document_id):
        """ลบข้อมูลเอกสารและข้อมูลที่เกี่ยวข้องในฐานข้อมูล โดยเก็บไฟล์ PDF บนเครื่องไว้"""
        with self.connect() as conn:
            conn.execute('DELETE FROM documents WHERE id=%s', (document_id,))
