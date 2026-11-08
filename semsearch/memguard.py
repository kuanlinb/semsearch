"""Memory limits: past them a process exits instead of dragging the whole Mac down.

Normal use is about 1.3–1.8 GB for the search server on the ONNX backend, 3.3 GB on PyTorch,
and under 2 GB for the indexer. Past the limit the indexer stops (the next scheduled run picks
up where it left off) and the search server exits so the app restarts it 5 seconds later. To
avoid a restart loop, the server restarts for memory at most once an hour, and never in its
first 10 minutes; after that it only logs and shows one notification.
"""
import ctypes
import json
import os
import subprocess
import threading
import time

from . import config

_lib = None


def footprint_mb(pid=None):
    """The number Activity Monitor shows as "Memory" (phys_footprint), or None if unavailable."""
    global _lib
    try:
        if _lib is None:
            _lib = ctypes.CDLL("/usr/lib/libproc.dylib")
        buf = (ctypes.c_uint64 * 40)()  # rusage_info_v2
        if _lib.proc_pid_rusage(int(pid or os.getpid()), 2, ctypes.byref(buf)) != 0:
            return None
        return buf[9] / 2**20  # 16-byte uuid (2 slots), 8 fields, then ri_phys_footprint
    except Exception:
        return None


def _notify(msg):
    try:
        subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "SemSearch"'],
                       timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _state_path():
    return config.DATA_DIR / "memguard.json"


def _recent_restart(within=3600):
    try:
        t = json.loads(_state_path().read_text()).get("last_restart", 0)
        return time.time() - t < within
    except Exception:
        return False


def start(role, limit_mb, every=60, min_uptime=600, log=print, exit=os._exit):
    """Check this process's memory every `every` seconds in the background. `role` is "server" or
    "indexer"; `exit` ends the process (the server stops its helper processes first)."""
    if not limit_mb or limit_mb <= 0:
        return
    started = time.time()
    warned = [False]

    def loop():
        while True:
            time.sleep(every)
            mb = footprint_mb()
            if mb is None or mb <= limit_mb:
                continue
            msg = f"{role} is using {mb:.0f} MB, over its {limit_mb} MB limit"
            if role == "indexer":
                log(msg + "; stopping this run, the next one continues")
                exit(4)
            # Over the limit right after starting usually means the index really grew: a restart
            # would not help, so warn once instead
            if time.time() - started < min_uptime or _recent_restart():
                if not warned[0]:
                    warned[0] = True
                    log(msg + "; already restarted within the hour (or just started), not restarting")
                    _notify(msg)
                continue
            log(msg + "; exiting so the app restarts it")
            try:
                _state_path().write_text(json.dumps({"last_restart": time.time(), "mb": round(mb)}))
            except Exception:
                pass
            exit(75)

    threading.Thread(target=loop, daemon=True, name=f"memguard-{role}").start()
