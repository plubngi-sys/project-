import os
import sys
from pathlib import Path
import ctypes

ROOT = Path(__file__).resolve().parent
if sys.platform == "win32":
    qt_bin = ROOT.parent / "runtime/Lib/site-packages/PyQt6/Qt6/bin"
    if qt_bin.is_dir():
        qt_dlls = os.add_dll_directory(str(qt_bin))
    # Prefer the locally installed PostgreSQL client when available on managed PCs.
    clients = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "PostgreSQL"
    candidates = sorted((p for p in clients.glob("*/bin/libpq.dll") if p.parents[1].name.isdigit()),
                        key=lambda p: int(p.parents[1].name), reverse=True)
    if candidates and not os.getenv("PSYCOPG_IMPL"):
        pg_bin = str(candidates[0].parent)
        pg_dlls = os.add_dll_directory(pg_bin)
        os.environ["PATH"] = pg_bin + os.pathsep + os.environ["PATH"]
        os.environ["PSYCOPG_IMPL"] = "python"

def main():
    from PyQt6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFormLayout,
                                 QLineEdit, QMessageBox, QCheckBox, QLabel)
    from PyQt6.QtCore import QSettings
    from psycopg.conninfo import make_conninfo
    from project1 import PDFReaderApp, Database

    app = QApplication(sys.argv)
    app.setApplicationName("PDFNoteStudio")
    settings = QSettings("PDFNoteStudio", "Connection")
    dialog = QDialog()
    dialog.setWindowTitle("เชื่อมต่อ PostgreSQL")
    layout = QFormLayout(dialog)
    layout.addRow(QLabel("เลือกฐานข้อมูลที่สร้างไว้แล้ว และใส่รหัสผ่าน PostgreSQL"))
    fields = {}
    for key, label, default in (("host","เซิร์ฟเวอร์","localhost"),("port","พอร์ต","5432"),
                                ("dbname","ฐานข้อมูล","pdf_note_studio"),("user","ผู้ใช้","postgres")):
        fields[key] = QLineEdit(str(settings.value(key, default)))
        layout.addRow(label, fields[key])
    password = QLineEdit()
    password.setEchoMode(QLineEdit.EchoMode.Password)
    layout.addRow("รหัสผ่าน", password)
    initialize = QCheckBox("สร้างหรืออัปเดตตารางสำหรับแอป")
    initialize.setChecked(not settings.contains("host"))
    layout.addRow(initialize)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addRow(buttons)
    password.setFocus()
    while dialog.exec() == QDialog.DialogCode.Accepted:
        values = {k: v.text().strip() for k, v in fields.items()}
        try:
            db = Database(make_conninfo(**values, password=password.text()))
            with db.connect() as conn:
                if initialize.isChecked():
                    conn.autocommit = True
                    conn.execute((ROOT / "database/schema.sql").read_text(encoding="utf-8"))
                else:
                    conn.execute("SELECT id FROM documents LIMIT 0")
        except Exception as exc:
            QMessageBox.warning(dialog, "เชื่อมต่อไม่ได้", str(exc))
            continue
        for key, value in values.items():
            settings.setValue(key, value)
        window = PDFReaderApp(db)
        window.show()
        return app.exec()
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        ctypes.windll.user32.MessageBoxW(0, str(exc), "PDF Note Studio", 16)
        sys.exit(1)
