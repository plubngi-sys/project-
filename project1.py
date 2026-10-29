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
from database.store import Database

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem, QTextEdit,
    QLineEdit, QFileDialog, QSplitter, QScrollArea,
    QTabWidget, QMessageBox, QToolBar, QSpinBox
)
from PyQt6.QtCore import Qt, QSize, QRectF, QThread, pyqtSignal
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

    def __init__(self, text, model="qwen2.5:7b"):
        super().__init__()
        self.text = text
        self.model = model
        self.is_cancelled = False

    def run(self):
        try:
            prompt = (
                "คุณคือผู้ช่วยวิเคราะห์เอกสารอัจฉริยะ "
                "โปรดสรุปใจความสำคัญและวิเคราะห์เนื้อหาต่อไปนี้เป็นภาษาไทย "
                "ให้อ่านเข้าใจง่าย กระชับ และจัดเป็นหัวข้อย่อย:\n\n"
                f"{self.text}"
            )
            response = ollama.chat(
                model=self.model,
                messages=[{'role': 'user', 'content': prompt}]
            )
            if not self.is_cancelled:
                self.result.emit(response['message']['content'])
        except Exception as e:
            if not self.is_cancelled:
                self.error.emit(str(e))


# ==============================================================================
# หน้าต่างหลักของโปรแกรม
# ==============================================================================
class PDFReaderApp(QMainWindow):
    def __init__(self, database=None):
        super().__init__()
        self.database = database or Database()
        self.document_id = None
        self.ai_context = None
        self.pending_summaries = []
        self.setWindowTitle("Modern PDF Reader & Note Studio (AI Analysis)")
        self.resize(1200, 800)

        self.doc = None
        self.current_page = 0
        self.total_pages = 0
        self.zoom_factor = 1.25
        self.current_search_query = ""

        self.ai_worker = None

        self.init_ui()

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
        self.txt_search.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #444444;
                border-radius: 6px;
                padding: 0 10px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #007acc;
            }
        """)

        self.btn_search = QPushButton("🔍 ค้นหา")
        self.btn_search.clicked.connect(self.search_text)
        self.btn_search.setFixedHeight(38)
        self.btn_search.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: #ffffff;
                border: 1px solid #444444;
                border-radius: 6px;
                padding: 0 12px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #444444;
            }
            QPushButton:pressed {
                background-color: #222222;
            }
        """)

        self.btn_clear_search = QPushButton("✖")
        self.btn_clear_search.setToolTip("ล้างการค้นหาและเอาไฮไลต์ออก")
        self.btn_clear_search.clicked.connect(self.clear_search)
        self.btn_clear_search.setFixedSize(38, 38)
        self.btn_clear_search.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: #ffffff;
                border: 1px solid #444444;
                border-radius: 6px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #444444;
            }
            QPushButton:pressed {
                background-color: #222222;
            }
        """)

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
        self.btn_ai.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #1D4ED8;
            }
            QPushButton:disabled {
                background-color: #3f3f46;
                color: #71717a;
            }
        """)
        self.btn_ai.clicked.connect(self.analyze_page_with_ollama)

        self.btn_cancel_ai = QPushButton("🛑 ยกเลิก")
        self.btn_cancel_ai.setFixedHeight(38)
        self.btn_cancel_ai.setEnabled(False)
        self.btn_cancel_ai.setStyleSheet("""
            QPushButton {
                background-color: #DC2626;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
                padding: 0 14px;
            }
            QPushButton:hover {
                background-color: #B91C1C;
            }
            QPushButton:disabled {
                background-color: #27272a;
                color: #52525b;
            }
        """)
        self.btn_cancel_ai.clicked.connect(self.cancel_ai_processing)

        ai_btn_layout.addWidget(self.btn_ai, stretch=3)
        ai_btn_layout.addWidget(self.btn_cancel_ai, stretch=1)
        nt_layout.addLayout(ai_btn_layout)

        self.btn_save_note = QPushButton("💾 บันทึกโน้ต (Ctrl+S)")
        self.btn_save_note.clicked.connect(self.save_current_note)
        self.btn_save_note.setShortcut(QKeySequence("Ctrl+S"))
        nt_layout.addWidget(self.btn_save_note)

        self.btn_retry_summary = QPushButton("บันทึกผล AI ที่ค้างอีกครั้ง")
        self.btn_retry_summary.clicked.connect(self.retry_pending_summaries)
        self.btn_retry_summary.setEnabled(False)
        nt_layout.addWidget(self.btn_retry_summary)

        self.txt_summary = QTextEdit()
        self.txt_summary.setReadOnly(True)
        self.txt_summary.setPlaceholderText("ผลสรุป AI ของหน้านี้จะแสดงที่นี่")
        nt_layout.addWidget(QLabel("ผลสรุป AI"))
        nt_layout.addWidget(self.txt_summary)
        nt_layout.addWidget(QLabel("โน้ตของคุณ"))
        self.txt_notes = QTextEdit()
        self.txt_notes.setPlaceholderText("จดโน้ตของหน้านี้ แล้วกดบันทึกโน้ต")
        self.txt_notes.setStyleSheet("font-size: 13px; padding: 6px;")
        nt_layout.addWidget(self.txt_notes)
        tabs.addTab(note_tab, "📝 โน้ตสรุป")

        right_layout.addWidget(tabs)
        self.splitter.addWidget(right_panel)

        self.splitter.setSizes([180, 680, 340])

    def create_toolbar(self):
        toolbar = QToolBar("เครื่องมือหลัก")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        btn_open = QAction("📂 เปิดไฟล์ PDF", self)
        btn_open.setShortcut(QKeySequence("Ctrl+O"))
        btn_open.triggered.connect(self.open_pdf_dialog)
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

    def save_current_note(self):
        if self.document_id is None:
            return False
        try:
            self.database.save_note(self.document_id, self.current_page + 1,
                                    self.txt_notes.toPlainText())
        except Exception:
            QMessageBox.warning(self, "บันทึกไม่สำเร็จ",
                                "เชื่อมต่อฐานข้อมูลหรือบันทึกไม่ได้ โน้ตยังอยู่ในช่องเดิม กรุณาลองอีกครั้ง")
            return False
        self.txt_notes.document().setModified(False)
        self.statusBar().showMessage("บันทึกโน้ตเรียบร้อยแล้ว", 4000)
        return True

    def confirm_note_change(self):
        if not self.txt_notes.document().isModified():
            return True
        answer = QMessageBox.question(
            self, "มีโน้ตที่ยังไม่บันทึก", "ต้องการบันทึกโน้ตก่อนออกจากหน้านี้หรือไม่?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard |
            QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save)
        if answer == QMessageBox.StandardButton.Save:
            return self.save_current_note()
        return answer == QMessageBox.StandardButton.Discard

    def show_page_data(self, note, summaries):
        self.txt_notes.setPlainText(note)
        self.txt_notes.document().setModified(False)
        self.txt_summary.setPlainText("\n\n".join(
            f"[{row['model_name']}]\n{row['content']}" for row in summaries))

    def load_pdf(self, path):
        if not self.confirm_note_change():
            return
        candidate = None
        try:
            candidate = fitz.open(path)
            if candidate.needs_pass or len(candidate) == 0:
                raise ValueError("เอกสารถูกล็อกหรือไม่มีหน้า")
            document_id = self.database.register_document(path, len(candidate))
            note = self.database.get_note(document_id, 1)
            summaries = self.database.list_summaries(document_id, 1)
            # เตรียมภาพก่อนแทนที่เอกสารเดิม เพื่อเก็บงานเดิมไว้หากเปิดไฟล์ล้มเหลว
            icons = []
            for page in candidate:
                pix = page.get_pixmap(dpi=36, colorspace=fitz.csRGB, alpha=False)
                qimg = QImage(pix.samples, pix.width, pix.height, pix.stride,
                              QImage.Format.Format_RGB888)
                icons.append(QIcon(QPixmap.fromImage(qimg)))
        except Exception:
            if candidate is not None:
                candidate.close()
            QMessageBox.critical(self, "เปิดเอกสารไม่สำเร็จ",
                                 "ตรวจสอบไฟล์ PDF การเชื่อมต่อ PostgreSQL และการสร้างตารางก่อนลองใหม่")
            return

        previous = self.doc
        self.doc = candidate
        self.document_id = document_id
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
        if page_index == self.current_page:
            self.render_page()
            return
        if not self.confirm_note_change():
            self.sync_navigation()
            return
        try:
            note = self.database.get_note(self.document_id, page_index + 1)
            summaries = self.database.list_summaries(self.document_id, page_index + 1)
        except Exception:
            self.sync_navigation()
            QMessageBox.warning(self, "โหลดข้อมูลไม่ได้", "ยังอยู่หน้าเดิม กรุณาตรวจสอบ PostgreSQL แล้วลองใหม่")
            return
        self.current_page = page_index
        self.sync_navigation()
        self.show_page_data(note, summaries)
        self.render_page()

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
        if self.ai_worker and self.ai_worker.isRunning():
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
        self.ai_context = (self.document_id, self.current_page + 1, "qwen2.5:7b")
        self.statusBar().showMessage("กำลังวิเคราะห์เนื้อหา...")
        self.ai_worker = OllamaWorker(text=page_text, model="qwen2.5:7b")
        self.ai_worker.result.connect(self.on_ai_success)
        self.ai_worker.error.connect(self.on_ai_failed)
        self.ai_worker.finished.connect(self.reset_ai_buttons)
        self.ai_worker.start()

    def cancel_ai_processing(self):
        if self.ai_worker and self.ai_worker.isRunning():
            # ไม่บังคับฆ่าเธรด รอคำขอที่ส่งไปจบและไม่รับผลลัพธ์นั้น
            self.ai_worker.is_cancelled = True
            self.btn_cancel_ai.setEnabled(False)
            self.statusBar().showMessage("ยกเลิกการรับผลแล้ว กำลังรอคำขอ AI เดิมสิ้นสุด")

    def retry_pending_summaries(self):
        remaining = []
        for context, content in self.pending_summaries:
            try:
                self.database.add_summary(*context, content)
            except Exception:
                remaining.append((context, content))
        self.pending_summaries = remaining
        self.btn_retry_summary.setEnabled(bool(remaining))
        if remaining:
            QMessageBox.warning(self, "ยังบันทึกไม่ได้", "ผล AI ยังเก็บไว้ในหน่วยความจำ กรุณาลองใหม่ก่อนปิดโปรแกรม")
        else:
            self.statusBar().showMessage("บันทึกผล AI ที่ค้างเรียบร้อยแล้ว", 4000)
        if self.document_id is not None:
            try:
                rows = self.database.list_summaries(self.document_id, self.current_page + 1)
                self.txt_summary.setPlainText("\n\n".join(
                    f"[{row['model_name']}]\n{row['content']}" for row in rows))
            except Exception:
                pass

    def on_ai_success(self, summary_text):
        if self.ai_worker.is_cancelled:
            return
        context = self.ai_context
        try:
            self.database.add_summary(*context, summary_text)
            self.statusBar().showMessage(f"บันทึกผล AI หน้า {context[1]} แล้ว", 4000)
        except Exception:
            self.pending_summaries.append((context, summary_text))
            self.btn_retry_summary.setEnabled(True)
            QMessageBox.warning(self, "บันทึกผล AI ไม่สำเร็จ",
                                "ผลยังอยู่ในหน่วยความจำ กดบันทึกผล AI ที่ค้างอีกครั้งก่อนปิดโปรแกรม")
        if context[:2] == (self.document_id, self.current_page + 1):
            self.txt_summary.setPlainText(summary_text + "\n\n" + self.txt_summary.toPlainText())

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

    def closeEvent(self, event):
        if self.ai_worker and self.ai_worker.isRunning():
            QMessageBox.information(self, "AI ยังทำงานอยู่", "กรุณารอคำขอ AI สิ้นสุดก่อนปิดโปรแกรม")
            event.ignore()
            return
        if self.pending_summaries:
            QMessageBox.warning(self, "ผล AI ยังไม่บันทึก", "กดบันทึกผล AI ที่ค้างอีกครั้งก่อนปิดโปรแกรม")
            event.ignore()
            return
        if not self.confirm_note_change():
            event.ignore()
            return
        if self.doc is not None:
            self.doc.close()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    font = QFont("Helvetica Neue", 10)
    app.setFont(font)

    try:
        database = Database()
        with database.connect() as connection:
            connection.execute("SELECT id FROM documents LIMIT 0")
            connection.execute("SELECT id FROM notes LIMIT 0")
            connection.execute("SELECT id FROM ai_summaries LIMIT 0")
        window = PDFReaderApp(database)
    except Exception:
        QMessageBox.critical(None, "เชื่อมต่อฐานข้อมูลไม่ได้",
                             "ตั้ง DATABASE_URL เปิด PostgreSQL และรัน python -m database.init_db ก่อนเริ่มโปรแกรม")
        sys.exit(1)
    window.show()
    sys.exit(app.exec())

