"""ส่วนแสดงผลของหน้าต่างอ่าน PDF และแถบเครื่องมือ"""
from pathlib import Path

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QAction, QKeySequence, QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QListWidget, QTextEdit, QLineEdit, QSplitter, QScrollArea, QTabWidget,
    QStackedWidget, QComboBox, QToolBar, QSpinBox, QSizePolicy, QToolButton, QStyle,
)


class NoteEditor(QTextEdit):
    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.document().isEmpty():
            return
        # แสดงเส้นบรรทัดใต้ข้อความแนะนำเฉพาะตอนที่สมุดยังว่าง
        painter = QPainter(self.viewport())
        painter.setPen(QColor("#ddd3c8"))
        step = max(30, self.fontMetrics().height() + 10)
        for y in range(step + 12, self.viewport().height(), step):
            painter.drawLine(4, y, self.viewport().width() - 4, y)
        painter.end()


class NotebookIllustration(QWidget):
    def __init__(self, compact=False):
        super().__init__()
        self.compact = compact
        if compact:
            self.setFixedSize(40, 36)
        else:
            self.setMaximumSize(416, 266)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale = min(self.width() / 400, self.height() / 255)
        painter.translate((self.width() - 400 * scale) / 2, (self.height() - 255 * scale) / 2)
        painter.scale(scale, scale)

        # วาดสมุดเป็นเส้นโค้งเพื่อให้ภาพยังคมชัดเมื่อปรับขนาดหน้าต่าง
        def shape(path, fill, stroke="#695244", width=1.7):
            painter.setPen(QPen(QColor(stroke), width))
            painter.fillPath(path, QColor(fill))
            painter.strokePath(path, painter.pen())

        if not self.compact:
            painter.save()
            painter.translate(294, 48)
            painter.rotate(9)
            painter.setPen(QPen(QColor("#796658"), 2))
            painter.setBrush(QColor("#e4be96"))
            painter.drawRoundedRect(18, -30, 7, 76, 2, 2)
            painter.setBrush(QColor("#82766a"))
            painter.drawRoundedRect(5, -21, 8, 64, 3, 3)
            painter.setBrush(QColor("#f0dfcd"))
            painter.drawRoundedRect(-7, 20, 53, 67, 9, 9)
            painter.restore()
            painter.setPen(QPen(QColor("#bb7859"), 2))
            stem = QPainterPath()
            stem.moveTo(65, 188)
            stem.cubicTo(16, 153, 34, 81, 69, 59)
            painter.drawPath(stem)
            for x, y, angle in [(38, 144, -52), (33, 120, 48), (40, 98, -35), (52, 80, 54)]:
                painter.save()
                painter.translate(x, y)
                painter.rotate(angle)
                leaf = QPainterPath()
                leaf.moveTo(0, 0)
                leaf.quadTo(-9, -14, 0, -32)
                leaf.quadTo(9, -15, 0, 0)
                shape(leaf, "#d79472", "#bd7858", 1)
                painter.restore()

        painter.save()
        if self.compact:
            painter.translate(-62, -64)
            painter.scale(1.3, 1.3)
        else:
            painter.translate(0, 4)
            painter.rotate(-4)
        for side in (-1, 1):
            painter.save()
            painter.translate(193, 0)
            painter.scale(side, 1)
            page = QPainterPath()
            page.moveTo(0, 106)
            page.cubicTo(32, 77, 85, 74, 117, 80)
            page.lineTo(142, 186)
            page.cubicTo(88, 178, 39, 184, 0, 211)
            page.closeSubpath()
            painter.translate(0, 7)
            shape(page, "#c27b55")
            painter.translate(0, -7)
            shape(page, "#fffaf1", "#88492e" if self.compact else "#604c40",
                  8 if self.compact else 2)
            if not self.compact:
                painter.setPen(QPen(QColor("#d7c3b1"), 1.3))
                for row in range(5):
                    line = QPainterPath()
                    line.moveTo(12, 115 + row * 16)
                    line.quadTo(60, 88 + row * 16, 108 + row * 3, 94 + row * 16)
                    painter.drawPath(line)
            painter.restore()
        if not self.compact:
            ribbon = QPainterPath()
            ribbon.moveTo(189, 107)
            ribbon.quadTo(196, 154, 194, 208)
            ribbon.lineTo(206, 227)
            ribbon.lineTo(196, 222)
            ribbon.lineTo(193, 229)
            ribbon.quadTo(184, 200, 185, 110)
            ribbon.closeSubpath()
            shape(ribbon, "#bf7652")
        painter.restore()
        painter.end()


