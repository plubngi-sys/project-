"""ส่งผลของงานเบื้องหลังกลับไปจัดการในเธรดหน้าต่างผ่านสัญญาณ Qt"""
from PyQt6.QtCore import QObject, QRunnable, pyqtSignal


class TaskSignals(QObject):
    completed = pyqtSignal(object)


class DatabaseTask(QRunnable):
    def __init__(self, work):
        super().__init__()
        self.work = work
        self.signals = TaskSignals()

    def run(self):
        try:
            outcome = (True, self.work())
        except Exception as error:
            outcome = (False, error)
        self.signals.completed.emit(outcome)
