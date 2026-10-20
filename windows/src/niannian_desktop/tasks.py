"""Run blocking HTTP work off Tk's UI thread; consume results on the UI thread."""
import queue
import threading


class BackgroundTasks:
    def __init__(self):
        self.results = queue.Queue()

    def submit(self, label, operation, success):
        def worker():
            try:
                self.results.put((True, operation(), success, label))
            except Exception as exc:
                self.results.put((False, exc, None, label))
        threading.Thread(target=worker, daemon=True).start()

    def drain(self):
        while True:
            try:
                yield self.results.get_nowait()
            except queue.Empty:
                return
