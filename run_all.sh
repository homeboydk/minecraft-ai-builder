#!/bin/bash
# Master run-script — kører i tmux, overlever SSH-lukning
# Usage: bash run_all.sh
# Genoptag:  tmux attach -t minecraft

set -e
cd "$(dirname "$0")"
mkdir -p logs

echo "=== Minecraft AI Builder ==="
echo "Kører i tmux — du kan lukke SSH trygt"
echo ""

# 1) Genstart Minecraft for at loade Citizens2
echo "[1/4] Genstarter Minecraft (loader Citizens2 plugin)..."
docker compose down
docker compose up -d
echo "Venter 60s på server er klar..."
sleep 60

# Vent på RCON er klar
for i in $(seq 1 20); do
    if python3 -c "
import socket,struct
s=socket.socket(); s.settimeout(3); s.connect(('127.0.0.1',25575))
d='NME21o3#'.encode()+ b'\x00\x00'
s.send(struct.pack('<iii',len(d)+8,1,3)+d)
s.recv(4096); print('OK'); s.close()
" 2>/dev/null; then
        echo "RCON klar!"
        break
    fi
    echo "  Venter på RCON... ($i/20)"
    sleep 5
done

# 2) Opret NPC
echo ""
echo "[2/4] Opretter Claude NPC..."
python3 npc_setup.py --create || echo "NPC: Citizens2 måske ikke klar endnu, spring over"

# 3) Start chat agent i baggrunden
echo ""
echo "[3/4] Starter chat agent..."
nohup python3 chat_agent.py >> logs/chat_agent.log 2>&1 &
CHAT_PID=$!
echo "Chat agent PID: $CHAT_PID (log: logs/chat_agent.log)"
sleep 2

# 4) Kør v4 detailed build
echo ""
echo "[4/4] Starter v4 super-detaljeret byg..."
echo "  Byg-log: logs/v4_build.log"
echo "  Genoptag med: python3 hvidovre_v4_detailed.py  (checkpoint_v4.json gemmes)"
python3 hvidovre_v4_detailed.py 2>&1 | tee logs/v4_build.log

echo ""
echo "=== ALT FÆRDIGT ==="
echo "Koordinater:"
echo "  Havn:    /tp 11440 -30 10666"
echo "  Strand:  /tp 11509 -40 10889"
echo "  Overblik:/tp 12163 80 10109"
echo ""
echo "Chat agent kører stadig (PID $CHAT_PID)"
echo "Log: tail -f logs/chat_agent.log"
