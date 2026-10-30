"""
Real Linux /proc Process Monitoring Service for LDST.
Reads live process metrics from /proc/<pid>/status, /proc/<pid>/stat, and /proc/<pid>/fd,
collects real time-series samples during target process execution, and provides
live Linux system /proc telemetry for the System Monitor view.
"""

import os
import time
from typing import Dict, Any, List, Optional

STATE_LABELS = {
    "R": "R (Running)",
    "S": "S (Sleeping)",
    "D": "D (Disk Sleep)",
    "Z": "Z (Zombie)",
    "T": "T (Stopped)",
    "t": "t (Tracing Stop)",
    "X": "X (Dead)",
    "I": "I (Idle)"
}

try:
    CLK_TCK = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
except Exception:
    CLK_TCK = 100


def find_traced_child_pid(parent_pid: int) -> Optional[int]:
    """
    When strace is the direct child process, find the actual traced target child PID
    via /proc/<pid>/task/<pid>/children or /proc/[0-9]*/status.
    """
    if parent_pid <= 0:
        return None

    children_path = f"/proc/{parent_pid}/task/{parent_pid}/children"
    try:
        if os.path.isfile(children_path):
            with open(children_path, "r", encoding="utf-8") as f:
                parts = f.read().strip().split()
                if parts and parts[0].isdigit():
                    return int(parts[0])
    except Exception:
        pass
    return None


