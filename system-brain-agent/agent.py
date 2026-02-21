#!/usr/bin/env python3
"""
system-brain-agent v0 (OBSERVE-ONLY)
"""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple

HOME = Path.home()
AGENT_DIR = HOME / "system-brain-agent"
LOG_DIR = AGENT_DIR / "logs"
EVENT_LOG = LOG_DIR / "events.jsonl"
EVIDENCE_DIR = LOG_DIR / "evidence"

SYSTEM_BRAIN_DIR = Path(os.environ.get("SYSTEM_BRAIN_DIR", str(HOME / "system-brain"))).expanduser()
PYTHON_BIN = os.environ.get("PYTHON_BIN", shutil.which("python3") or "/usr/bin/python3")
OLLAMA_BIN = os.environ.get("OLLAMA_BIN") or shutil.which("ollama") or "/usr/local/bin/ollama"

CMD_TIMEOUT_SEC = int(os.environ.get("SBA_CMD_TIMEOUT", "30"))
EVIDENCE_KEEP = int(os.environ.get("SBA_EVIDENCE_KEEP", "50"))

@dataclass
class CmdResult:
    ok: bool
    rc: int
    out: str
    err: str
    cmd: str

def utc_ts() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def run(cmd: str, timeout: int = CMD_TIMEOUT_SEC) -> CmdResult:
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return CmdResult(
            ok=(p.returncode == 0),
            rc=p.returncode,
            out=(p.stdout or "").strip(),
            err=(p.stderr or "").strip(),
            cmd=cmd,
        )
    except Exception as e:
        return CmdResult(ok=False, rc=1, out="", err=str(e), cmd=cmd)

def ensure_dirs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

def write_event(event: Dict) -> None:
    with EVENT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

def evidence_bundle_dir(ts: str) -> Path:
    return EVIDENCE_DIR / ts.replace(":", "-")

def write_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", errors="replace")

def prune_evidence(keep: int) -> None:
    if keep <= 0:
        return
    try:
        bundles = sorted([p for p in EVIDENCE_DIR.iterdir() if p.is_dir()], key=lambda p: p.name)
    except FileNotFoundError:
        return
    excess = len(bundles) - keep
    if excess <= 0:
        return
    for p in bundles[:excess]:
        try:
            for child in sorted(p.rglob("*"), reverse=True):
                if child.is_file():
                    child.unlink(missing_ok=True)
            p.rmdir()
        except Exception:
            pass

def check_ollama_active() -> Tuple[bool, Dict]:
    r = run("systemctl is-active ollama.service", timeout=10)
    return (r.ok and r.out == "active"), {"systemctl_is_active": r.__dict__}

def check_port() -> Tuple[bool, Dict]:
    r = run("ss -ltnp | grep -E '(:|\\.)11434\\b' || true", timeout=10)
    return ("11434" in r.out), {"ss_grep_11434": r.__dict__}

def check_ollama_list() -> Tuple[bool, Dict]:
    r = run(f"{OLLAMA_BIN} list", timeout=20)
    return (r.ok and len(r.out) > 0), {"ollama_list": r.__dict__, "ollama_bin": str(OLLAMA_BIN)}

def check_compile() -> Tuple[bool, Dict]:
    if not SYSTEM_BRAIN_DIR.exists():
        return False, {"system_brain_dir": str(SYSTEM_BRAIN_DIR), "error": "SYSTEM_BRAIN_DIR missing"}
    r = run(f"{PYTHON_BIN} -m py_compile {SYSTEM_BRAIN_DIR}/*.py", timeout=30)
    return r.ok, {"system_brain_dir": str(SYSTEM_BRAIN_DIR), "py_compile": r.__dict__}

def snapshot(ts: str, details: Dict) -> None:
    bundle = evidence_bundle_dir(ts)
    bundle.mkdir(parents=True, exist_ok=True)

    write_file(bundle / "details.json", json.dumps(details, indent=2, ensure_ascii=False))

    cmds = {
        "systemctl_ollama_status.txt": "systemctl status ollama.service --no-pager -l || true",
        "journal_ollama_tail.txt": "journalctl -u ollama.service -n 200 --no-pager || true",
        "ports_ss_full.txt": "ss -ltnp || true",
        "ip_addr.txt": "ip a || true",
        "nmcli_device_status.txt": "nmcli device status || true",
        "ollama_list.txt": f"{OLLAMA_BIN} list || true",
        "compile_check.txt": f"{PYTHON_BIN} -m py_compile {SYSTEM_BRAIN_DIR}/*.py || true",
    }

    for fname, cmd in cmds.items():
        r = run(cmd, timeout=30)
        content = (
            f"CMD: {cmd}\nOK: {r.ok}\nRC: {r.rc}\n\nSTDOUT:\n{r.out}\n\nSTDERR:\n{r.err}\n"
        )
        write_file(bundle / fname, content)

def main() -> None:
    ensure_dirs()
    ts = utc_ts()

    ok1, d1 = check_ollama_active()
    ok2, d2 = check_port()
    ok3, d3 = check_ollama_list()
    ok4, d4 = check_compile()

    status = {
        "ollama_active": ok1,
        "port_11434_listening": ok2,
        "ollama_list_ok": ok3,
        "system_brain_compile_ok": ok4,
    }

    overall = all(status.values())
    event = {"timestamp": ts, "overall_ok": overall, "status": status}
    write_event(event)

    if not overall:
        snapshot(ts, {"event": event, "details": [d1, d2, d3, d4]})
        prune_evidence(EVIDENCE_KEEP)

if __name__ == "__main__":
    main()
