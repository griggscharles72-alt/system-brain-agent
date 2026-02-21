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
