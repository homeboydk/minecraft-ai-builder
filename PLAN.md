# Plan: Minecraft AI Builder — Roadmap & Stabilitet

## Status

- [x] OSM-download og parsing (bygninger, veje, vand, strand, landuse, moler/kajer)
- [x] Strip-baseret byg med forceload (løste chunk-loading problemet)
- [x] Detaljeret byg: vinduer (glasruder), asfaltveje, fortove, gadetræer
- [x] Hvidovrehavn 1:1 bygget og verificeret (1,07M RCON kommandoer)
- [ ] Chat-kommandosystem (se nedenfor)
- [ ] AI NPC (se nedenfor)
- [ ] Stabilt genoptagbart byggesystem

---

## Krav 1: Chat-kommandosystem

**Mål:** Skriv en kommando i Minecraft-chatten og Claude svarer/udfører den via RCON.

### Arkitektur

```
Spilleren skriver: !byg hvidovre
         ↓
log_watcher.py overvåger server.log (eller RCON "list" polling)
         ↓
Parser kommandoen, sender til Claude API (claude-haiku-4-5 for hurtighed)
         ↓
Claude svarer og/eller sender RCON-kommandoer tilbage til serveren
         ↓
Svar vises i chatten: /tellraw @a {"text":"[AI] ..."}
```

### Kommandoformater
- `!byg <område>` — byg et OSM-område
- `!tp <stednavn>` — teleporter til et bygget sted
- `!info` — vis hvad der er bygget
- `!hjælp` — vis tilgængelige kommandoer
- Fritext uden `!` → sendes til Claude som spørgsmål

### Implementation
- `chat_agent.py`: Log-watcher + RCON-responder
- Kræver adgang til `server.log` (mount i Docker eller via `docker logs -f minecraft`)
- Alternativ: Poll RCON `/list` + `say` kommandoer virker ikke til at læse chat
- **Bedste løsning**: Brug Paper-plugin eller læs direkte fra container log-stream

### Tekniske noter
- `docker logs -f minecraft 2>&1 | grep "<"` — filtrerer chatbeskeder
- Format i log: `[HH:MM:SS] [Server thread/INFO]: <SpillerNavn> besked`
- Claude model: `claude-haiku-4-5` via LiteLLM på `http://10.1.1.10:4000`

---

## Krav 2: AI NPC

**Mål:** En NPC i spillet der repræsenterer Claude — kan svare på spørgsmål og give information om byggeriet.

### Arkitektur

**Option A: Citizens2 plugin (anbefalet)**
- Installer Citizens2 plugin på Paper-serveren
- NPC oprettes via: `/npc create Claude --type PLAYER`
- Chat-listener via Citizens API (kræver lille plugin eller scripts API)
- NPC's svar injiceres via RCON: `/npc select <id>` → custom dialog

**Option B: Fake player via protocol (avanceret)**
- Brug ViaVersion + en bot-library (fx Mineflayer via Node.js)
- Botten forbinder som en rigtig spiller med navn "Claude"
- Kan bevæge sig, chatte, reagere på proximity

**Anbefalet start: Option A (Citizens2)**
```
# Tilføj til docker-compose.yml PLUGINS:
https://ci.citizensnpcs.co/job/citizens2/lastSuccessfulBuild/artifact/dist/Citizens-2.x.x-SNAPSHOT.jar
```

NPC-adfærd:
- Stå ved havnen (X=8440, Z=7666)
- Reagér når spiller kommer inden for 5 blokke (via Citizens proximity events)
- Eller: Reagér via chat-kommandosystem (`!claude <spørgsmål>`)

---

## Stabilitetsplan

### Problem der blev løst
Første forsøg: 295k RCON-kommandoer, nul blokke placeret.
**Årsag**: Forceload af 16.240 chunks på én gang — server nåede ikke at loade dem inden fills kørte.
**Løsning**: Strip-baseret byg (128 blok-strips, ~153 chunks ad gangen).

### Planlagte forbedringer

#### 1. Checkpoint-system
```python
# checkpoint.json gemmes efter hvert strip
{
  "script": "hvidovre_v3.py",
  "bbox": [55.614, 12.470, 55.630, 12.507],
  "mc_origin": [8000, 8000],
  "completed_strips": [1, 2, 3, 4, 5],
  "total_strips": 14,
  "cmd_count": 541615,
  "timestamp": "2026-03-09T22:45:00"
}
```
Genoptag med `--resume checkpoint.json`

#### 2. Post-strip verifikation
```python
def verify_strip(strip_z0, strip_z1, sample_n=10):
    """Sample N tilfældige punkter, returnér antal non-air blokke."""
    ...
    if found == 0:
        print(f"ADVARSEL: Strip {strip_z0}-{strip_z1} har 0 blokke — retry")
        return False
    return True
```

#### 3. `save-all flush` per strip
```python
cmd("save-all flush")   # Inden forceload remove
time.sleep(1.0)
forceload_strip(strip_z0, strip_z1, False)
```

#### 4. Kør med nohup
```bash
nohup python3 osm_builder.py --bbox ... > build.log 2>&1 &
```

#### 5. Generisk `osm_builder.py`
Parametriseret script der accepterer:
- `--bbox S,W,N,E`
- `--origin X,Z`
- `--scale 1.0`
- `--resume <checkpoint>`
- `--dry-run`

---

## Fremtidige byggerier

| Område | Bbox | Skala | Prioritet |
|--------|------|-------|-----------|
| Hele Hvidovre kommune | 55.60,12.44,55.65,12.55 | 1:1 | Høj |
| København centrum | 55.665,12.545,55.695,12.615 | 1:1 | Medium |
| Danmark (oversigt) | 54.5,8.0,57.8,15.3 | 1:100 | Lav |
