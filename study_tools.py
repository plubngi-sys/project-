"""เครื่องมือทบทวนบทเรียนในหน้าต่าง PDF Note Studio"""
import json
import re
from pathlib import Path
from collections import Counter

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
                             QPushButton, QLabel, QInputDialog, QFileDialog, QMessageBox, QMenu)


def source_pages(doc, question, current_page):
    # ใช้กลุ่มอักขระเพื่อให้ค้นคำไทยได้แม้ไม่ได้เว้นวรรค
    def grams(text):
        text = re.sub(r'\s+', '', text.casefold())
        return Counter(text[i:i+3] for i in range(max(1, len(text)-2)))
    keys = grams(question)
    ranked = []
    for i, page in enumerate(doc):
        text = page.get_text().strip()
        if not text:
            continue
        passages = [text[start:start+1600] for start in range(0, len(text), 1400)]
        score, excerpt = max(((sum((keys & grams(part)).values()), part) for part in passages),
                             key=lambda match: match[0])
        if score or i == current_page:
            ranked.append((score, i == current_page, i+1, excerpt))
    return {page: excerpt for _, _, page, excerpt in sorted(ranked, reverse=True)[:3]}


def read_citation(raw, sources):
    data = json.loads(raw)
    page, quote, answer = data['page'], data['quote'], data['answer']
    if type(page) is not int or page not in sources or not isinstance(quote, str) or not quote.strip():
        raise ValueError('ไม่มีแหล่งอ้างอิง')
    if quote not in sources[page] or not isinstance(answer, str) or not answer.strip():
        raise ValueError('ตรวจสอบข้อความอ้างอิงไม่ได้')
    return page, quote, answer


