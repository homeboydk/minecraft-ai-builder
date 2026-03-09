#!/bin/bash
# Start Minecraft chat agent med nohup (overlever terminal-lukning)
# Usage: ./start_agent.sh [--dry-run]

cd "$(dirname "$0")"

# Tjek om allerede kørende
if pgrep -f "chat_agent.py" > /dev/null; then
    echo "Chat agent kører allerede (PID: $(pgrep -f chat_agent.py))"
    exit 0
fi

# Kræv anthropic pakke
pip install anthropic -q 2>/dev/null

LOG="logs/chat_agent.log"
mkdir -p logs

echo "Starter chat agent..."
nohup python3 chat_agent.py "$@" >> "$LOG" 2>&1 &
PID=$!

sleep 1
if kill -0 $PID 2>/dev/null; then
    echo "Chat agent startet (PID: $PID)"
    echo "Log: tail -f $LOG"
else
    echo "Fejl ved start — se $LOG"
fi
