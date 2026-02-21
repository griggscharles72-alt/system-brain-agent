# system-brain-agent v0 (Observer Only)

Observe-only nervous system for System-Brain v1.

- Runs contract checks every 3 minutes via systemd **user** timer.
- Appends one JSON event per run to `logs/events.jsonl`.
- On failure, writes evidence bundle to `logs/evidence/<timestamp>/`.
- No remediation. No self-heal. No system mutation.

## Contract checks (v0)
1. `systemctl is-active ollama.service`
2. `ss -ltnp` contains port `11434`
3. `ollama list` succeeds
4. `python3 -m py_compile ~/system-brain/*.py` succeeds (override with `SYSTEM_BRAIN_DIR`)
