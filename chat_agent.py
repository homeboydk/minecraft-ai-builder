#!/usr/bin/env python3
"""
Minecraft Chat Agent — monitors server log, responds to player commands via Claude.

Usage:
    python3 chat_agent.py [--dry-run]

Commands in-game:
    !hjælp              — vis kommandoer
    !info               — vis hvad der er bygget
    !tp <stednavn>      — teleporter dig til et bygget sted
    !byg <stednavn>     — byg et OSM-område (starter build-script)
    !claude <spørgsmål> — stil Claude et spørgsmål
    (fritext)           — sendes til Claude hvis man er inden for NPC-range

Requires:
    pip install anthropic
    docker container 'minecraft' kørende
"""

import subprocess, threading, time, re, json, os, sys, socket, struct
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
RCON_HOST    = '127.0.0.1'
RCON_PORT    = 25575
RCON_PASS    = 'NME21o3#'
CONTAINER    = 'minecraft'
DRY_RUN      = '--dry-run' in sys.argv
CLAUDE_MODEL = 'claude-haiku-4-5-20251001'

# Buildte steder spilleren kan teleportere til
KNOWN_PLACES = {
    'havn':        (8440,  -30, 7666,  'Hvidovrehavn'),
    'havnen':      (8440,  -30, 7666,  'Hvidovrehavn'),
    'strand':      (9509,  -40, 7889,  'Hvidovre Strand'),
    'stranden':    (9509,  -40, 7889,  'Hvidovre Strand'),
    'overblik':    (9163,   60, 7109,  'Overblik over bygget'),
    'hvidovre':    (9163,   60, 7109,  'Hvidovre overblik'),
    'eiffel':      (200,   150,  200,  'Eiffeltårnet'),
    'eiffeltårn':  (200,   150,  200,  'Eiffeltårnet'),
}

HELP_TEXT = (
    '§e=== Claude Minecraft AI ===§r '
    '§7!hjælp§r §7!info§r §7!tp <sted>§r §7!byg <sted>§r §7!claude <spørgsmål>§r '
    '§7Steder:§r havn, strand, overblik, eiffel'
)

INFO_TEXT = (
    '§6=== Bygget af Claude ===§r '
    '§aHvidovrehavn + Strand + Stentoftevej§r (1:1 skala, 1.07M blokke) '
    '§7X=8000..10326 Z=6219..8000§r | '
    '§aEiffeltårnet§r (2/3 skala) §7X=200 Z=200§r'
)

# System prompt til Claude
SYSTEM_PROMPT = """Du er Claude, en AI-assistent der lever som NPC i et Minecraft-server.
Serveren er et 1:1 kort over Hvidovre, Danmark — bygget fra OpenStreetMap data.
Du kender til: Hvidovrehavn, Hvidovre Strand, Stentoftevej, Eiffeltårnet (bygget til sammenligning).

Svar KORT (max 2 sætninger) — det er en Minecraft chat-besked.
Brug ikke markdown. Vær venlig og hjælpsom.
Du kan fortælle om byggeriet, Hvidovre-området, og hvad der er planlagt.
"""

# ── RCON ──────────────────────────────────────────────────────────────────────
class RconClient:
    def __init__(self):
        self._s = None
        self._lock = threading.Lock()
        self._connect()

    def _connect(self):
        try:
            s = socket.socket()
            s.settimeout(10)
            s.connect((RCON_HOST, RCON_PORT))
            self._send_pkt(s, 1, 3, RCON_PASS)
            self._s = s
        except Exception as e:
            print(f'[RCON] connect failed: {e}')
            self._s = None

    def _send_pkt(self, s, rid, rt, payload):
        d = payload.encode('utf-8') + b'\x00\x00'
        s.send(struct.pack('<iii', len(d)+8, rid, rt) + d)
        r = b''
        while len(r) < 4 or len(r) < struct.unpack('<i', r[:4])[0]+4:
            chunk = s.recv(4096)
            if not chunk: break
            r += chunk
        return r[12:-2].decode('utf-8', 'replace')

    def cmd(self, command):
        if DRY_RUN:
            print(f'[DRY-RUN] {command}')
            return ''
        with self._lock:
            for attempt in range(3):
                try:
                    if self._s is None:
                        self._connect()
                    return self._send_pkt(self._s, 2, 2, command)
                except Exception as e:
                    print(f'[RCON] cmd failed (attempt {attempt+1}): {e}')
                    try: self._s.close()
                    except: pass
                    self._s = None
                    time.sleep(1)
            return ''

    def tellraw(self, message, target='@a'):
        """Send colored message to all players."""
        # Escape double quotes in message
        safe = message.replace('"', '\\"')
        self.cmd(f'tellraw {target} {{"text":"{safe}"}}')

    def tellraw_claude(self, message, target='@a'):
        """Send message as Claude (gold name prefix)."""
        lines = [message[i:i+200] for i in range(0, len(message), 200)]
        for line in lines:
            safe = line.replace('"', '\\"').replace('\\n', ' ')
            self.cmd(
                f'tellraw {target} ["",{{"text":"[Claude] ","color":"gold","bold":true}},'
                f'{{"text":"{safe}","color":"white"}}]'
            )

