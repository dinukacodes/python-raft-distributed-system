import ntplib
import time
import threading
from prometheus_client import Gauge
from typing import Optional, Dict

# Create Prometheus metrics at module level to avoid duplication
time_drift_metric = Gauge('time_drift_ms', 'Time drift in milliseconds', ['node_id'])
ntp_sync_metric = Gauge('ntp_sync_status', 'NTP synchronization status', ['node_id'])

class TimeSynchronizer:
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.ntp_client = ntplib.NTPClient()
        self.logical_clock = 0
        self.last_ntp_sync = 0
        self.time_drift = 0
        self.ntp_servers = ['pool.ntp.org', 'time.google.com', 'time.windows.com']
        self.ntp_sync_status = 0  # Track sync status in a class variable
        
        # Start background sync thread
        self.sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        self.sync_thread.start()
    
    def _sync_loop(self):
        """Background thread for time synchronization"""
        while True:
            try:
                self.sync_with_ntp()
                time.sleep(60)  # Sync every minute
            except Exception as e:
                print(f"Error in time sync: {e}")
                time.sleep(10)  # Retry after 10 seconds on error
    
    def sync_with_ntp(self) -> Optional[float]:
        """Sync with NTP server and return drift"""
        for server in self.ntp_servers:
            try:
                response = self.ntp_client.request(server, version=3)
                self.time_drift = (response.offset * 1000)  # Convert to milliseconds
                self.last_ntp_sync = time.time()
                ntp_sync_metric.labels(node_id=self.node_id).set(1)
                time_drift_metric.labels(node_id=self.node_id).set(self.time_drift)
                self.ntp_sync_status = 1  # Update class variable
                return self.time_drift
            except Exception as e:
                print(f"Failed to sync with {server}: {e}")
                continue
        
        # If all NTP servers fail, use logical clock
        ntp_sync_metric.labels(node_id=self.node_id).set(0)
        self.ntp_sync_status = 0  # Update class variable
        return None
    
    def get_current_time(self) -> float:
        """Get current time with drift compensation"""
        if time.time() - self.last_ntp_sync > 300:  # 5 minutes since last sync
            self.sync_with_ntp()
        
        if self.time_drift != 0:
            return time.time() + (self.time_drift / 1000)
        return time.time()
    
    def increment_logical_clock(self) -> int:
        """Increment and return logical clock value"""
        self.logical_clock += 1
        return self.logical_clock
    
    def update_logical_clock(self, received_time: int) -> int:
        """Update logical clock based on received time"""
        self.logical_clock = max(self.logical_clock, received_time) + 1
        return self.logical_clock
    
    def get_metrics(self) -> Dict:
        """Get current time synchronization metrics"""
        return {
            'time_drift_ms': self.time_drift,
            'last_ntp_sync': self.last_ntp_sync,
            'logical_clock': self.logical_clock,
            'ntp_sync_status': self.ntp_sync_status  # Use class variable instead of Gauge._value
        } 