class ReaderWindow(QMainWindow):
    def init_ui(self):
        theme = Path(__file__).with_name("studio_theme.qss")
        self.setStyleSheet(theme.read_text(encoding="utf-8"))
        self.create_toolbar()

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(16, 16, 16, 8)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(6)
        self.splitter.setChildrenCollapsible(False)
        main_layout.addWidget(self.splitter)

        # 1. แผงซ้าย: Thumbnails
        left_panel = QWidget()
        left_panel.setObjectName("pagesPanel")
        left_panel.setMinimumWidth(165)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(12, 18, 12, 12)
        pages_title = QLabel("หน้าเอกสาร")
        pages_title.setObjectName("pagesTitle")
        left_layout.addWidget(pages_title)

        self.thumbnail_list = QListWidget()
        self.thumbnail_list.setIconSize(QSize(110, 155))
        self.thumbnail_list.setSpacing(8)
        self.thumbnail_list.currentRowChanged.connect(self.go_to_page)
        left_layout.addWidget(self.thumbnail_list)
        self.splitter.addWidget(left_panel)

        # 2. แผงกลาง: หน้าอ่าน PDF
        center_panel = QWidget()
        center_panel.setObjectName("readerPanel")
        center_panel.setMinimumWidth(300)
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(12, 12, 12, 10)
        center_layout.setSpacing(12)

        nav_layout = QHBoxLayout()
        self.document_label = QLabel("ยังไม่ได้เปิดเอกสาร")
        self.document_label.setMinimumWidth(60)
        self.document_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        nav_layout.addWidget(self.document_label, 1)
        self.windowTitleChanged.connect(self.update_document_label)
        self.btn_prev = QPushButton("‹")
        self.btn_prev.setToolTip("หน้าก่อนหน้า")
        self.btn_prev.setFixedSize(36, 36)
        self.btn_prev.clicked.connect(self.prev_page)
        nav_layout.addWidget(self.btn_prev)

        self.spin_page = QSpinBox()
        self.spin_page.setMinimum(1)
        self.spin_page.setFixedWidth(64)
        self.spin_page.valueChanged.connect(lambda val: self.go_to_page(val - 1))
        nav_layout.addWidget(self.spin_page)

        self.lbl_page_total = QLabel("/ 0")
        nav_layout.addWidget(self.lbl_page_total)

        self.btn_next = QPushButton("›")
        self.btn_next.setToolTip("หน้าถัดไป")
        self.btn_next.setFixedSize(36, 36)
        self.btn_next.clicked.connect(self.next_page)
        nav_layout.addWidget(self.btn_next)

        for action in self.zoom_actions:
            button = QToolButton()
            button.setDefaultAction(action)
            nav_layout.addWidget(button)
        fullscreen = QPushButton()
        fullscreen.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarMaxButton))
        fullscreen.setToolTip("สลับเต็มหน้าจอ")
        fullscreen.setFixedSize(36, 36)
        fullscreen.clicked.connect(self.toggle_fullscreen)
        nav_layout.addWidget(fullscreen)
        center_layout.addLayout(nav_layout)

        self.reader_stack = QStackedWidget()
        welcome = QWidget()
        welcome.setObjectName("welcome")
        intro = QVBoxLayout(welcome)
        intro.setContentsMargins(8, 8, 8, 8)
        intro.setSpacing(12)
        intro.addStretch(3)
        art_row = QHBoxLayout()
        art_row.addStretch(1)
        art_row.addWidget(NotebookIllustration(), 8)
        art_row.addStretch(1)
        intro.addLayout(art_row, 4)
        title = QLabel("เปิดเอกสาร PDF")
        title.setObjectName("welcomeTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        intro.addWidget(title)
        hint = QLabel("เลือกไฟล์เพื่อเริ่มอ่านและจดบันทึก")
        hint.setObjectName("welcomeHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        intro.addWidget(hint)
        intro.addStretch(3)
        self.reader_stack.addWidget(welcome)

        self.scroll_area = QScrollArea()
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_pdf_page = QLabel()
        self.lbl_pdf_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_pdf_page.setObjectName("paper")
        self.scroll_area.setWidget(self.lbl_pdf_page)
        self.scroll_area.setWidgetResizable(True)
        self.reader_stack.addWidget(self.scroll_area)
        center_layout.addWidget(self.reader_stack)

        self.splitter.addWidget(center_panel)

        # 3. แผงขวา: ค้นหาคำ + จดโน้ตและควบคุม AI
        right_panel = QWidget()
        right_panel.setObjectName("workspacePanel")
        right_panel.setMinimumWidth(300)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(14, 18, 14, 14)
        heading = QLabel("สมุดความคิด")
        heading.setObjectName("sectionTitle")
        right_layout.addWidget(heading)

        tabs = QTabWidget()

        # --- แท็บ 1: ค้นหาคำ ---
        search_tab = QWidget()
        st_layout = QVBoxLayout(search_tab)
        
        self.search_scope = QComboBox()
        self.search_scope.addItems(["ข้อความใน PDF ที่เปิดอยู่", "โน้ตและผล AI ทุกชีท"])
        self.search_scope.currentIndexChanged.connect(self.clear_search)
        st_layout.addWidget(self.search_scope)
        search_bar = QHBoxLayout()
        search_bar.setSpacing(6)
        search_bar.setContentsMargins(0, 0, 0, 0)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("พิมพ์คำที่ต้องการค้นหา...")
        self.txt_search.returnPressed.connect(self.search_text)
        self.txt_search.setFixedHeight(38)

        self.btn_search = QPushButton("ค้นหา")
        self.btn_search.clicked.connect(self.search_text)
        self.btn_search.setFixedHeight(38)

        self.btn_clear_search = QPushButton("×")
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
        tabs.addTab(search_tab, "ค้นหา")

        # --- แท็บ 2: จดโน้ต + AI สรุปเนื้อหา ---
        note_tab = QWidget()
        nt_layout = QVBoxLayout(note_tab)

        ai_btn_layout = QHBoxLayout()
        ai_btn_layout.setSpacing(6)

        self.btn_ai = QPushButton("วิเคราะห์หน้านี้ด้วย AI")
        self.btn_ai.setFixedHeight(38)
        self.btn_ai.clicked.connect(self.analyze_page_with_ollama)

        self.btn_cancel_ai = QPushButton("ยกเลิก")
        self.btn_cancel_ai.setFixedHeight(38)
        self.btn_cancel_ai.setEnabled(False)
        self.btn_cancel_ai.clicked.connect(self.cancel_ai_processing)

        ai_btn_layout.addWidget(self.btn_ai, stretch=3)
        ai_btn_layout.addWidget(self.btn_cancel_ai, stretch=1)
        ai_tab = QWidget()
        ai_layout = QVBoxLayout(ai_tab)
        ai_layout.addLayout(ai_btn_layout)

        self.btn_save_note = QPushButton("บันทึกโน้ต    Ctrl+S")
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
        self.note_page_label = QLabel("โน้ตหน้าที่ 1")
        nt_layout.addWidget(self.note_page_label)
        self.txt_notes = NoteEditor()
        self.txt_notes.setPlaceholderText("เปิดเอกสารเพื่อเริ่มจดโน้ต")
        nt_layout.addWidget(self.txt_notes)
        nt_layout.addWidget(self.btn_save_note)
        tabs.insertTab(0, note_tab, "โน้ต")
        tabs.insertTab(1, ai_tab, "สรุป AI")
        tabs.setCurrentWidget(note_tab)

        right_layout.addWidget(tabs)
        self.splitter.addWidget(right_panel)

        self.splitter.setSizes([160, 650, 350])
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setStretchFactor(2, 1)
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().showMessage("พร้อมเปิดเอกสาร")

    def update_document_label(self, title):
        filename = title.removeprefix("PDF Reader - ")
        if title.startswith("PDF Reader - "):
            self.document_label.setText(filename)
            self.document_label.setToolTip(filename)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def create_toolbar(self):
        toolbar = QToolBar("เครื่องมือหลัก")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self.open_action = btn_open = QAction("เปิด PDF", self)
        btn_open.setShortcut(QKeySequence("Ctrl+O"))
        btn_open.triggered.connect(self.open_pdf_dialog)
        toolbar.addWidget(NotebookIllustration(compact=True))
        brand = QLabel("PDF NOTE STUDIO")
        brand.setObjectName("brand")
        toolbar.addWidget(brand)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        open_button = QToolButton()
        open_button.setObjectName("openPdf")
        open_button.setDefaultAction(btn_open)
        open_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        open_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toolbar.addWidget(open_button)
        self.add_study_menu(toolbar)


        btn_zoom_in = QAction("＋", self)
        btn_zoom_in.triggered.connect(self.zoom_in)


        btn_zoom_out = QAction("−", self)
        btn_zoom_out.triggered.connect(self.zoom_out)


        btn_zoom_reset = QAction("100%", self)
        btn_zoom_reset.setToolTip("คืนขนาดเอกสารเป็น 100%")
        btn_zoom_reset.triggered.connect(self.zoom_reset)
        self.zoom_actions = [btn_zoom_out, btn_zoom_reset, btn_zoom_in]
