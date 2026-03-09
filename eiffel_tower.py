#!/usr/bin/env python3
"""Eiffel Tower Minecraft Build
330m real → 220 blocks (2/3 scale, fits Y=99 to Y=319).
"""
import socket, struct, time, math

HOST, PORT, PASS = '127.0.0.1', 25575, 'NME21o3#'

def connect():
    s = socket.socket(); s.settimeout(10); s.connect((HOST, PORT))
    def pkt(rid, rt, p):
        d = p.encode('utf-8') + b'\x00\x00'
        s.send(struct.pack('<iii', len(d)+8, rid, rt) + d)
        r = b''
        while len(r) < 4 or len(r) < struct.unpack('<i', r[:4])[0]+4:
            r += s.recv(4096)
        return r[12:-2].decode('utf-8', 'replace')
    pkt(1, 3, PASS); return s, pkt

_s, _pkt = connect()
cmd_count = 0

def cmd(c):
    global _s, _pkt, cmd_count
    try:
        r = _pkt(2, 2, c); cmd_count += 1
        if cmd_count % 100 == 0:
            print(f"  [{cmd_count}]", end='\r', flush=True)
        return r
    except Exception:
        time.sleep(0.5)
        try: _s.close()
        except: pass
        _s, _pkt = connect()
        return _pkt(2, 2, c)

def F(x1,y1,z1, x2,y2,z2, blk, mode=""):
    if x1>x2: x1,x2=x2,x1
    if y1>y2: y1,y2=y2,y1
    if z1>z2: z1,z2=z2,z1
    vol = (x2-x1+1)*(y2-y1+1)*(z2-z1+1)
    if vol > 32768:
        dx,dy,dz = x2-x1+1, y2-y1+1, z2-z1+1
        if dx >= dy and dx >= dz:
            m = x1+dx//2-1
            F(x1,y1,z1,m,y2,z2,blk,mode); F(m+1,y1,z1,x2,y2,z2,blk,mode)
        elif dy >= dz:
            m = y1+dy//2-1
            F(x1,y1,z1,x2,m,z2,blk,mode); F(x1,m+1,z1,x2,y2,z2,blk,mode)
        else:
            m = z1+dz//2-1
            F(x1,y1,z1,x2,y2,m,blk,mode); F(x1,y1,m+1,x2,y2,z2,blk,mode)
        return
    cmd(f"fill {x1} {y1} {z1} {x2} {y2} {z2} {blk}" + (f" {mode}" if mode else ""))

def S(x,y,z,blk): cmd(f"setblock {x} {y} {z} {blk}")

def line(x1,y1,z1, x2,y2,z2, blk):
    n = max(abs(x2-x1), abs(y2-y1), abs(z2-z1))
    if n == 0: S(x1,y1,z1,blk); return
    for i in range(n+1):
        t=i/n
        S(round(x1+t*(x2-x1)), round(y1+t*(y2-y1)), round(z1+t*(z2-z1)), blk)

# ── MATERIALS ──
DG   = "minecraft:gray_concrete"
GRAY = "minecraft:light_gray_concrete"
AIR  = "minecraft:air"
GR   = "minecraft:grass_block"
DT   = "minecraft:dirt"
SL   = "minecraft:sea_lantern"
BARS = "minecraft:iron_bars"
IRON = "minecraft:iron_block"

# ── SCALE ──
# Eiffel Tower: 330m, base ±62m each leg from center
# Minecraft: Y=99 to Y=319 = 220 blocks → scale = 220/330 ≈ 2/3
CX, GY, CZ = 200, 99, 200
SCALE = 220/330
def sc(m): return max(1, int(round(m*SCALE)))

# Heights (blocks above ground)
H1   = sc(57)    # 38  — 1st platform
H2   = sc(115)   # 77  — 2nd platform
H3   = sc(276)   # 184 — 3rd platform (legs converge)
HTOP = 220       # antenna tip

# Leg center X/Z offset from tower center at given height
# Interpolated from real Eiffel Tower proportions × 2/3
PROFILE = [
    (0,     41),
    (sc(12), 33),
    (sc(22), 26),
    (sc(32), 19),
    (H1,    13),   # 1st floor
    (sc(72), 8),
    (H2,     5),   # 2nd floor
    (sc(200), 2),
    (H3,     0),   # 3rd floor — fully merged
]

def leg_off(h):
    for i in range(len(PROFILE)-1):
        y0,o0 = PROFILE[i]; y1,o1 = PROFILE[i+1]
        if y0 <= h <= y1:
            t = (h-y0)/(y1-y0) if y1>y0 else 0
            return int(round(o0+t*(o1-o0)))
    return 0

# Pillar half-size at each height (gives thick visible pillars)
def leg_ps(h):
    if h <= sc(15):  return 4   # 9×9 at very base
    if h <= sc(30):  return 3   # 7×7 lower section
    if h <= H1:      return 2   # 5×5 up to 1st floor
    if h <= H2:      return 1   # 3×3 up to 2nd floor
    return 0                    # 1×1 / merged shaft above

