Certainly! Below is a **full README** that includes everything necessary, from environment checks to code installation and validation steps, with full details on how to set up, verify, and remove the **System-Brain-Agent v0**.

---

# System-Brain-Agent v0 (Observer-Only)

**System-Brain-Agent v0** is a read-only observer for **System-Brain v1**. It performs periodic contract checks, logs JSONL events, and captures evidence bundles on failures. The agent runs as a user-level `systemd` service every 3 minutes.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation Steps](#installation-steps)
3. [Contract Checks](#contract-checks)
4. [System-Brain-Agent Verification](#system-brain-agent-verification)
5. [Uninstalling System-Brain-Agent](#uninstalling-system-brain-agent)
6. [Postflight: Confirming Install](#postflight-confirming-install)
7. [Failure-Path Validation](#failure-path-validation)

---

## Prerequisites

Before installing **System-Brain-Agent**, you must ensure your system meets these prerequisites.

### 1. System Packages

Make sure the following software packages are installed:

```bash
sudo apt update
sudo apt install -y python3 python3-venv sqlite3 curl ca-certificates iproute2 network-manager systemd
```

This installs:

* **Python3**: Required to run the agent script.
* **sqlite3**: For any database interaction (if applicable).
* **curl**: To download and install Ollama.
* **network-manager**: For managing network interfaces (for failure checks).
* **systemd**: Required to manage systemd services.

### 2. Verify Dependencies

Run the following commands to check if the necessary tools are available:

```bash
command -v python3
command -v ss
command -v nmcli
systemctl --user status --no-pager >/dev/null; echo "user_systemd_rc=$?"
systemctl is-active ollama.service
ss -ltnp | grep -E '(:|\.)11434\b' || echo "NO_11434"
ollama list
test -d ~/system-brain && echo "OK system-brain exists" || echo "MISSING system-brain"
python3 -m py_compile ~/system-brain/*.py
```

---

## Installation Steps

1. **System-Brain-Agent Installer**

This script will install **System-Brain-Agent v0**, configure `systemd` user services, and set up necessary directories.

### Full Installer Script

Copy the script below, save it as `system-brain-agent-install.sh`, and execute it:

````bash
set -euo pipefail

# ===============================
# system-brain-agent v0 INSTALLER
# OBSERVE-ONLY (sensory layer)
# ===============================

AGENT_DIR="$HOME/system-brain-agent"
LOG_DIR="$AGENT_DIR/logs"
EVID_DIR="$LOG_DIR/evidence"
USER_UNIT_DIR="$HOME/.config/systemd/user"

mkdir -p "$AGENT_DIR" "$LOG_DIR" "$EVID_DIR" "$USER_UNIT_DIR"

# ---- Preflight: user systemd bus ----
if ! systemctl --user status --no-pager >/dev/null 2>&1; then
  echo "ERROR: systemctl --user is not available in this session."
  echo "Fix options:"
  echo "  - Use a normal desktop login session, then re-run"
  echo "  - Or enable linger: sudo loginctl enable-linger \"$USER\""
  exit 1
fi

# ===============================
# agent.py
# ===============================
cat > "$AGENT_DIR/agent.py" <<'PY'
#!/usr/bin/env python3
"""
system-brain-agent v0 (OBSERVE-ONLY)
- Runs contract checks derived from System-Brain v1.
- Appends one JSON event per run to logs/events.jsonl.
- On failure, writes evidence bundle under logs/evidence/<timestamp>/.
- No remediation. No self-heal. No system mutation.
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
        p = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
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
            f"CMD: {cmd}\n"
            f"OK: {r.ok}\n"
            f"RC: {r.rc}\n\n"
            f"STDOUT:\n{r.out}\n\n"
            f"STDERR:\n{r.err}\n"
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
PY
chmod +x "$AGENT_DIR/agent.py"

# ===============================
# verify.sh
# ===============================
cat > "$AGENT_DIR/verify.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

echo "== agent manual run =="
"$HOME/system-brain-agent/agent.py"
echo

echo "== last 5 events (JSONL) =="
tail -n 5 "$HOME/system-brain-agent/logs/events.jsonl" || true
echo

echo "== timer status =="
systemctl --user status system-brain-agent.timer --no-pager -l || true
systemctl --user list-timers | grep system-brain-agent || true
echo

echo "== last service log =="
systemctl --user status system-brain-agent.service --no-pager -l || true
journalctl --user -u system-brain-agent.service -n 80 --no-pager || true
SH
chmod +x "$AGENT_DIR/verify.sh"

# ===============================
# uninstall.sh
# ===============================
cat > "$AGENT_DIR/uninstall.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

systemctl --user disable --now system-brain-agent.timer 2>/dev/null || true
systemctl --user stop system-brain-agent.service 2>/dev/null || true

rm -f "$HOME/.config/systemd/user/system-brain-agent.service"
rm -f "$HOME/.config/systemd/user/system-brain-agent.timer"
systemctl --user daemon-reload || true

echo "Removed user units."
echo "To delete code+logs:"
echo "  rm -rf $HOME/system-brain-agent"
SH
chmod +x "$AGENT_DIR/uninstall.sh"

# ===============================
# README.md
# ===============================
cat > "$AGENT_DIR/README.md" <<'MD'
# system-brain-agent v0 (Observer Only)

Observe-only nervous system for System-Brain v1.

- Runs contract checks every 3 minutes via systemd **user** timer.
- Appends one JSON event per run to `logs/events.jsonl`.
- On failure, writes evidence bundle to `logs/evidence/<timestamp>/`.
- No remediation. No self-heal. No system mutation.

## Contract checks (v0)
- `systemctl is-active ollama.service`
- `ss -ltnp` contains port `11434`
- `ollama list` succeeds
- `python3 -m py_compile ~/system-brain/*.py` succeeds (override with SYSTEM_BRAIN_DIR)

## Files
- `~/system-brain-agent/agent.py`
- `~/system-brain-agent/logs/events.jsonl`
- `~/system-brain-agent/logs/evidence/<timestamp>/`
- `~/system-brain-agent/verify.sh`
- `~/system-brain-agent/uninstall.sh`

## Env overrides
- `SYSTEM_BRAIN_DIR=/path/to/system-brain`
- `OLLAMA_BIN=/usr/local/bin/ollama`
- `PYTHON_BIN=/usr/bin/python3`
- `SBA_CMD_TIMEOUT=30`
- `SBA_EVIDENCE_KEEP=50` (0 disables pruning)

## Verify
```bash
~/system-brain-agent/verify.sh

Uninstall

~/system-brain-agent/uninstall.sh

Notes
	•	User timers may not run while logged out unless linger is enabled:
	•	loginctl show-user "$USER" -p Linger
	•	sudo loginctl enable-linger "$USER" (only if you want always-on)
MD

===============================

systemd user units

===============================

cat > “$USER_UNIT_DIR/system-brain-agent.service” <<‘UNIT’
[Unit]
Description=System Brain Agent (Observer v0)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=%h/system-brain-agent/agent.py
UNIT

cat > "$USER_UNIT_DIR/system-brain-agent.timer" <<'UNIT'
[Unit]
Description=Run System Brain Agent every 3 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=3min
Persistent=true

[Install]
WantedBy=timers.target
UNIT

systemctl --user daemon-reload
systemctl --user enable --now system-brain-agent.timer

echo “Installed system-brain-agent v0 (observe-only).”
echo “Verify with: ~/system-brain-agent/verify.sh”
echo “Uninstall :  ~/system-brain-agent/uninstall.sh”
MD

---

### Preflight Checks:

1. System Dependencies

```bash
command -v python3
command -v ss
command -v nmcli
systemctl --user status --no-pager >/dev/null; echo "user_systemd_rc=$?"
systemctl is-active ollama.service
ss -ltnp | grep -E '(:|\.)11434\b' || echo "NO_11434"
ollama list
test -d ~/system-brain && echo "OK system-brain exists" || echo "MISSING system-brain"
python3 -m py_compile ~/system-brain/*.py
````

2. Install Steps

   * Run the installation block provided.

---

### Postflight:

1. Verify the System-Brain-Agent install:

```bash
~/system-brain-agent/verify.sh
```

2. Check service and timer status:

```bash
systemctl --user status system-brain-agent.timer
systemctl --user status system-brain-agent.service
```

3. Confirm logs are being written:

```bash
tail -n 3 ~/system-brain-agent/logs/events.jsonl
```

4. Optionally, force-run the agent:

```bash
~/system-brain-agent/agent.py
```

---

### Failure-Path Validation:

For testing evidence capture, you can stop `ollama` and manually trigger an agent run:

```bash
sudo systemctl stop ollama
~/system-brain-agent/agent.py
```

This should create an evidence bundle in the `~/system-brain-agent/logs/evidence/` directory.

---

### Uninstall:

To remove **System-Brain-Agent**:

```bash
~/system-brain-agent/uninstall.sh
```

To delete the code and logs:

```bash
rm -rf $HOME/system-brain-agent
```

---

This should cover every detail for installing, validating, and uninstalling **System-Brain-Agent v0**.