def read_proc_snapshot(pid: int) -> Optional[Dict[str, Any]]:
    """
    Read real /proc/<pid>/status, /proc/<pid>/stat, and /proc/<pid>/fd for a live PID.
    Returns None if the process has already exited.
    """
    if pid <= 0:
        return None

    status_path = f"/proc/{pid}/status"
    if not os.path.isfile(status_path):
        return None

    info: Dict[str, Any] = {
        "pid": pid,
        "ppid": 0,
        "name": "",
        "state_code": "",
        "state": "Unavailable",
        "vm_size_kb": 0,
        "vm_rss_kb": 0,
        "vm_peak_kb": 0,
        "vm_hwm_kb": 0,
        "threads": 0,
        "open_fds": -1,
        "utime_ticks": 0,
        "stime_ticks": 0,
        "voluntary_ctxt_switches": 0,
        "nonvoluntary_ctxt_switches": 0
    }

    try:
        with open(status_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("Name:"):
                    info["name"] = line.split(":", 1)[1].strip()
                elif line.startswith("State:"):
                    val = line.split(":", 1)[1].strip()
                    sc = val[0] if val else ""
                    info["state_code"] = sc
                    info["state"] = STATE_LABELS.get(sc, val or "Unavailable")
                elif line.startswith("PPid:"):
                    info["ppid"] = int(line.split(":", 1)[1].strip() or 0)
                elif line.startswith("VmPeak:"):
                    parts = line.split(":", 1)[1].strip().split()
                    if parts and parts[0].isdigit():
                        info["vm_peak_kb"] = int(parts[0])
                elif line.startswith("VmSize:"):
                    parts = line.split(":", 1)[1].strip().split()
                    if parts and parts[0].isdigit():
                        info["vm_size_kb"] = int(parts[0])
                elif line.startswith("VmHWM:"):
                    parts = line.split(":", 1)[1].strip().split()
                    if parts and parts[0].isdigit():
                        info["vm_hwm_kb"] = int(parts[0])
                elif line.startswith("VmRSS:"):
                    parts = line.split(":", 1)[1].strip().split()
                    if parts and parts[0].isdigit():
                        info["vm_rss_kb"] = int(parts[0])
                elif line.startswith("Threads:"):
                    parts = line.split(":", 1)[1].strip().split()
                    if parts and parts[0].isdigit():
                        info["threads"] = int(parts[0])
                elif line.startswith("voluntary_ctxt_switches:"):
                    parts = line.split(":", 1)[1].strip().split()
                    if parts and parts[0].isdigit():
                        info["voluntary_ctxt_switches"] = int(parts[0])
                elif line.startswith("nonvoluntary_ctxt_switches:"):
                    parts = line.split(":", 1)[1].strip().split()
                    if parts and parts[0].isdigit():
                        info["nonvoluntary_ctxt_switches"] = int(parts[0])
    except Exception:
        return None

    # Count open file descriptors in /proc/<pid>/fd
    fd_dir = f"/proc/{pid}/fd"
    try:
        if os.path.isdir(fd_dir):
            info["open_fds"] = len(os.listdir(fd_dir))
    except Exception:
        info["open_fds"] = -1

    # Read CPU ticks (utime, stime) from /proc/<pid>/stat
    stat_path = f"/proc/{pid}/stat"
    try:
        if os.path.isfile(stat_path):
            with open(stat_path, "r", encoding="utf-8", errors="replace") as f:
                raw_stat = f.read().strip()
            rparen = raw_stat.rfind(")")
            if rparen != -1:
                after = raw_stat[rparen + 2:].split()
                # Field 3 is index 0 in 'after'; utime is field 14 (index 11), stime is field 15 (index 12)
                if len(after) > 12:
                    info["utime_ticks"] = int(after[11])
                    info["stime_ticks"] = int(after[12])
    except Exception:
        pass

    return info


class ProcessTimelineSampler:
    """
    Collects real time-series samples from /proc/<pid> while a debugged process runs.
    Never invents or interpolates fake points.
    """

    def __init__(self, root_pid: int, is_strace_wrapped: bool = False):
        self.root_pid = root_pid
        self.is_strace_wrapped = is_strace_wrapped
        self.target_pid = root_pid
        self.t0 = time.monotonic()
        self.samples: List[Dict[str, Any]] = []
        self.peak_vm_size_kb = 0
        self.peak_vm_rss_kb = 0
        self.peak_threads = 0
        self.peak_open_fds = -1
        self.last_state = "Unavailable"
        self.last_ppid = 0
        self._prev_ticks: Optional[int] = None
        self._prev_time: Optional[float] = None

    def poll_once(self) -> Optional[Dict[str, Any]]:
        now = time.monotonic()
        elapsed_ms = round((now - self.t0) * 1000.0, 2)

        inspect_pid = self.root_pid
        if self.is_strace_wrapped:
            child = find_traced_child_pid(self.root_pid)
            if child:
                inspect_pid = child
                self.target_pid = child

        snap = read_proc_snapshot(inspect_pid)
        if not snap and inspect_pid != self.root_pid:
            snap = read_proc_snapshot(self.root_pid)

        if not snap or snap["vm_size_kb"] <= 0:
            return None

        # Skip strace binary's own memory metrics if we are waiting for target child,
        # unless target is the only process
        if self.is_strace_wrapped and snap["name"] == "strace" and len(self.samples) > 0:
            return None

        total_ticks = snap["utime_ticks"] + snap["stime_ticks"]
        cpu_pct = 0.0
        if self._prev_ticks is not None and self._prev_time is not None:
            dt = now - self._prev_time
            dticks = max(0, total_ticks - self._prev_ticks)
            if dt > 0.001:
                cpu_pct = round(min(100.0, ((dticks / float(CLK_TCK)) / dt) * 100.0), 1)
        else:
            # First sample: compute average CPU since process start if elapsed > 0
            if elapsed_ms > 2.0 and total_ticks > 0:
                cpu_pct = round(min(100.0, ((total_ticks / float(CLK_TCK)) / (elapsed_ms / 1000.0)) * 100.0), 1)

        self._prev_ticks = total_ticks
        self._prev_time = now

        vm_size = max(snap["vm_size_kb"], snap["vm_peak_kb"])
        vm_rss = max(snap["vm_rss_kb"], snap["vm_hwm_kb"])

        if vm_size > self.peak_vm_size_kb:
            self.peak_vm_size_kb = vm_size
        if vm_rss > self.peak_vm_rss_kb:
            self.peak_vm_rss_kb = vm_rss
        if snap["threads"] > self.peak_threads:
            self.peak_threads = snap["threads"]
        if snap["open_fds"] > self.peak_open_fds:
            self.peak_open_fds = snap["open_fds"]

        self.last_state = snap["state"]
        self.last_ppid = snap["ppid"]
        if snap["name"] != "strace":
            self.target_pid = snap["pid"]

        point = {
            "sample_index": len(self.samples) + 1,
            "elapsed_ms": elapsed_ms,
            "pid": snap["pid"],
            "ppid": snap["ppid"],
            "name": snap["name"],
            "state": snap["state"],
            "cpu_percent": cpu_pct,
            "vm_size_kb": snap["vm_size_kb"],
            "vm_rss_kb": snap["vm_rss_kb"],
            "threads": snap["threads"],
            "open_fds": snap["open_fds"]
        }
        if len(self.samples) < 300:
            self.samples.append(point)
        return point


def get_system_proc_overview(active_sessions: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Read real host Linux /proc telemetry (/proc/meminfo, /proc/loadavg, /proc/uptime)
    and inspect real processes for the System Monitor page.
    """
    mem_total_kb = 0
    mem_avail_kb = 0
    mem_free_kb = 0
    try:
        if os.path.isfile("/proc/meminfo"):
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        mem_total_kb = int(line.split()[1])
                    elif line.startswith("MemAvailable:"):
                        mem_avail_kb = int(line.split()[1])
                    elif line.startswith("MemFree:"):
                        mem_free_kb = int(line.split()[1])
    except Exception:
        pass

    load_1, load_5, load_15 = 0.0, 0.0, 0.0
    running_tasks = "Unavailable"
    try:
        if os.path.isfile("/proc/loadavg"):
            with open("/proc/loadavg", "r", encoding="utf-8") as f:
                parts = f.read().strip().split()
                if len(parts) >= 4:
                    load_1 = float(parts[0])
                    load_5 = float(parts[1])
                    load_15 = float(parts[2])
                    running_tasks = parts[3]
    except Exception:
        pass

    uptime_sec = 0.0
    try:
        if os.path.isfile("/proc/uptime"):
            with open("/proc/uptime", "r", encoding="utf-8") as f:
                uptime_sec = float(f.read().strip().split()[0])
    except Exception:
        pass

    # Scan /proc for current user's / relevant processes
    processes: List[Dict[str, Any]] = []
    my_uid = os.getuid() if hasattr(os, "getuid") else -1
    try:
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            pid = int(entry)
            status_path = f"/proc/{pid}/status"
            try:
                uid_match = False
                with open(status_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                for line in content.splitlines():
                    if line.startswith("Uid:"):
                        parts = line.split()
                        if len(parts) >= 2 and int(parts[1]) == my_uid:
                            uid_match = True
                        break
                if not uid_match and my_uid != -1:
                    continue
                snap = read_proc_snapshot(pid)
                if snap:
                    cmdline = ""
                    try:
                        with open(f"/proc/{pid}/cmdline", "rb") as cf:
                            raw_cmd = cf.read(256).replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()
                            cmdline = raw_cmd
                    except Exception:
                        pass
                    snap["cmdline"] = cmdline or snap["name"]
                    processes.append(snap)
            except Exception:
                continue
    except Exception:
        pass

    processes.sort(key=lambda p: -p.get("vm_rss_kb", 0))

    mem_used_kb = max(0, mem_total_kb - (mem_avail_kb or mem_free_kb))
    mem_used_pct = round((mem_used_kb / mem_total_kb) * 100.0, 1) if mem_total_kb > 0 else 0.0

    return {
        "proc_available": os.path.isdir("/proc"),
        "memory": {
            "total_kb": mem_total_kb,
            "used_kb": mem_used_kb,
            "available_kb": mem_avail_kb,
            "used_percent": mem_used_pct
        },
        "loadavg": {
            "load_1m": load_1,
            "load_5m": load_5,
            "load_15m": load_15,
            "scheduling_entities": running_tasks
        },
        "uptime_seconds": round(uptime_sec, 1),
        "active_debug_sessions": active_sessions or [],
        "user_processes": processes[:35]
    }
