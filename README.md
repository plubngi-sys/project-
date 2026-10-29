# PDF Note Studio

โปรแกรมอ่าน PDF ค้นหาคำ จดโน้ตรายหน้า และสรุปภาษาไทยด้วย Ollama พร้อมจัดเก็บข้อมูลใน PostgreSQL

## เริ่มใช้งานบน Windows

1. สร้างฐานข้อมูล `pdf_note_studio` ใน pgAdmin
2. เปิด PowerShell ในโฟลเดอร์โปรเจกต์ แล้วรัน:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
$env:DATABASE_URL = 'postgresql://postgres:YOUR_PASSWORD@localhost:5432/pdf_note_studio'
.venv\Scripts\python -m database.init_db
.venv\Scripts\python project1.py
```

แทน YOUR_PASSWORD ด้วยรหัสของคุณ หากมีอักขระพิเศษให้ URL-encode และอย่าใส่รหัสจริงลง GitHub
หากสร้างตารางไว้แล้ว ข้ามคำสั่ง init_db ได้ ตัวแปร DATABASE_URL ต้องตั้งใน Terminal ที่ใช้เปิดโปรแกรม
ระบบไม่โหลดไฟล์ .env อัตโนมัติ

อ่าน [รายละเอียดฐานข้อมูลและ ER Diagram](database/README.md)

## วิธีทดสอบด้วยตนเอง

1. เปิด PDF แล้วพิมพ์โน้ตหน้า 1 กด Ctrl+S
2. ไปหน้า 2 เขียนโน้ตอีกข้อความแล้วบันทึก
3. ปิดแล้วเปิดโปรแกรมใหม่ เปิดไฟล์เดิม ตรวจว่าแต่ละหน้ามีโน้ตถูกต้อง
4. ลองเปลี่ยนหน้าทั้งที่ยังไม่บันทึก ตรวจตัวเลือกบันทึก/ทิ้ง/ยกเลิก
5. เปิด Ollama และติดตั้งโมเดลด้วย `ollama pull qwen2.5:7b`
6. เริ่มวิเคราะห์หน้า 1 แล้วเปลี่ยนหน้า ตรวจว่าผล AI ถูกเก็บในหน้า 1 และไม่ทับโน้ต

## ชุดทดสอบ

```powershell
.venv\Scripts\python -m unittest discover -s tests -v
```

ชุดทดสอบหน้าต่างใช้ฐานข้อมูลจำลองและไม่เรียก Ollama จริง ส่วนชุดทดสอบ PostgreSQL ต้องตั้ง TEST_DATABASE_URL ตามคู่มือ
