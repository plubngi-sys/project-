"""ส่วนแสดงผลของหน้าต่างอ่าน PDF และแถบเครื่องมือ"""
from pathlib import Path

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QListWidget, QTextEdit, QLineEdit, QSplitter, QScrollArea, QTabWidget,
    QToolBar, QSpinBox,
)


class ReaderWindow(QMainWindow):
    def init_ui(self):
        theme = Path(__file__).with_name("studio_theme.qss")
        self.setStyleSheet(theme.read_text(encoding="utf-8"))
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
