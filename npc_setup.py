#!/usr/bin/env python3
"""
NPC setup — opretter Claude NPC i Minecraft via RCON + Citizens2.

Kræver: Citizens2 plugin installeret (tilføj til docker-compose.yml PLUGINS)

Usage:
    python3 npc_setup.py [--create | --move | --delete]
"""

import socket, struct, time, sys

RCON_HOST, RCON_PORT, RCON_PASS = '127.0.0.1', 25575, 'NME21o3#'

# Hvidovrehavn position (v3 byg)
NPC_NAME     = 'Claude'
NPC_X        = 8440
NPC_Y        = -59   # 1 over build surface
NPC_Z        = 7666

def connect():
    s = socket.socket(); s.settimeout(10); s.connect((RCON_HOST, RCON_PORT))
    def pkt(rid, rt, p):
        d = p.encode('utf-8') + b'\x00\x00'
        s.send(struct.pack('<iii', len(d)+8, rid, rt) + d)
        r = b''
        while len(r) < 4 or len(r) < struct.unpack('<i', r[:4])[0]+4:
            c = s.recv(4096)
            if not c: break
            r += c
        return r[12:-2].decode('utf-8', 'replace')
    pkt(1, 3, RCON_PASS); return s, pkt

def cmd(pkt, c):
    r = pkt(2, 2, c)
    print(f'> {c}\n  → {r}')
    return r

def create_npc():
    s, pkt_ = connect()
    c = lambda x: cmd(pkt_, x)

    # Forceload NPC-position
    c(f'forceload add {NPC_X-16} {NPC_Z-16} {NPC_X+16} {NPC_Z+16}')
    time.sleep(0.5)

    # Citizens2 kommandoer
    c(f'npc create {NPC_NAME} --at {NPC_X},{NPC_Y},{NPC_Z} --type PLAYER')
    time.sleep(0.3)
    c(f'npc skin {NPC_NAME}')          # brug standard player skin
    c(f'npc look')                      # vend mod nærmeste spiller
    c(f'npc select')
    c(f'npc trait sentineltrait')       # stå stille
    c(f'npc rename §6{NPC_NAME}§r')    # guld farve på navn

    # Proximity greeting via Citizens trait (hvis installeret)
    # Alternativt: brug chat_agent.py til at håndtere !claude kommandoer

    c(f'forceload remove {NPC_X-16} {NPC_Z-16} {NPC_X+16} {NPC_Z+16}')
    s.close()
    print(f'\nNPC "{NPC_NAME}" oprettet ved X={NPC_X} Y={NPC_Y} Z={NPC_Z}')
    print('Tip: Brug chat_agent.py til at håndtere "!claude <spørgsmål>" kommandoer')

def move_npc():
    """Flyt NPC til ny position (kræver valgt NPC)."""
    s, pkt_ = connect()
    c = lambda x: cmd(pkt_, x)
    c(f'npc select --id 1')  # justér NPC ID
    c(f'npc tp {NPC_X} {NPC_Y} {NPC_Z}')
    s.close()

def test_citizens():
    """Test om Citizens2 er installeret."""
    s, pkt_ = connect()
    r = pkt_(2, 2, 'npc list')
    print(f'Citizens test: {r}')
    if 'unknown command' in r.lower() or 'npc' not in r.lower():
        print('\nCitizens2 er IKKE installeret.')
        print('Tilføj til docker-compose.yml PLUGINS:')
        print('  https://ci.citizensnpcs.co/job/citizens2/lastSuccessfulBuild/artifact/dist/Citizens-2.0.35-SNAPSHOT.jar')
    else:
        print('\nCitizens2 er installeret ✓')
    s.close()

if __name__ == '__main__':
    if '--create' in sys.argv:
        create_npc()
    elif '--move' in sys.argv:
        move_npc()
    elif '--test' in sys.argv:
        test_citizens()
    else:
        test_citizens()
        print('\nBrug: python3 npc_setup.py --create  (efter Citizens2 er installeret)')
