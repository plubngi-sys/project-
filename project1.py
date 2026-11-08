"""
================================================================================
Project: Modern PDF Reader & Note Studio 
         (PDF Viewer + Full Search & Highlight + Ollama AI Analysis)
Tool: Python 3, PyQt6, PyMuPDF, Ollama
================================================================================
"""

import sys
import os
import pymupdf as fitz
import ollama
import asyncio
import httpx
from collections import deque
from pathlib import Path
from database.store import Database
from database.outbox import SummaryOutbox
from background import DatabaseTask

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem, QTextEdit,
    QLineEdit, QFileDialog, QSplitter, QScrollArea,
    QTabWidget, QMessageBox, QToolBar, QSpinBox
)
from PyQt6.QtCore import Qt, QSize, QRectF, QThread, pyqtSignal, pyqtSlot, QThreadPool, QStandardPaths, QTimer
from PyQt6.QtGui import (
    QPixmap, QImage, QIcon, QFont, QAction, QKeySequence, 
    QPainter, QColor
)


# ==============================================================================
# เธรดทำงานเบื้องหลังสำหรับ Ollama AI (รองรับการยกเลิกกลางคัน)
# ==============================================================================
class OllamaWorker(QThread):
    result = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, text, model="qwen2.5:7b", timeout=120):
        super().__init__()
        self.text, self.model, self.timeout = text, model, timeout
        self.is_cancelled = False
        self.loop = None
        self.task = None

    def cancel(self):
        self.is_cancelled = True
        loop, task = self.loop, self.task
        if loop is not None and task is not None:
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:
                pass  # วงจรเหตุการณ์อาจสิ้นสุดพร้อมกับการกดยกเลิก

    async def request(self):
        self.loop = asyncio.get_running_loop()
        self.task = asyncio.current_task()
        if self.is_cancelled:
            return
        prompt = ("โปรดสรุปใจความสำคัญและวิเคราะห์ข้อความต่อไปนี้เป็นภาษาไทย "
                  "ให้อ่านเข้าใจง่าย กระชับ และจัดเป็นหัวข้อย่อย:\n\n" + self.text)
        # ยกเลิกคำขอ HTTP ได้ และกำหนดทั้งเวลารอเครือข่ายกับเวลารวมของงาน
        async with ollama.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            response = await asyncio.wait_for(client.chat(
                model=self.model, messages=[{'role': 'user', 'content': prompt}]),
                timeout=self.timeout)
            if not self.is_cancelled:
                self.result.emit(response['message']['content'])

    def run(self):
        try:
            asyncio.run(self.request())
        except asyncio.CancelledError:
            pass
        except (TimeoutError, httpx.TimeoutException):
            if not self.is_cancelled:
                self.error.emit("AI ใช้เวลาเกินกำหนด กรุณาลองใหม่หรือใช้โมเดลที่เล็กลง")
        except Exception:
            if not self.is_cancelled:
                self.error.emit("เรียก AI ไม่สำเร็จ กรุณาตรวจสอบ Ollama และโมเดลที่ติดตั้ง")
        finally:
            self.loop = self.task = None