CORNERS = [(1,1),(1,-1),(-1,1),(-1,-1)]  # SE NE SW NW

print(f"Eiffel Tower 2/3 scale: base ±{leg_off(0)} blk, height {HTOP}")
print(f"Platforms: 1st Y{GY+H1}, 2nd Y{GY+H2}, 3rd Y{GY+H3}, tip Y{GY+HTOP}")

# ─────────────────────────────
# 0. CLEAR
# ─────────────────────────────
print("0/9 Clearing...")
F(CX-120, GY-15, CZ-120, CX+120, GY+225, CZ+120, AIR)
F(CX-120, GY-5,  CZ-120, CX+120, GY-1,   CZ+120, DT)
F(CX-120, GY,    CZ-120, CX+120, GY,      CZ+120, GR)
# Concrete plaza under base
F(CX-50, GY, CZ-50, CX+50, GY, CZ+50, GRAY)

# ─────────────────────────────
# 1. FOUR CURVED LEGS
# ─────────────────────────────
print("1/9 Legs...")
for h in range(1, H3+1):
    y   = GY + h
    off = leg_off(h)
    ps  = leg_ps(h)

    if off <= 2:
        # Legs fully converged → solid central shaft
        F(CX-3, y, CZ-3, CX+3, y, CZ+3, DG)
        continue

    for sx, sz in CORNERS:
        lx = CX + sx*off
        lz = CZ + sz*off
        F(lx-ps, y, lz-ps, lx+ps, y, lz+ps, DG)

# ─────────────────────────────
# 2. HORIZONTAL CONNECTING RINGS (every 5 blocks)
# ─────────────────────────────
print("2/9 Horizontal rings...")
for h in range(0, H3, 5):
    off = leg_off(h)
    ps  = leg_ps(h)
    y   = GY + h + 1
    if off <= 2: break

    # Connect between adjacent legs on each face (outer edges)
    outer = off + ps   # outermost block of the leg

    # N edge: x from (-outer) to (+outer), z = CZ - outer
    for x in range(-outer, outer+1):
        S(CX+x, y, CZ-outer, DG)
        S(CX+x, y, CZ+outer, DG)
    # W/E edges: z from (-outer) to (+outer), x = ±outer
    for z in range(-outer+1, outer):
        S(CX-outer, y, CZ+z, DG)
        S(CX+outer, y, CZ+z, DG)

# ─────────────────────────────
# 3. CROSS-BRACING (full-section X diagonals per face)
#    Two X patterns: ground→H1 and H1→H2
# ─────────────────────────────
print("3/9 Cross-bracing diagonals...")

def cross_brace_section(h_bot, h_top):
    o_b  = leg_off(h_bot);  o_t  = leg_off(h_top)
    ps_b = leg_ps(h_bot);   ps_t = leg_ps(h_top)
    yb   = GY + h_bot + 1;  yt   = GY + h_top
    if o_b <= 0 or o_t <= 0: return
    ob = o_b + ps_b;  ot = o_t + ps_t  # outer extents
    # N face X
    line(CX-ob, yb, CZ-ob, CX+ot, yt, CZ-ot, DG)
    line(CX+ob, yb, CZ-ob, CX-ot, yt, CZ-ot, DG)
    # S face X
    line(CX-ob, yb, CZ+ob, CX+ot, yt, CZ+ot, DG)
    line(CX+ob, yb, CZ+ob, CX-ot, yt, CZ+ot, DG)
    # W face X
    line(CX-ob, yb, CZ-ob, CX-ot, yt, CZ+ot, DG)
    line(CX-ob, yb, CZ+ob, CX-ot, yt, CZ-ot, DG)
    # E face X
    line(CX+ob, yb, CZ-ob, CX+ot, yt, CZ+ot, DG)
    line(CX+ob, yb, CZ+ob, CX+ot, yt, CZ-ot, DG)

# Lower section: ground → 1st floor (split in half so diagonals aren't too long)
h_mid = H1 // 2
cross_brace_section(0, h_mid)
cross_brace_section(h_mid, H1)
# Middle section: 1st → 2nd floor
cross_brace_section(H1, H2)

# ─────────────────────────────
# 4. BASE ARCHES  (4 curved arches connecting adjacent legs)
# ─────────────────────────────
print("4/9 Base arches...")
arch_peak = sc(20)   # ~13 blocks
base_outer = leg_off(0) + leg_ps(0)  # 41+4 = 45

for i in range(2*base_outer+1):
    t  = i / (2*base_outer)
    yt = int(arch_peak * math.sin(math.pi * t))
    xi = CX - base_outer + i
    zi = CZ - base_outer + i
    yy = GY + 1 + yt
    for dy in range(3):  # 3 blocks wide arches
        S(xi,            yy+dy, CZ-base_outer, DG)   # N arch
        S(xi,            yy+dy, CZ+base_outer, DG)   # S arch
        S(CX-base_outer, yy+dy, zi,            DG)   # W arch
        S(CX+base_outer, yy+dy, zi,            DG)   # E arch

