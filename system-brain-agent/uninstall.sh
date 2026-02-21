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
