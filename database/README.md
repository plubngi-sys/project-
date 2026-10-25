# PostgreSQL — PDF Note Studio

ส่วนนี้เป็นฐานข้อมูลสำหรับโปรแกรมแบบผู้ใช้คนเดียว ยังไม่ใช่ระบบแยกบัญชีผู้ใช้
ไฟล์ PDF อยู่บนเครื่อง ฐานข้อมูลเก็บตำแหน่งไฟล์และ SHA-256 ไม่ได้เก็บไฟล์ PDF

## ติดตั้งบน Windows

1. ติดตั้ง PostgreSQL พร้อม pgAdmin แล้วเปิด pgAdmin เชื่อมต่อ server
2. คลิกขวา Databases → Create → Database ตั้งชื่อ `pdf_note_studio`
3. เปิด Terminal ในโฟลเดอร์โปรเจกต์ แล้วติดตั้ง dependency:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
$env:DATABASE_URL = 'postgresql://postgres:YOUR_PASSWORD@localhost:5432/pdf_note_studio'
.venv\Scripts\python -m database.init_db
```

แทน `YOUR_PASSWORD` ด้วยรหัสตอนติดตั้ง PostgreSQL หากมีอักขระพิเศษให้ URL-encode
ห้ามนำ URL ที่มีรหัสจริง commit ลง GitHub ตัวแปรนี้ตั้งใหม่เมื่อเปิด Terminal ใหม่
ไฟล์ `.env` ไม่ได้ถูกโหลดอัตโนมัติ
สามารถเปิด `schema.sql` ใน Query Tool ของฐานข้อมูลนี้แล้ว Execute แทนการใช้ init_db ได้
สคริปต์สร้างตารางเรียกซ้ำได้ แต่ยังไม่มีระบบ migration สำหรับเปลี่ยน schema ที่มีอยู่

## ER Diagram

```mermaid
erDiagram
    documents ||--|{ document_pages : contains
    document_pages ||--o| notes : has
    document_pages ||--o{ ai_summaries : has
```

| ตาราง | คีย์และข้อกำหนด |
|---|---|
| documents | id PK, file_hash UNIQUE, total_pages > 0 |
| document_pages | PK (document_id, page_number), FK ไป documents |
| notes | id PK, UNIQUE (document_id, page_number), FK ไป document_pages |
| ai_summaries | id PK, FK ไป document_pages, เก็บประวัติหลายครั้ง |

เลขหน้าในฐานข้อมูลเริ่มที่ **1** แต่ `current_page` ในโปรแกรมเริ่มที่ **0**
register_document สร้างแถวหน้าตามจำนวนหน้าจริงที่โปรแกรมอ่านมา
การลบ documents จะลบข้อมูลลูกด้วย ON DELETE CASCADE แต่ไม่ลบไฟล์ PDF
การเรียก SQL โดยตรงต้องไม่เพิ่ม document_pages เกิน total_pages

## ตัวอย่างเชื่อมกับ project1.py

```python
from database.store import Database

db = Database()
# หลังเปิด PDF และอ่านจำนวนหน้าได้แล้ว:
document_id = db.register_document(path, len(doc))
# เมื่อโหลดโน้ตของหน้า:
note = db.get_note(document_id, current_page + 1)
# เมื่อผู้ใช้กดบันทึก:
db.save_note(document_id, current_page + 1, text)
# เมื่อ AI สำเร็จ ใช้ ID และเลขหน้าที่จับไว้ตอนเริ่มงาน AI:
db.add_summary(document_id, page_number, 'qwen2.5:7b', summary)
history = db.list_summaries(document_id, page_number)
```

**ยังไม่ได้ต่อปุ่ม/เหตุการณ์ใน project1.py** เพื่อให้ทีม UI นำโมดูลนี้ไปเชื่อมอย่างชัดเจน
ควรเก็บโน้ตกับผล AI คนละ widget, เตือนก่อนทิ้งโน้ตที่ยังไม่บันทึก,
จับ document_id/page_number ตอนเริ่ม AI เพื่อไม่บันทึกผิดหน้าถ้าผู้ใช้เปลี่ยนหน้า,
และแจ้งผู้ใช้เมื่อบันทึกล้มเหลว ห้ามแสดงว่าสำเร็จก่อน transaction commit
ควรรันงานฐานข้อมูลใน worker ของ UI ถ้าฐานข้อมูลอยู่ไกลหรือมีโอกาสช้า

## ทดสอบกับฐานข้อมูลแยก

สร้างฐานข้อมูล `pdf_note_studio_test` ก่อน แล้วรัน:

```powershell
$env:TEST_DATABASE_URL = 'postgresql://postgres:YOUR_PASSWORD@localhost:5432/pdf_note_studio_test'
.venv\Scripts\python -m unittest discover -s tests -v
```

ทดสอบการจำไฟล์เดิมหลังเปลี่ยนชื่อ, ภาษาไทยและข้อความคล้าย SQL,
แก้ไขโน้ต, ปฏิเสธเลขหน้าไม่ถูกต้อง, เก็บประวัติ AI และ cascade delete
หากไม่ได้ตั้ง TEST_DATABASE_URL ชุดทดสอบจะ skip
