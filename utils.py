import time
import threading
import logging

class Watchdog:
    def __init__(self, timeout=60, callback=None):
        self.timeout = timeout
        self.callback = callback
        self._last_feed_time = time.time()
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
    
    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._monitor, name="Watchdog", daemon=True)
        self._thread.start()
    
    def feed(self):
        with self._lock: self._last_feed_time = time.time()
    
    def stop(self):
        self._running = False
    
    def _monitor(self):
        while self._running:
            time.sleep(5)
            with self._lock:
                if time.time() - self._last_feed_time > self.timeout:
                    if self.callback: self.callback()