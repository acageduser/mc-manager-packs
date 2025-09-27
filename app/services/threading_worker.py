from PySide6.QtCore import QObject, Signal, QThread

class Worker(QObject):
    progressed = Signal(float)          # 0..1
    message = Signal(str)
    finished = Signal(object)
    failed = Signal(str)
    started = Signal()

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self._cancel = False

    def cancel(self):
        self._cancel = True
        self.message.emit("Cancel requested...")

    def run(self):
        self.started.emit()
        try:
            def progress(p):
                self.progressed.emit(max(0.0, min(1.0, float(p))))
            def log(msg):
                self.message.emit(str(msg))
            result = self._fn(progress=progress, log=log, cancelled=lambda: self._cancel, *self._args, **self._kwargs)
            self.finished.emit(result)
        except Exception as ex:
            self.failed.emit(str(ex))

def run_in_thread(fn, *args, **kwargs):
    th = QThread()
    worker = Worker(fn, *args, **kwargs)
    worker.moveToThread(th)
    th.started.connect(worker.run)
    return th, worker