rcon = RconClient()

# ── Claude API ────────────────────────────────────────────────────────────────
def ask_claude(question: str, player: str) -> str:
    try:
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=200,
            system=SYSTEM_PROMPT,
            messages=[{
                'role': 'user',
                'content': f'Spiller "{player}" spørger: {question}'
            }]
        )
        return resp.content[0].text.strip()
    except ImportError:
        return 'anthropic-pakken mangler. Kør: pip install anthropic'
    except Exception as e:
        return f'Fejl: {e}'

# ── Command handlers ──────────────────────────────────────────────────────────
def handle_tp(player: str, args: str):
    key = args.strip().lower()
    if key in KNOWN_PLACES:
        x, y, z, name = KNOWN_PLACES[key]
        rcon.cmd(f'tp {player} {x} {y} {z}')
        rcon.tellraw_claude(f'Teleporterer {player} til {name}!', f'@a')
    else:
        options = ', '.join(sorted(set(v[3] for v in KNOWN_PLACES.values())))
        rcon.tellraw_claude(f'Kender ikke "{args}". Kendte steder: {options}')

def handle_byg(player: str, args: str):
    rcon.tellraw_claude(
        f'Byg-kommando modtaget: "{args}". '
        f'Brug osm_builder.py --bbox ... for at starte et nyt byg. '
        f'(Automatisk byg via chat er endnu ikke implementeret)'
    )

def handle_info(player: str):
    rcon.cmd(f'tellraw @a {{"text":"{INFO_TEXT}"}}')

def handle_help(player: str):
    rcon.cmd(f'tellraw @a {{"text":"{HELP_TEXT}"}}')

def handle_claude(player: str, question: str):
    rcon.tellraw_claude('Et øjeblik...', f'@a')
    answer = ask_claude(question, player)
    rcon.tellraw_claude(answer)

# ── Log parser ────────────────────────────────────────────────────────────────
# Matches: [HH:MM:SS] [Server thread/INFO]: <PlayerName> message
CHAT_RE = re.compile(
    r'\[[\d:]+\] \[Server thread/INFO\]: <(\w+)> (.+)'
)
# Also matches: [HH:MM:SS] [Server thread/INFO]: PlayerName joined the game
JOIN_RE = re.compile(
    r'\[[\d:]+\] \[Server thread/INFO\]: (\w+) joined the game'
)

def process_line(line: str):
    line = line.strip()

    # Welcome joining players
    m = JOIN_RE.search(line)
    if m:
        player = m.group(1)
        print(f'[JOIN] {player}')
        rcon.tellraw_claude(
            f'Velkommen {player}! Skriv !hjælp for kommandoer. '
            f'Du er i et 1:1 kort over Hvidovre, Danmark.'
        )
        return

    # Parse chat messages
    m = CHAT_RE.search(line)
    if not m:
        return

    player  = m.group(1)
    message = m.group(2).strip()
    print(f'[CHAT] <{player}> {message}')

    lower = message.lower()

    if lower in ('!hjælp', '!help', '!hjaelp'):
        handle_help(player)
    elif lower in ('!info', '!status'):
        handle_info(player)
    elif lower.startswith('!tp '):
        handle_tp(player, message[4:].strip())
    elif lower.startswith('!teleport '):
        handle_tp(player, message[10:].strip())
    elif lower.startswith('!byg ') or lower.startswith('!build '):
        args = message.split(' ', 1)[1].strip()
        handle_byg(player, args)
    elif lower.startswith('!claude '):
        handle_claude(player, message[8:].strip())
    elif lower.startswith('!'):
        rcon.tellraw_claude(f'Ukendt kommando. Skriv !hjælp for hjælp.')

# ── Main loop ─────────────────────────────────────────────────────────────────
def tail_docker_logs():
    print(f'[INFO] Starter log-overvågning af container "{CONTAINER}"...')
    while True:
        try:
            proc = subprocess.Popen(
                ['docker', 'logs', '-f', '--tail', '0', CONTAINER],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT
            )
            print('[INFO] Forbundet til docker logs.')
            for raw in proc.stdout:
                line = raw.decode('utf-8', 'replace')
                try:
                    process_line(line)
                except Exception as e:
                    print(f'[ERR] process_line: {e}')
            proc.wait()
            print('[WARN] docker logs afsluttet, genstarter om 5s...')
        except Exception as e:
            print(f'[ERR] tail_docker_logs: {e}')
        time.sleep(5)

def main():
    if DRY_RUN:
        print('[DRY-RUN] Tester log-parsing uden at sende RCON-kommandoer')

    # Announce startup
    rcon.tellraw_claude('Chat-agent startet. Skriv !hjælp for kommandoer.')
    print(f'[INFO] Chat-agent klar. Model: {CLAUDE_MODEL}')

    tail_docker_logs()

if __name__ == '__main__':
    main()