# ─────────────────────────────
# 5. 1st FLOOR PLATFORM  (~38 blocks up)
# ─────────────────────────────
print("5/9 1st floor...")
p1h  = GY + H1
p1sz = sc(14) + 2  # slightly wider than the legs at H1
F(CX-p1sz,   p1h,   CZ-p1sz,   CX+p1sz,   p1h+3, CZ+p1sz,   DG)
F(CX-p1sz+2, p1h+1, CZ-p1sz+2, CX+p1sz-2, p1h+2, CZ+p1sz-2, GRAY)
# Railing
for x in range(-p1sz, p1sz+1):
    S(CX+x, p1h+4, CZ-p1sz, BARS)
    S(CX+x, p1h+4, CZ+p1sz, BARS)
for z in range(-p1sz+1, p1sz):
    S(CX-p1sz, p1h+4, CZ+z, BARS)
    S(CX+p1sz, p1h+4, CZ+z, BARS)
# Underside lights
for dx in range(-p1sz+2, p1sz-1, 4):
    for dz in range(-p1sz+2, p1sz-1, 4):
        S(CX+dx, p1h-1, CZ+dz, SL)

# ─────────────────────────────
# 6. 2nd FLOOR PLATFORM  (~77 blocks up)
# ─────────────────────────────
print("6/9 2nd floor...")
p2h  = GY + H2
p2sz = sc(9)
F(CX-p2sz,   p2h,   CZ-p2sz,   CX+p2sz,   p2h+3, CZ+p2sz,   DG)
F(CX-p2sz+1, p2h+1, CZ-p2sz+1, CX+p2sz-1, p2h+2, CZ+p2sz-1, GRAY)
for x in range(-p2sz, p2sz+1):
    S(CX+x, p2h+4, CZ-p2sz, BARS)
    S(CX+x, p2h+4, CZ+p2sz, BARS)
for z in range(-p2sz+1, p2sz):
    S(CX-p2sz, p2h+4, CZ+z, BARS)
    S(CX+p2sz, p2h+4, CZ+z, BARS)
for dx in range(-p2sz+1, p2sz, 3):
    for dz in range(-p2sz+1, p2sz, 3):
        S(CX+dx, p2h-1, CZ+dz, SL)

# ─────────────────────────────
# 7. UPPER SHAFT RINGS  (already built as merged shaft in step 1)
# ─────────────────────────────
print("7/9 Upper shaft rings...")
for h in range(H2, H3, 10):
    y = GY + h
    F(CX-4, y, CZ-4, CX+4, y, CZ+4, DG)

# ─────────────────────────────
# 8. 3rd FLOOR PLATFORM  (~184 blocks up)
# ─────────────────────────────
print("8/9 3rd floor...")
p3h  = GY + H3
p3sz = sc(6)
F(CX-p3sz,   p3h,   CZ-p3sz,   CX+p3sz,   p3h+3, CZ+p3sz,   DG)
F(CX-p3sz+1, p3h+1, CZ-p3sz+1, CX+p3sz-1, p3h+2, CZ+p3sz-1, GRAY)
for x in range(-p3sz, p3sz+1):
    S(CX+x, p3h+4, CZ-p3sz, BARS)
    S(CX+x, p3h+4, CZ+p3sz, BARS)
for z in range(-p3sz+1, p3sz):
    S(CX-p3sz, p3h+4, CZ+z, BARS)
    S(CX+p3sz, p3h+4, CZ+z, BARS)
S(CX, p3h-1, CZ, SL)

# ─────────────────────────────
# 9. SPIRE  (3rd floor → Y=319)
# ─────────────────────────────
print("9/9 Spire...")
sp_bot = p3h + 5
sp_top = GY + HTOP
span   = sp_top - sp_bot
for y in range(sp_bot, sp_top+1):
    t = (y - sp_bot) / span
    if t < 0.2:   F(CX-2, y, CZ-2, CX+2, y, CZ+2, DG)
    elif t < 0.6: F(CX-1, y, CZ-1, CX+1, y, CZ+1, DG)
    else:         S(CX, y, CZ, DG)
S(CX, sp_top-1, CZ, IRON)
S(CX, sp_top,   CZ, SL)

# ── DONE ──
cmd(f"tp HomeboyDK {CX} {GY + HTOP//2} {CZ - leg_off(0) - 80}")
cmd("gamemode creative HomeboyDK")

print(f"\n✅ {cmd_count} commands")
print(f"   Y{GY} – Y{GY+HTOP} (tip at Y=319)")
print(f"   Player teleported {leg_off(0)+80} blocks north at mid-height")
