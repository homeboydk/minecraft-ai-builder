# Minecraft AI Builder

Automatisk OSM→Minecraft byggesystem + in-game AI NPC og chat-kommandoer.

## Hvad projektet gør

- Henter kortdata fra OpenStreetMap (Overpass API)
- Bygger 1:1 skala byområder i Minecraft via RCON
- Bygninger med vinduer, veje med asfalt/fortove/gadetræer, vand, strand m.m.
- (Planlagt) In-game AI NPC og chat-kommandosystem

## Server

- Paper 1.21.1, Docker (`docker-compose.yml`)
- RCON: `127.0.0.1:25575`
- Flat creative world, ground: Y=-61 (grass), build surface: Y=-60

## Færdige byggerier

| Fil | Beskrivelse | MC koordinater |
|-----|-------------|----------------|
| `eiffel_tower.py` | Eiffeltårnet, 2/3 skala | X=200, Z=200 |
| `hvidovre_v3.py` | Hvidovrehavn + strand + Stentoftevej, 1:1 | X=8000..10326, Z=6219..8000 |

## Hurtig start

```bash
# Kør et byg (kræver kørende Minecraft server)
python3 hvidovre_v3.py

# Genoptag fra checkpoint (planlagt)
python3 osm_builder.py --bbox 55.614,12.470,55.630,12.507 --resume
```

## Koordinater i spillet

```
/tp 8440 -30 7666   ← Hvidovrehavn (havn)
/tp 9163 60 7109    ← Overblik over hele bygget
/tp 9509 -40 7889   ← Hvidovre strand
```

---

Se [PLAN.md](PLAN.md) for stabilitetsplan og roadmap.