class StudyTools:
    def add_study_menu(self, toolbar):
        menu = QMenu("ทบทวน", self)
        for title, method in [
            ("ปักธงหน้านี้ · ยังไม่เข้าใจ", self.flag_current),
            ("หน้าที่ปักธง", self.review_flags),
            ("สร้างแฟลชการ์ดจากโน้ต", self.make_card),
            ("ทบทวนแฟลชการ์ด", self.review_cards),
            ("รวมชีทก่อนสอบ", self.exam_sheet),
            ("ถามชีทพร้อมเลขหน้า", self.ask_sheet),
        ]:
            menu.addAction(title, method)
        button = QPushButton("ทบทวน")
        button.setMenu(menu)
        toolbar.addWidget(button)

    def study_ready(self, need_doc=False):
        if self.db_task or self.db_queue:
            self.statusBar().showMessage("กรุณารองานฐานข้อมูลเสร็จก่อน", 3000)
            return False
        if need_doc and self.document_id is None:
            QMessageBox.information(self, "ทบทวน", "เปิดเอกสาร PDF ก่อน")
            return False
        return True

    def flag_current(self):
        if self.study_ready(True):
            doc, page = self.document_id, self.current_page+1
            text, ok = QInputDialog.getText(self, "ปักธงหน้านี้", "อยากกลับมาทบทวนเรื่องอะไร?")
            if ok and text.strip():
                self.submit_db(lambda: self.database.flag_page(doc,page,text.strip()),
                               lambda _: self.statusBar().showMessage("ปักธงแล้ว", 3000))

    def pick(self, title, rows, labels, buttons, multi=False):
        if not rows:
            QMessageBox.information(self, title, "ยังไม่มีรายการ")
            return None, []
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(580,380)
        layout = QVBoxLayout(dlg)
        listing = QListWidget()
        layout.addWidget(listing)
        for label in labels:
            item = QListWidgetItem(label, listing)
            if multi:
                item.setCheckState(Qt.CheckState.Unchecked)
        listing.setCurrentRow(0)
        actions = QHBoxLayout()
        layout.addLayout(actions)
        chosen = []
        for title in buttons:
            btn = QPushButton(title)
            btn.clicked.connect(lambda _, t=title: (chosen.append(t), dlg.accept()))
            actions.addWidget(btn)
        if not dlg.exec():
            return None, []
        indices = ([i for i in range(len(rows)) if listing.item(i).checkState()==Qt.CheckState.Checked]
                   if multi else [listing.currentRow()])
        return chosen[0], [rows[i] for i in indices if i >= 0]

    def review_flags(self):
        if self.study_ready():
            self.submit_db(self.database.flags, self.show_flags)

    def show_flags(self, rows):
        labels = [f"{r['file_name']} · หน้า {r['page_number']} · "
                  f"{'เข้าใจแล้ว' if r['resolved'] else 'ยังไม่เข้าใจ'}\n{r['question']}" for r in rows]
        action, selected = self.pick("หน้าที่ปักธง", rows, labels, ["เปิดหน้า", "เปลี่ยนสถานะ"])
        if not selected:
            return
        row = selected[0]
        if action == "เปิดหน้า":
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self.after_note_check(lambda: self.load_document_data(
                row['file_path'],row['page_number'],row['document_id'])))
        else:
            self.submit_db(lambda: self.database.resolve_flag(row['document_id'],row['page_number'],
                not row['resolved']), lambda _: self.statusBar().showMessage("เปลี่ยนสถานะแล้ว",3000))

    def make_card(self):
        if not self.study_ready(True):
            return
        answer = self.txt_notes.toPlainText().strip()
        if not answer:
            QMessageBox.information(self, "แฟลชการ์ด", "เขียนโน้ตหน้านี้เพื่อใช้เป็นคำตอบก่อน")
            return
        doc, page = self.document_id, self.current_page+1
        question, ok = QInputDialog.getText(self,"สร้างแฟลชการ์ด","ตั้งคำถามสำหรับโน้ตหน้านี้")
        if ok and question.strip():
            self.submit_db(lambda: self.database.create_card(doc,page,question.strip(),answer),
                           lambda _: self.statusBar().showMessage("สร้างแฟลชการ์ดแล้ว",3000))

    def review_cards(self):
        if self.study_ready():
            self.submit_db(self.database.cards, self.show_cards)

    def show_cards(self, rows):
        _, selected = self.pick("แฟลชการ์ด", rows, [
            f"{r['question']}\n{r['file_name']} · หน้า {r['page_number']} · "
            f"{'จำได้' if r['remembered'] else 'ทวนอีกครั้ง'}" for r in rows], ["พลิกดูคำตอบ"])
        if selected:
            r = selected[0]
            box = QMessageBox(self)
            box.setWindowTitle("คำตอบแฟลชการ์ด")
            box.setTextFormat(Qt.TextFormat.PlainText)
            box.setText(r['answer'])
            yes = box.addButton("จำได้", QMessageBox.ButtonRole.AcceptRole)
            again = box.addButton("ทวนอีกครั้ง", QMessageBox.ButtonRole.ActionRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.exec()
            if box.clickedButton() in (yes, again):
                remembered = box.clickedButton() == yes
                self.submit_db(lambda: self.database.rate_card(r['id'], remembered),
                               lambda _: self.statusBar().showMessage("บันทึกผลทบทวนแล้ว",3000))

    def exam_sheet(self):
        if self.study_ready():
            self.submit_db(self.database.exam_entries, self.export_exam)

    def export_exam(self, rows):
        _, items = self.pick("เลือกรายการที่จะรวมในชีท", rows, [
            f"{r['file_name']} · หน้า {r['page_number']} · {r['kind']}\n{r['content'][:90]}" for r in rows],
            ["ส่งออกชีท"], True)
        if not items:
            return
        path, _ = QFileDialog.getSaveFileName(self,"รวมชีทก่อนสอบ","ชีทก่อนสอบ.txt","ข้อความ (*.txt)")
        if path:
            try:
                Path(path).write_text("ชีทก่อนสอบ\n\n"+"\n\n".join(
                    f"{r['file_name']} · หน้า {r['page_number']} · {r['kind']}\n{r['content']}" for r in items),
                    encoding='utf-8-sig')
            except OSError:
                QMessageBox.warning(self,"ส่งออกไม่ได้","กรุณาเลือกตำแหน่งที่เขียนไฟล์ได้")
            else:
                self.statusBar().showMessage("ส่งออกชีทแล้ว",3000)

    def ask_sheet(self):
        if not self.study_ready(True) or (self.ai_worker and self.ai_worker.isRunning()):
            return
        question, ok = QInputDialog.getText(self, "ถามชีท", "ต้องการถามอะไรจากเอกสารที่เปิดอยู่?")
        if not ok or not question.strip():
            return
        sources = source_pages(self.doc,question,self.current_page)
        if not sources:
            QMessageBox.information(self,"ถามชีท","ไม่พบข้อความที่ใช้ตอบคำถาม")
            return
        prompt = ("ตอบคำถามภาษาไทยโดยใช้เฉพาะหลักฐานจากหน้าที่ให้มา ส่ง JSON เท่านั้น มีฟิลด์ "
                  "answer, page (จำนวนเต็ม), quote (คัดตรงจากหน้านั้น) หากข้อมูลไม่พอให้ส่ง {}\n"
                  + json.dumps(dict(question=question, pages=sources), ensure_ascii=False))
        worker = self.question_worker(prompt)
        self.ai_worker = worker
        origin = self.document_id
        worker.result.connect(lambda raw: self.show_answer(raw,sources,origin))
        worker.error.connect(self.on_ai_failed)
        worker.finished.connect(self.reset_ai_buttons)
        self.btn_cancel_ai.setEnabled(True)
        self.btn_ai.setEnabled(False)
        self.statusBar().showMessage("กำลังค้นคำตอบจากข้อความในชีท…")
        worker.start()

    def show_answer(self, raw, sources, origin):
        if self.ai_worker.is_cancelled:
            return
        try:
            page, quote, answer = read_citation(raw,sources)
        except (TypeError, KeyError, ValueError):
            QMessageBox.information(self,"ถามชีท","ยังหาคำตอบพร้อมข้อความอ้างอิงที่ตรวจสอบได้ไม่พบ")
            return
        box = QMessageBox(self)
        box.setWindowTitle("คำตอบจากชีท")
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(f"{answer}\n\nหน้า {page}\n“{quote}”")
        jump = box.addButton("เปิดหน้าอ้างอิง", QMessageBox.ButtonRole.ActionRole) if origin==self.document_id else None
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        if jump and box.clickedButton()==jump:
            self.go_to_page(page-1)
