"""Run blocking HTTP work off Tk's UI thread; consume results on the UI thread."""
import queue
import threading


class BackgroundTasks:
    def __init__(self):
        self.results = queue.Queue()
        self.generation = 0

    def invalidate(self):
        """Discard callbacks from a previous login/family/window generation."""
        self.generation += 1

    def submit(self, label, operation, success):
        generation = self.generation
        def worker():
            try:
                self.results.put((generation, True, operation(), success, label))
            except Exception as exc:
                self.results.put((generation, False, exc, None, label))
        threading.Thread(target=worker, daemon=True).start()

    def drain(self):
        while True:
            try:
                generation, *result = self.results.get_nowait()
                if generation == self.generation:
                    yield tuple(result)
            except queue.Empty:
                return
