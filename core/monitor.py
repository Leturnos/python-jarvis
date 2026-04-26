import os
import psutil
import threading
import time
import gc
from core.logger_config import logger

class MemoryMonitor:
    def __init__(self, interval_seconds=60, threshold_mb=800):
        self.interval_seconds = interval_seconds
        self.threshold_mb = threshold_mb
        self.stop_event = threading.Event()
        self.monitor_thread = None
        self.process = psutil.Process(os.getpid())

    def _monitor_loop(self):
        logger.info(f"Memory monitor started (Threshold: {self.threshold_mb}MB, Interval: {self.interval_seconds}s)")
        while not self.stop_event.is_set():
            try:
                # Memory info in bytes -> convert to MB
                mem_info = self.process.memory_info()
                rss_mb = mem_info.rss / (1024 * 1024)
                
                if rss_mb > self.threshold_mb:
                    logger.warning(f"High memory usage detected: {rss_mb:.2f}MB (Threshold: {self.threshold_mb}MB). Forcing garbage collection...")
                    
                    # Force garbage collection
                    collected = gc.collect()
                    
                    # Check memory again after GC
                    mem_info_after = self.process.memory_info()
                    rss_mb_after = mem_info_after.rss / (1024 * 1024)
                    
                    logger.info(f"GC completed. Reclaimed {collected} objects. Memory is now {rss_mb_after:.2f}MB.")
                else:
                    logger.debug(f"Current memory usage: {rss_mb:.2f}MB")
                    
            except Exception as e:
                logger.error(f"Error in memory monitor: {e}")
                
            # Wait for the interval, but allow quick exit if stop_event is set
            self.stop_event.wait(self.interval_seconds)
            
    def start(self):
        if self.monitor_thread is None or not self.monitor_thread.is_alive():
            self.stop_event.clear()
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            
    def stop(self):
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.stop_event.set()
            self.monitor_thread.join(timeout=2.0)
            logger.info("Memory monitor stopped.")
