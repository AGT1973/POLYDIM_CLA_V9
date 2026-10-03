# ============================================================================
# POLYDIM CONSUMPTION & RESOURCE WATCHDOG (ANTI-HANG & ANTI-TOKEN-EXPLOSION)
# Hardware Target: AMD A4-6300 APU (DDR3 Dual-Channel, 2.7 GB/s)
# ============================================================================

import os
import sys
import time
import psutil
import sqlite3
import ctypes

def prevent_windows_sleep():
    """Locks Windows power state to prevent sleep, standby, or hibernation during compute."""
    try:
        if sys.platform == "win32":
            ES_CONTINUOUS = 0x80000000
            ES_SYSTEM_REQUIRED = 0x00000001
            ES_AWAYMODE_REQUIRED = 0x00000040
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
            )
            return True
    except Exception as e:
        print(f"[WATCHDOG WARN] Could not set Windows execution state: {e}", file=sys.stderr)
    return False

class PolydimConsumptionWatchdog:
    def __init__(self, ram_limit_pct=80.0, proc_limit_mb=1500.0, check_interval_sec=10):
        prevent_windows_sleep()
        self.ram_limit_pct = ram_limit_pct
        self.proc_limit_mb = proc_limit_mb
        self.check_interval_sec = check_interval_sec
        self.db_path = r"E:\POLYDIM-THEORICAL\POLYDIM_VECDB.sqlite"
        self.log_path = r"E:\POLYDIM_EINSOF\watchdog_telemetry.log"

    def audit_system_resources(self):
        mem = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.5)
        
        status = {
            "ram_used_pct": mem.percent,
            "ram_avail_mb": mem.available / (1024 * 1024),
            "ram_total_mb": mem.total / (1024 * 1024),
            "cpu_pct": cpu,
            "alert": False,
            "reason": "OK"
        }

        if mem.percent >= self.ram_limit_pct:
            status["alert"] = True
            status["reason"] = f"CRITICAL: System RAM at {mem.percent:.1f}% (Limit: {self.ram_limit_pct}%)"
        
        return status

    def audit_process_memory(self):
        current_pid = os.getpid()
        high_proc = []
        for p in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_percent']):
            try:
                m_mb = p.info['memory_info'].rss / (1024 * 1024)
                if m_mb > self.proc_limit_mb:
                    high_proc.append({
                        "pid": p.info['pid'],
                        "name": p.info['name'],
                        "mem_mb": m_mb
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return high_proc

    def check_and_log(self):
        res = self.audit_system_resources()
        high_p = self.audit_process_memory()

        entry = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] CPU: {res['cpu_pct']:.1f}% | RAM: {res['ram_used_pct']:.1f}% ({res['ram_avail_mb']:.0f} MB free)"
        if high_p:
            entry += f" | High Mem Procs: {len(high_p)}"
        if res["alert"]:
            entry += f" | ALERT: {res['reason']}"

        print(entry)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(entry + "\n")

        return res, high_p

if __name__ == "__main__":
    wd = PolydimConsumptionWatchdog()
    print("--- POLYDIM CONSUMPTION WATCHDOG HEALTHCHECK ---")
    res, high_p = wd.check_and_log()
    print(f"Status: {'CRITICAL' if res['alert'] else 'HEALTHY'}")