# ==============================================================================
# หน้าต่างหลักของโปรแกรม
# ==============================================================================
class PDFReaderApp(QMainWindow):
    def __init__(self, database=None, outbox=None):
        super().__init__()
        self.database = database or Database()
        self.document_id = None
        self.ai_context = None
        location = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
        self.outbox = outbox or SummaryOutbox(location / 'summary-outbox.sqlite3', self.database.scope_key)
        self.volatile_summaries = []
        self.document_hash = None
        self.current_summaries = []
        self.db_queue = deque()
        self.db_task = None
        self.db_pool = QThreadPool(self)
        self.db_pool.setMaxThreadCount(1)
        self.setWindowTitle("PDF Note Studio")
        self.resize(1200, 800)

        self.doc = None
        self.current_page = 0
        self.total_pages = 0
        self.zoom_factor = 1.25
        self.current_search_query = ""

        self.ai_worker = None

        self.init_ui()
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #f7f8f5; color: #213832; }
            QToolBar, QToolBar QLabel, QToolButton { background: #163e36; color: white; border: none; padding: 6px; }
            QToolButton:hover { background: #28584d; }
            QPushButton { background: white; border: 1px solid #bdcdc6; border-radius: 5px; padding: 6px 9px; }
            QPushButton:hover { background: #e3efe8; }
            QPushButton#primary { background: #196650; color: white; font-weight: bold; }
            QPushButton:disabled, QPushButton#primary:disabled { background: #e7ebe7; color: #67766f; }
            QTextEdit, QListWidget, QLineEdit, QSpinBox { background: white; border: 1px solid #c7d4cd; border-radius: 5px; padding: 5px; }
            QTextEdit:focus, QLineEdit:focus { border-color: #197454; }
            QListWidget::item:selected { background: #dcefe5; color: #153f31; }
            QTabBar::tab { background: #e8ede8; padding: 8px 12px; }
            QTabBar::tab:selected { background: white; border-bottom: 3px solid #197454; }
            QTabWidget::pane { border: 1px solid #c7d4cd; }
            QScrollArea, QLabel#paper { background: #e4e9e4; }
            QSplitter::handle { background: #d2dbd4; }
        """)
        self.update_controls()

    def init_ui(self):
        self.create_toolbar()

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.splitter)

        # 1. แผงซ้าย: Thumbnails
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("📑 หน้าเอกสาร (Pages)"))

        self.thumbnail_list = QListWidget()
        self.thumbnail_list.setIconSize(QSize(100, 140))
        self.thumbnail_list.currentRowChanged.connect(self.go_to_page)
        left_layout.addWidget(self.thumbnail_list)
        self.splitter.addWidget(left_panel)

        # 2. แผงกลาง: หน้าอ่าน PDF
        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)

        nav_layout = QHBoxLayout()
        self.btn_prev = QPushButton("◀ หน้าก่อนหน้า")
        self.btn_prev.clicked.connect(self.prev_page)
        nav_layout.addWidget(self.btn_prev)

        self.spin_page = QSpinBox()
        self.spin_page.setMinimum(1)
        self.spin_page.valueChanged.connect(lambda val: self.go_to_page(val - 1))
        nav_layout.addWidget(self.spin_page)

        self.lbl_page_total = QLabel("/ 0")
        nav_layout.addWidget(self.lbl_page_total)

        self.btn_next = QPushButton("หน้าถัดไป ▶")
        self.btn_next.clicked.connect(self.next_page)
        nav_layout.addWidget(self.btn_next)
        nav_layout.addStretch()

        center_layout.addLayout(nav_layout)

        self.scroll_area = QScrollArea()
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_pdf_page = QLabel("ยังไม่ได้เปิดไฟล์ PDF\nกดที่เมนู 'เปิดไฟล์ PDF' เพื่อเริ่มต้น")
        self.lbl_pdf_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_pdf_page.setStyleSheet("color: #666; font-size: 14px;")
        self.lbl_pdf_page.setObjectName("paper")
        self.scroll_area.setWidget(self.lbl_pdf_page)
        self.scroll_area.setWidgetResizable(True)
        center_layout.addWidget(self.scroll_area)

        self.splitter.addWidget(center_panel)

        # 3. แผงขวา: ค้นหาคำ + จดโน้ตและควบคุม AI
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        tabs = QTabWidget()

        # --- แท็บ 1: ค้นหาคำ ---
        search_tab = QWidget()
        st_layout = QVBoxLayout(search_tab)
        
        search_bar = QHBoxLayout()
        search_bar.setSpacing(6)
        search_bar.setContentsMargins(0, 0, 0, 0)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("พิมพ์คำที่ต้องการค้นหา...")
        self.txt_search.returnPressed.connect(self.search_text)
        self.txt_search.setFixedHeight(38)

        self.btn_search = QPushButton("🔍 ค้นหา")
        self.btn_search.clicked.connect(self.search_text)
        self.btn_search.setFixedHeight(38)

        self.btn_clear_search = QPushButton("✖")
        self.btn_clear_search.setToolTip("ล้างการค้นหาและเอาไฮไลต์ออก")
        self.btn_clear_search.clicked.connect(self.clear_search)
        self.btn_clear_search.setFixedSize(38, 38)

        search_bar.addWidget(self.txt_search)
        search_bar.addWidget(self.btn_search)
        search_bar.addWidget(self.btn_clear_search)
        st_layout.addLayout(search_bar)

        self.search_results = QListWidget()
        self.search_results.itemClicked.connect(self.on_search_result_clicked)
        st_layout.addWidget(self.search_results)
        tabs.addTab(search_tab, "🔍 ค้นหาคำ")

        # --- แท็บ 2: จดโน้ต + AI สรุปเนื้อหา ---
        note_tab = QWidget()
        nt_layout = QVBoxLayout(note_tab)

        ai_btn_layout = QHBoxLayout()
        ai_btn_layout.setSpacing(6)

        self.btn_ai = QPushButton("✨ วิเคราะห์หน้านี้ด้วย AI")
        self.btn_ai.setFixedHeight(38)
        self.btn_ai.clicked.connect(self.analyze_page_with_ollama)

        self.btn_cancel_ai = QPushButton("🛑 ยกเลิก")
        self.btn_cancel_ai.setFixedHeight(38)
        self.btn_cancel_ai.setEnabled(False)
        self.btn_cancel_ai.clicked.connect(self.cancel_ai_processing)

        ai_btn_layout.addWidget(self.btn_ai, stretch=3)
        ai_btn_layout.addWidget(self.btn_cancel_ai, stretch=1)
        ai_tab = QWidget()
        ai_layout = QVBoxLayout(ai_tab)
        ai_layout.addLayout(ai_btn_layout)

        self.btn_save_note = QPushButton("💾 บันทึกโน้ต (Ctrl+S)")
        self.btn_save_note.clicked.connect(self.save_current_note)
        self.btn_save_note.setShortcut(QKeySequence("Ctrl+S"))
        self.btn_save_note.setObjectName("primary")
        self.btn_ai.setObjectName("primary")

        self.btn_retry_summary = QPushButton("บันทึกผล AI ที่ค้างอีกครั้ง")
        self.btn_retry_summary.clicked.connect(self.retry_pending_summaries)
        self.btn_export_summary = QPushButton("ส่งออกผล AI ที่รอบันทึก")
        self.btn_export_summary.clicked.connect(self.export_pending_summaries)


        self.txt_summary = QTextEdit()
        self.txt_summary.setReadOnly(True)
        self.txt_summary.setPlaceholderText("ผลสรุป AI ของหน้านี้จะแสดงที่นี่")
        ai_layout.addWidget(QLabel("ผลสรุปของหน้านี้"))
        ai_layout.addWidget(self.txt_summary, 1)
        ai_layout.addWidget(self.btn_retry_summary)
        ai_layout.addWidget(self.btn_export_summary)
        nt_layout.addWidget(QLabel("โน้ตของคุณ"))
        self.txt_notes = QTextEdit()
        self.txt_notes.setPlaceholderText("จดโน้ตของหน้านี้ แล้วกดบันทึกโน้ต")
        self.txt_notes.setStyleSheet("font-size: 13px; padding: 6px;")
        nt_layout.addWidget(self.txt_notes)
        nt_layout.addWidget(self.btn_save_note)
        tabs.insertTab(0, note_tab, "โน้ต")
        tabs.insertTab(1, ai_tab, "สรุป AI")
        tabs.setCurrentWidget(note_tab)

        right_layout.addWidget(tabs)
        self.splitter.addWidget(right_panel)

        self.splitter.setSizes([180, 680, 340])

    def create_toolbar(self):
        toolbar = QToolBar("เครื่องมือหลัก")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self.open_action = btn_open = QAction("📂 เปิดไฟล์ PDF", self)
        btn_open.setShortcut(QKeySequence("Ctrl+O"))
        btn_open.triggered.connect(self.open_pdf_dialog)
        toolbar.addWidget(QLabel("PDF Note Studio"))
        toolbar.addSeparator()
        toolbar.addAction(btn_open)

        toolbar.addSeparator()

        btn_zoom_in = QAction("➕ ซูมเข้า", self)
        btn_zoom_in.triggered.connect(self.zoom_in)
        toolbar.addAction(btn_zoom_in)

        btn_zoom_out = QAction("➖ ซูมออก", self)
        btn_zoom_out.triggered.connect(self.zoom_out)
        toolbar.addAction(btn_zoom_out)

        btn_zoom_reset = QAction("🔄 100%", self)
        btn_zoom_reset.triggered.connect(self.zoom_reset)
        toolbar.addAction(btn_zoom_reset)

    def open_pdf_dialog(self):
        file_path, _ = QFileDialog.getOpenFileNames(
            self, "เลือกเอกสาร PDF", "", "PDF Files (*.pdf)"
        )
        if file_path:
            self.load_pdf(file_path[0])

    def update_controls(self):
        busy = self.db_task is not None or bool(self.db_queue)
        for widget in (self.btn_prev, self.btn_next, self.spin_page, self.thumbnail_list,
                       self.txt_search, self.btn_search, self.btn_clear_search):
            widget.setEnabled(not busy)
        self.open_action.setEnabled(not busy)
        self.txt_notes.setReadOnly(busy or self.document_id is None)
        self.btn_save_note.setEnabled(not busy and self.document_id is not None)
        self.btn_ai.setEnabled(not busy and self.document_id is not None and
                               not (self.ai_worker and self.ai_worker.isRunning()))
        self.refresh_pending_button()

    def submit_db(self, work, success, failure=None):
        self.db_queue.append((work, success, failure))
        self.pump_db()

    def pump_db(self):
        if self.db_task is not None or not self.db_queue:
            self.update_controls()
            return
        work, self.db_success, self.db_failure = self.db_queue.popleft()
        self.db_task = DatabaseTask(work)
        self.db_task.signals.completed.connect(self.finish_db)
        self.statusBar().showMessage("กำลังติดต่อฐานข้อมูล...")
        self.update_controls()
        self.db_pool.start(self.db_task)

    @pyqtSlot(object)
    def finish_db(self, outcome):
        ok, value = outcome
        try:
            if ok:
                self.db_success(value)
            elif self.db_failure:
                self.db_failure(value)
            else:
                self.database_error(value)
        finally:
            self.db_task = None
            self.pump_db()

    def database_error(self, error):
        # ไม่แสดงข้อความ exception ดิบ เพราะอาจมีรายละเอียดการเชื่อมต่อ
        QMessageBox.warning(self, "ฐานข้อมูลไม่พร้อม",
                            "ทำรายการไม่สำเร็จ ตรวจสอบ PostgreSQL และรัน python -m database.init_db "
                            "เพื่ออัปเกรดตาราง งานเดิมยังไม่ถูกทิ้ง")
        self.statusBar().showMessage("ฐานข้อมูลทำรายการไม่สำเร็จ", 5000)

    def save_current_note(self, checked=False, after=None):
        if self.document_id is None or self.db_task is not None:
            return
        document_id, page = self.document_id, self.current_page + 1
        content = self.txt_notes.toPlainText()
        def saved(_):
            self.txt_notes.document().setModified(False)
            self.statusBar().showMessage("บันทึกโน้ตเรียบร้อยแล้ว", 4000)
            if after:
                QTimer.singleShot(0, after)
        self.submit_db(lambda: self.database.save_note(document_id, page, content), saved)

    def after_note_check(self, action):
        if self.db_task is not None or self.db_queue:
            return
        if not self.txt_notes.document().isModified():
            action()
            return
        answer = QMessageBox.question(
            self, "มีโน้ตที่ยังไม่บันทึก", "ต้องการบันทึกโน้ตก่อนออกจากหน้านี้หรือไม่?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard |
            QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save)
        if answer == QMessageBox.StandardButton.Save:
            self.save_current_note(after=action)
        elif answer == QMessageBox.StandardButton.Discard:
            action()
        else:
            self.sync_navigation()

    def show_page_data(self, note, summaries):
        self.txt_notes.setPlainText(note)
        self.txt_notes.document().setModified(False)
        self.show_summaries(summaries)

    def show_summaries(self, summaries):
        self.current_summaries = summaries
        saved_ids = {str(row.get('request_id')) for row in summaries if row.get('request_id')}
        pending = [row for row in self.outbox.items() + self.volatile_summaries
                   if row['document_id'] == self.document_id and
                   row['page_number'] == self.current_page + 1 and row['file_hash'] == self.document_hash
                   and row['request_id'] not in saved_ids]
        text = [f"[รอบันทึก: {row['model_name']}]\n{row['content']}" for row in pending]
        text.extend(f"[{row['model_name']}]\n{row['content']}" for row in summaries)
        self.txt_summary.setPlainText("\n\n".join(text))

    def load_pdf(self, path):
        self.after_note_check(lambda: self.load_document_data(path))

    def load_document_data(self, path):
        # ใช้ PyMuPDF ในเธรดหน้าต่าง ส่วน hash และ SQL ทำใน worker
        try:
            candidate = fitz.open(path)
            if candidate.needs_pass or len(candidate) == 0:
                raise ValueError("เอกสารถูกล็อกหรือไม่มีหน้า")
            pages = len(candidate)
        except Exception:
            if 'candidate' in locals():
                candidate.close()
            QMessageBox.warning(self, "เปิดไฟล์ไม่ได้", "ตรวจสอบไฟล์ PDF และรหัสผ่านเอกสาร")
            return
        def work():
            document_id = self.database.register_document(path, pages)
            metadata = self.database.get_document(document_id)
            return (document_id, metadata['file_hash'],
                    self.database.get_note(document_id, 1),
                    self.database.list_summaries(document_id, 1))
        def loaded(data):
            # สร้างภาพ Qt ในเธรดหน้าต่างเท่านั้น
            try:
                icons = []
                for page in candidate:
                    pix = page.get_pixmap(dpi=36, colorspace=fitz.csRGB, alpha=False)
                    qimg = QImage(pix.samples, pix.width, pix.height, pix.stride,
                                  QImage.Format.Format_RGB888)
                    icons.append(QIcon(QPixmap.fromImage(qimg)))
            except Exception:
                candidate.close()
                QMessageBox.warning(self, "เปิดไฟล์ไม่ได้", "ตรวจสอบว่าไฟล์ PDF ยังอยู่และอ่านได้")
                return
            previous = self.doc
            self.doc = candidate
            self.document_id, self.document_hash, note, summaries = data
            self.total_pages = len(candidate)
            self.current_page = 0
            self.current_search_query = ""
            self.txt_search.clear()
            self.search_results.clear()
            self.spin_page.blockSignals(True)
            self.spin_page.setMaximum(self.total_pages)
            self.spin_page.setValue(1)
            self.spin_page.blockSignals(False)
            self.lbl_page_total.setText(f"/ {self.total_pages}")
            self.setWindowTitle(f"PDF Reader - {os.path.basename(path)}")
            self.thumbnail_list.blockSignals(True)
            self.thumbnail_list.clear()
            for i, icon in enumerate(icons):
                self.thumbnail_list.addItem(QListWidgetItem(icon, f"หน้า {i + 1}"))
            self.thumbnail_list.blockSignals(False)
            self.show_page_data(note, summaries)
            self.render_page()
            if previous is not None:
                previous.close()
        def failed(error):
            candidate.close()
            self.database_error(error)
        self.submit_db(work, loaded, failed)

    def render_page(self):
        if not self.doc or self.current_page >= self.total_pages:
            return

        page = self.doc.load_page(self.current_page)
        zoom_dpi = int(100 * self.zoom_factor)
        pix = page.get_pixmap(dpi=zoom_dpi, colorspace=fitz.csRGB, alpha=False)

        qimg = QImage(
            pix.samples, pix.width, pix.height, pix.stride,
            QImage.Format.Format_RGB888
        )
        pixmap = QPixmap.fromImage(qimg)

        # วาดแถบไฮไลต์สีเหลือง
        if self.current_search_query:
            rects = page.search_for(self.current_search_query)
            if rects:
                painter = QPainter(pixmap)
                painter.setBrush(QColor(255, 235, 59, 130))
                painter.setPen(Qt.PenStyle.NoPen)

                scale_x = pixmap.width() / page.rect.width
                scale_y = pixmap.height() / page.rect.height

                for r in rects:
                    highlight_rect = QRectF(
                        r.x0 * scale_x,
                        r.y0 * scale_y,
                        (r.x1 - r.x0) * scale_x,
                        (r.y1 - r.y0) * scale_y
                    )
                    painter.drawRect(highlight_rect)

                painter.end()

        self.lbl_pdf_page.setPixmap(pixmap)

        self.thumbnail_list.blockSignals(True)
        self.thumbnail_list.setCurrentRow(self.current_page)
        self.thumbnail_list.blockSignals(False)

    def sync_navigation(self):
        self.spin_page.blockSignals(True)
        self.spin_page.setValue(self.current_page + 1)
        self.spin_page.blockSignals(False)
        self.thumbnail_list.blockSignals(True)
        self.thumbnail_list.setCurrentRow(self.current_page)
        self.thumbnail_list.blockSignals(False)

    def go_to_page(self, page_index):
        if not self.doc or not 0 <= page_index < self.total_pages:
            return
        if self.db_task is not None:
            self.sync_navigation()
            return
        if page_index == self.current_page:
            self.render_page()
            return
        self.after_note_check(lambda: self.load_page_data(page_index))

    def load_page_data(self, page_index):
        document_id = self.document_id
        def work():
            return (self.database.get_note(document_id, page_index + 1),
                    self.database.list_summaries(document_id, page_index + 1))
        def loaded(data):
            self.current_page = page_index
            self.sync_navigation()
            self.show_page_data(*data)
            self.render_page()
        def failed(error):
            self.sync_navigation()
            self.database_error(error)
        self.submit_db(work, loaded, failed)

    def prev_page(self):
        if self.current_page > 0:
            self.go_to_page(self.current_page - 1)

    def next_page(self):
        if self.current_page < self.total_pages - 1:
            self.go_to_page(self.current_page + 1)

    def zoom_in(self):
        if self.zoom_factor < 3.0:
            self.zoom_factor += 0.2
            self.render_page()

    def zoom_out(self):
        if self.zoom_factor > 0.6:
            self.zoom_factor -= 0.2
            self.render_page()

    def zoom_reset(self):
        self.zoom_factor = 1.0
        self.render_page()

    def search_text(self):
        query = self.txt_search.text().strip()
        if not self.doc or not query:
            return

        self.current_search_query = query
        self.search_results.clear()
        found_count = 0
        first_match_page = None

        for i in range(self.total_pages):
            page = self.doc.load_page(i)
            rects = page.search_for(query)
            if rects:
                if first_match_page is None:
                    first_match_page = i
                found_count += len(rects)
                item = QListWidgetItem(f"📍 หน้า {i + 1} (พบ {len(rects)} จุด)")
                item.setData(Qt.ItemDataRole.UserRole, i)
                self.search_results.addItem(item)

        if found_count == 0:
            self.search_results.addItem("❌ ไม่พบคำที่ค้นหา")
            self.render_page()
        else:
            if first_match_page is not None:
                self.go_to_page(first_match_page)
            else:
                self.render_page()

    def clear_search(self):
        self.current_search_query = ""
        self.txt_search.clear()
        self.search_results.clear()
        self.render_page()

    def on_search_result_clicked(self, item):
        page_num = item.data(Qt.ItemDataRole.UserRole)
        if page_num is not None:
            self.go_to_page(page_num)

    # ==========================================================================
    # ระบบควบคุม Ollama AI
    # ==========================================================================
    def analyze_page_with_ollama(self):
        if self.db_task is not None or (self.ai_worker and self.ai_worker.isRunning()):
            return
        if not self.doc:
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาเปิดไฟล์ PDF ก่อนใช้งาน AI")
            return

        page = self.doc.load_page(self.current_page)
        page_text = page.get_text().strip()

        if not page_text:
            QMessageBox.warning(
                self, "แจ้งเตือน", 
                "ไม่พบข้อความในหน้านี้ (อาจเป็นรูปภาพล้วน หรือเอกสารสแกน)"
            )
            return

        self.btn_ai.setEnabled(False)
        self.btn_ai.setText("⏳ กำลังวิเคราะห์...")
        self.btn_cancel_ai.setEnabled(True)

        # จับเอกสารและเลขหน้าตอนเริ่มงาน แม้ผู้ใช้จะเปลี่ยนหน้าในระหว่างรอ AI
        self.ai_context = (self.document_id, self.document_hash, self.current_page + 1, "qwen2.5:7b")
        self.statusBar().showMessage("กำลังวิเคราะห์เนื้อหา...")
        self.ai_worker = OllamaWorker(text=page_text, model="qwen2.5:7b")
        self.ai_worker.result.connect(self.on_ai_success)
        self.ai_worker.error.connect(self.on_ai_failed)
        self.ai_worker.finished.connect(self.reset_ai_buttons)
        self.ai_worker.start()

    def cancel_ai_processing(self):
        if self.ai_worker and self.ai_worker.isRunning():
            # ยกเลิก coroutine และให้ client ปิด HTTP ก่อนเธรดสิ้นสุด
            self.ai_worker.cancel()
            self.btn_cancel_ai.setEnabled(False)
            self.statusBar().showMessage("กำลังยกเลิกคำขอ AI และปิดการเชื่อมต่อ")

    def refresh_pending_button(self):
        count = len(self.outbox.items()) + len(self.volatile_summaries)
        self.btn_retry_summary.setText(f"บันทึกผล AI ที่ค้างอีกครั้ง ({count})")
        self.btn_retry_summary.setEnabled(bool(count) and self.db_task is None and not self.db_queue)
        self.btn_export_summary.setEnabled(bool(count))
        self.btn_retry_summary.setVisible(bool(count))
        self.btn_export_summary.setVisible(bool(count))

    def retry_pending_summaries(self):
        if self.db_task is not None:
            return
        # หากดิสก์เคยเขียนไม่ได้ ให้ลองเก็บผลในเครื่องก่อนส่งทุกครั้ง
        for row in self.volatile_summaries[:]:
            try:
                self.outbox.enqueue(row['document_id'], row['file_hash'], row['page_number'],
                                    row['model_name'], row['content'])
                self.volatile_summaries.remove(row)
            except Exception:
                QMessageBox.warning(self, "เก็บผลในเครื่องไม่ได้", "ส่งออกผล AI ก่อนปิดโปรแกรม")
                break
        batch = self.outbox.items()
        if not batch:
            self.refresh_pending_button()
            return
        document_id, page = self.document_id, self.current_page + 1
        def work():
            for row in batch:
                self.database.add_summary(row['document_id'], row['page_number'], row['model_name'],
                                          row['content'], request_id=row['request_id'],
                                          expected_hash=row['file_hash'])
                # ลบจากคิวหลัง PostgreSQL commit สำเร็จเท่านั้น
                self.outbox.acknowledge(row['request_id'])
            return self.database.list_summaries(document_id, page) if document_id is not None else []
        def saved(rows):
            self.show_summaries(rows)
            self.statusBar().showMessage("บันทึกผล AI ที่ค้างเรียบร้อยแล้ว", 5000)
        def failed(error):
            self.refresh_pending_button()
            self.database_error(error)
        self.submit_db(work, saved, failed)

    def export_pending_summaries(self):
        import json
        path, _ = QFileDialog.getSaveFileName(self, "ส่งออกผล AI ที่ค้าง", "ai-results.json", "JSON (*.json)")
        if not path:
            return
        try:
            Path(path).write_text(json.dumps(self.outbox.items() + self.volatile_summaries,
                                            ensure_ascii=False, indent=2), encoding='utf-8')
            # ผลที่ยังเขียนลงคิวไม่ได้มีสำเนาในไฟล์ส่งออกแล้ว จึงปิดโปรแกรมได้
            self.volatile_summaries.clear()
            self.refresh_pending_button()
            self.statusBar().showMessage("ส่งออกผล AI แล้ว คิวที่เก็บบนดิสก์ยังอยู่", 5000)
        except Exception:
            QMessageBox.warning(self, "ส่งออกไม่สำเร็จ", "กรุณาเลือกตำแหน่งที่เขียนไฟล์ได้")

    def on_ai_success(self, summary_text):
        if self.ai_worker.is_cancelled:
            return
        document_id, file_hash, page, model = self.ai_context
        try:
            self.outbox.enqueue(document_id, file_hash, page, model, summary_text)
        except Exception:
            # เก็บสำรองในหน่วยความจำและห้ามปิดโดยไม่ส่งออก หากดิสก์เต็มหรือเขียนไม่ได้
            from uuid import uuid4
            self.volatile_summaries.append(dict(request_id=str(uuid4()), document_id=document_id,
                file_hash=file_hash, page_number=page, model_name=model, content=summary_text))
            QMessageBox.warning(self, "ยังเก็บผลในเครื่องไม่ได้", "ดิสก์อาจเต็ม กรุณาส่งออกผล AI ก่อนปิดโปรแกรม")
        self.refresh_pending_button()
        if (document_id, page) == (self.document_id, self.current_page + 1):
            self.show_summaries(self.current_summaries)
        if self.db_task is None:
            self.retry_pending_summaries()
        else:
            # ผลถูกเก็บลงดิสก์แล้ว รอให้รายการฐานข้อมูลก่อนหน้าจบ
            self.statusBar().showMessage("เก็บผล AI ในเครื่องแล้ว กดบันทึกผลที่ค้างเมื่อฐานข้อมูลพร้อม")

    def on_ai_failed(self, error_message):
        QMessageBox.critical(
            self, "เกิดข้อผิดพลาดจาก Ollama",
            f"ไม่สามารถเชื่อมต่อกับ Ollama ได้:\n{error_message}\n\n"
            "คำแนะนำ: ตรวจสอบว่าได้เปิดโปรแกรม Ollama ในเครื่องแล้วหรือไม่"
        )

    def reset_ai_buttons(self):
        self.btn_ai.setEnabled(True)
        self.btn_ai.setText("✨ วิเคราะห์หน้านี้ด้วย AI")
        self.btn_cancel_ai.setEnabled(False)
        self.update_controls()

    def closeEvent(self, event):
        if self.db_task is not None or self.db_queue:
            self.statusBar().showMessage("กรุณารองานฐานข้อมูลจบก่อนปิดโปรแกรม")
            event.ignore()
            return
        if self.ai_worker and self.ai_worker.isRunning():
            self.cancel_ai_processing()
            self.statusBar().showMessage("กำลังยกเลิก AI กรุณากดปิดอีกครั้งเมื่อเสร็จ")
            event.ignore()
            return
        if self.volatile_summaries:
            QMessageBox.warning(self, "มีผล AI ที่ยังไม่เก็บลงดิสก์",
                                "ส่งออกผล AI หรือลองบันทึกใหม่ก่อนปิด เพื่อไม่ให้ข้อมูลหาย")
            event.ignore()
            return
        if self.txt_notes.document().isModified():
            event.ignore()
            self.after_note_check(self.close_after_discard)
            return
        self.close_document()
        event.accept()

    def close_after_discard(self):
        self.txt_notes.document().setModified(False)
        self.close()

    def close_document(self):
        if self.doc is not None:
            self.doc.close()
            self.doc = None


if __name__ == "__main__":
    app = QApplication(sys.argv)
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    app.setApplicationName("PDFNoteStudio")
    try:
        window = PDFReaderApp(Database())
    except Exception:
        QMessageBox.critical(None, "เปิดโปรแกรมไม่ได้",
                             "ตรวจสอบ DATABASE_URL และสิทธิ์เขียนโฟลเดอร์ข้อมูลของโปรแกรม "
                             "หากไฟล์คิวเสียหายให้เก็บสำเนาก่อนแก้ไข อย่าลบคิวทิ้ง")
        sys.exit(1)
    window.show()
    sys.exit(app.exec())
