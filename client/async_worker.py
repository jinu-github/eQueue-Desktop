"""Generic background-thread helper so UI-triggered API calls don't
freeze the window. Runs any callable on a QThread and delivers the
result (or exception) back on the main thread via Qt signals — that's
the only thread-safe way to touch widgets afterward.

Usage:
    self._worker = run_async(
        lambda: self.api.login(username, password),
        on_success=self._on_login_success,
        on_error=self._on_login_error,
    )
"""
from PyQt6.QtCore import QThread, pyqtSignal


class _CallableWorker(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(Exception)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            result = self._fn()
        except Exception as e:
            self.failed.emit(e)
        else:
            self.succeeded.emit(result)


def run_async(fn, on_success=None, on_error=None, parent=None):
    """Runs fn() on a background thread. on_success(result) and
    on_error(exception) are called back on the main/UI thread.

    Returns the QThread — the caller MUST keep a reference to it
    (e.g. self._worker = run_async(...)) or Qt may garbage-collect it
    mid-flight and silently drop the callback.
    """
    worker = _CallableWorker(fn, parent=parent)
    if on_success:
        worker.succeeded.connect(on_success)
    if on_error:
        worker.failed.connect(on_error)
    worker.finished.connect(worker.deleteLater)
    worker.start()
    return worker