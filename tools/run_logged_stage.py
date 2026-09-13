

from __future__ import annotations

import queue
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
MAKE = Path(r"C:\Program Files (x86)\GnuWin32\bin\make.exe")


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: run_logged_stage.py <stage> [run_mode]", file=sys.stderr)
        return 2
    stage = sys.argv[1]
    run_mode = sys.argv[2] if len(sys.argv) > 2 else "full"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "full-pipeline-utf8.log"
    status_path = LOG_DIR / "full-pipeline-status.txt"
    command = [str(MAKE), stage, f"RUN_MODE={run_mode}"]
    with log_path.open("a", encoding="utf-8", newline="\n") as log:
        def write(message: str) -> None:
            line = f"[{now()}] {message}\n"
            log.write(line)
            log.flush()
            print(line, end="", flush=True)

        write(f"START stage={stage} run_mode={run_mode} command={command!r}")
        status_path.write_text(
            f"RUNNING\nstage={stage}\nrun_mode={run_mode}\npid=child-process\nstarted={now()}\nlog={log_path}\n",
            encoding="utf-8",
        )
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        status_path.write_text(
            f"RUNNING\nstage={stage}\nrun_mode={run_mode}\npid={process.pid}\nstarted={now()}\nlog={log_path}\n",
            encoding="utf-8",
        )
        assert process.stdout is not None
        output_queue: queue.Queue[str | None] = queue.Queue()

        def read_output() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                output_queue.put(line.rstrip("\r\n"))
            output_queue.put(None)

        threading.Thread(target=read_output, daemon=True).start()
        while True:
            try:
                line = output_queue.get(timeout=5)
            except queue.Empty:
                if process.poll() is None:
                    write(f"HEARTBEAT stage={stage} run_mode={run_mode} child_pid={process.pid} still_running=true")
                    continue
                line = None
            if line is None:
                break
            write(line)
        code = process.wait()
        write(f"EXIT stage={stage} run_mode={run_mode} code={code}")
        write(f"END stage={stage} run_mode={run_mode}")
        status_path.write_text(
            f"FINISHED\nstage={stage}\nrun_mode={run_mode}\nexit_code={code}\nfinished={now()}\nlog={log_path}\n",
            encoding="utf-8",
        )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
