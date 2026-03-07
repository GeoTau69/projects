# Workspace `/home/geo/projects/`

> Monorepo, Fedora 43 · owner: `geo` · Gitea + GitHub

## Infrastruktura

- **Git remoty**: Gitea `localhost:3000/geo/projects` (primární) + GitHub mirror
  - Push: `git push gitea main && git push github main`
  - Gitea credentials: `~/.git-credentials` · GitHub: SSH `~/.ssh/id_ed25519` + `gh` CLI
- **Systém**: Fedora 43, Btrfs, Python 3.14
- **Git identity**: `geo <jk@kompi.cz>`, default branch `main`

## Síťové adresy

Fedora server: LAN `192.168.0.101` · Tailscale `fedora` / `100.117.55.88`

| Služba | Lokální | LAN | Tailscale |
|--------|---------|-----|-----------|
| Gitea | :3000 | 192.168.0.101:3000 | fedora:3000 |
| docs | :8080 | 192.168.0.101:8080 | fedora:8080 |
| fedoraOS | :8081 | 192.168.0.101:8081 | fedora:8081 |
| backup-dashboard | :8090 | 192.168.0.101:8090 | fedora:8090 |
| dashboard | :8099 | 192.168.0.101:8099 | fedora:8099 |
| agent-ui | :8100 | 192.168.0.101:8100 | fedora:8100 |
| web-edit | :8765 | 192.168.0.101:8765 | fedora:8765 · [funnel](https://fedora.tail41712d.ts.net/) |

## Konvence

- Kód/komentáře: **čeština** · kódování: **UTF-8**
- Každý projekt: self-contained, žádné cross-imports mezi projekty
- Každý projekt má: `project.yaml` (metadata) + `CLAUDE.md` (kontext)
- Backup soubory (`*.backup-*`) neverzovat · privilegované příkazy přes `sudo`

### Stručnost výstupu — POVINNÉ, úspora output tokenů

<!-- DOKUMENTACE: Output tokeny platí uživatel. Každý zbytečný text = zbytečný náklad.
     Diff výpisy (● Update... ⎿ Added X lines...) generuje Claude Code CLI LOKÁLNĚ
     bez spotřeby tokenů — to je OK. Problém jsou pouze textové zprávy modelu
     mezi tool cally — ty stojí output tokeny a musí být minimální. -->

**TOTO JE NEJVYŠŠÍ PRIORITA pro všechny modely.**

- **ŽÁDNÝ komentář mezi tool cally** pokud není architektonické rozhodnutí
- Při editaci/vytváření: žádný text, rovnou tool call
- Na začátku úkolu: max 3 bullet points co se změní
- Na konci úkolu: max 3 bullet points co se změnilo
- Shrnutí, tabulky, návrhy variant: **zachovat plně**
- Mechanický průběh, debug, "teď udělám X": **VYNECHAT**
- Uživatel platí za KAŽDÝ output token — plýtvání = plýtvání penězi

## Dělba práce — Model routing

| Model | Role | Odpovědnost | Kdy použít |
|-------|------|-------------|------------|
| **Opus 4.6** | Architekt + šéf | Návrh architektury, obsah a struktura MD/JSON, audit, specifikace, review | Nové systémy, architektonická rozhodnutí, review workerů |
| **Sonnet 4.6** | SW inženýr | Implementace **přesně** dle Opus specifikace, kód + **vlastník všech `CLAUDE.md`** | Psaní kódu, úpravy souborů, aktualizace kontextu projektu |
| **Haiku 4.5** | Dokumentarista | **Pouze** generování `docs/data/{projekt}.json` dle Opus spec → HTML | `docs/data/{projekt}.json` pipeline — čte, negeneruje CLAUDE.md |

### Řídící smyčka (Opus Directive pattern)

```
Opus: DIRECTIVE (co + jak + proč) → MEMORY.md
  → Worker (Sonnet/Haiku): implementuje PŘESNĚ dle spec
    → Worker: hlásí DONE + co udělal → MEMORY.md
      → Opus: REVIEW (povinný!) → ✅ OK nebo 🔄 REWORK
```

**"Bez spojení není velení"** — Opus je velitel, ne poradce. Worker bez direktivy bloudí, velitel bez review je slepý.

**Opus review protokol** (povinný po každém worker handbacku):
1. **Přečti** MEMORY.md — co worker zapsal jako DONE
2. **Zkontroluj** klíčové soubory (diff nebo read změněných souborů)
3. **Ověř live** (curl, test) pokud je to UI/služba
4. **Reportuj** uživateli: ✅ OK nebo 🔄 REWORK + co opravit

**Pravidla pro workery (Sonnet, Haiku):**
1. **Nereinterpretuj** Opus specifikaci — implementuj přesně jak je zadáno
2. **Neměň design** — pokud nesouhlasíš, zapiš `ESCALATION: důvod` do MEMORY.md a ČEKEJ
3. **Hlásit dokončení** — po implementaci zapiš do MEMORY.md co jsi udělal
4. **Neinformuj jiný worker po svém** — Haiku dostává instrukce od Opuse, ne od Sonnetu

### Worker Self-Check Protocol (povinný před hlášením DONE)

Před tím, než worker řekne "hotovo", musí provést auto-review a napsat **DELTA MANIFEST** do MEMORY.md. Formát:

```
## DELTA MANIFEST — {projekt}/{task} (Worker, YYYY-MM-DD HH:MM)

**Opus Spec:** [co bylo zadáno — 1 řádek shrnutí]

✅ SPLNĚNO — co je 100% hotovo:
- [checklist item 1]
- [checklist item 2]

⚠️ ČÁSTEČNĚ / NEJISTOTA — co není úplné nebo nejsem si jistý:
- [uncertainty item 1 + důvod]
- [uncertainty item 2 + důvod]

🔴 ESCALATION pro Opus REVIEW — co KONKRÉTNĚ má Opus zkontrolovat:
1. [konkrétní test/kontrola 1]
2. [konkrétní test/kontrola 2]

🔗 REFERENČNÍ INFO:
- Klíčové soubory: [cesty]
- Build output: [stdout shrnutí]
- Live status: [curl result / test status]

→ WAITING FOR OPUS AUTO-REVIEW
```

**Klíčová pravidla pro DELTA MANIFEST:**
- **Konkrétnost** — "HTML se generoval bez chyby" NENÍ konkrétní. "HTML schema check PASS, ale DOM struktura sekcí neověřena" — JE konkrétní.
- **Self-test first** — worker musí SAM otestovat co je možné (curl, build.py, schema validator). Teprve pak eskaluje.
- **Escalation není selhání** — je to NORMÁLNÍ. Worker říká: "toto jsem otestoval ✓, toto potřebuji abyste zkontrolovali ✓"
- **Bez eskalace = červená vlajka** — pokud worker napíše "DONE" bez ⚠️ a 🔴 sekcí, Opus reviewuje s vyšší skepsí.

### Vlastnictví obsahu

| Co | Kdo rozhoduje | Kdo implementuje |
|----|--------------|-----------------|
| Struktura a obsah MD souborů | **Opus** | Sonnet |
| JSON design (docs pipeline) | **Opus** | Haiku |
| `{projekt}/CLAUDE.md` | Opus (design) | **Sonnet** (píše) |
| Kód (Python, JS, ...) | Opus (spec) | **Sonnet** (kóduje) |
| `docs/data/{projekt}.json` | Opus (spec) | **Haiku** (generuje) |

Cenový princip: Opus ($75/M out) jen na rozhodování + review. Sonnet ($15/M out) na implementaci + CLAUDE.md. Haiku ($4/M out) na JSON/HTML pipeline.

## Kontextové soubory

| Soubor | Načítání | Účel |
|--------|----------|------|
| `MODEL.md` | Manuálně | Session log (posledních 5 záznamů) + aktuální stav |
| `todo.md` | Manuálně | Centrální backlog |
| `docs/INFO.md` | Manuálně | Portál průvodce — viz **ℹ️ Info** (http://localhost:8080) |
| `memory/MEMORY.md` | **Auto** | Volatile session state — aktuální úkol, next steps |

**Auto-memory:** `~/.claude/projects/-home-geo/memory/MEMORY.md` (symlink z `-home-geo-projects/`)

## Zlaté pravidlo — Session persistence

<!-- DOKUMENTACE: Dvě signální fráze řídí ukládání kontextu mezi sessions/modely.
     "štafeta" = lehký handoff (v rámci session, bez git). Typicky před /model switch.
     "konec zvonec" = plný checkpoint (git commit+push). Před odhlášením.
     Obě fráze jsou case-insensitive. Platí pro všechny modely bez výjimky. -->

### Signální fráze

| Fráze | Kdy | Co model udělá |
|-------|-----|-----------------|
| **`ulož si práci`** | Kdykoliv během session | Aktualizuje MEMORY.md s aktuálním stavem. Bez git, bez sanitace. Napíše: *"Uloženo."* |
| **`štafeta`** | Předání jinému modelu (před `/model`) | Aktualizuje MEMORY.md se shrnutím + specifikací pro dalšího. Bez git, bez sanitace. Napíše: *"Štafeta předána — přepni model."* |
| **`konec zvonec`** | Konec práce, odhlášení | Sanitace + MEMORY.md + MODEL.md session log + git commit + push. Napíše: *"Vše synchronizováno — můžeš se odhlásit."* |

### `štafeta` — postup

<!-- Lehký handoff: žádný git, žádná sanitace. Cíl = předat kontext dalšímu modelu. -->

1. Aktualizuje MEMORY.md (cesty viz tabulka v Kontextové soubory)
   - Co jsem udělal (3-5 bodů)
   - Co má příští model udělat (konkrétní specifikace)
   - Rozpracované soubory (cesty)
2. Napíše: *"Štafeta předána — přepni model."*

### `konec zvonec` — postup

<!-- Plný checkpoint: sanitace + git. Cíl = bezpečné odhlášení bez ztráty kontextu. -->

1. Spustí sanitaci pokud MODEL.md > 100 řádků: `python3 tools/sanitize.py --target all --keep 5`
2. Aktualizuje MEMORY.md
3. Přidá 1 řádek do `MODEL.md` SESSION LOG (tabulkový formát)
4. Commitne + pushne: `git push gitea main && git push github main`
5. Napíše: *"Vše synchronizováno — můžeš se odhlásit."*

**Bez výpisu průběhu** u obou frází — jen závěrečná hláška.

> Platí pro VŠECHNY modely bez výjimky (Opus, Sonnet, Haiku).

## Příkazy workspace

```bash
make docs                # Regeneruje tabulku projektů v tomto souboru
make validate            # Ověří izolaci projektů
make new-project NAME=x  # Nový projekt ze šablony
make list                # Rychlý výpis projektů
```

## Projekty — navigator

> **Workflow**: Tento soubor slouží jako mapa. Před prací na projektu X přečti `X/CLAUDE.md` pro plný kontext.
> `make docs` aktualizuje tabulku níže z `project.yaml` souborů (statické sekce výše jsou zachovány).

<!-- PROJEKTY:START -->
<!-- generováno: 2026-03-07 12:22 -->

| Projekt | Status | Tech | Port | Živý stav | Popis | Detail |
|---------|--------|------|------|-----------|-------|--------|
| 🟢 `agent-ui/` | active | python | 8100 | 🔴 | Webové rozhraní pro orchestrátor (Flask + ... | `agent-ui/CLAUDE.md` |
| 🟢 `ai/` | active | python/toolkit | None | ❓ | Sada nástrojů pro optimalizaci práce s AI ... | `ai/CLAUDE.md` |
| 🟢 `backup-dashboard/` | active | python | 8090 | 🟢 | Webové rozhraní pro správu 3-vrstvového ba... | `backup-dashboard/CLAUDE.md` |
| 🟢 `dashboard/` | active | python | 8099 | 🟢 | Živý přehled stavu všech projektů, služeb ... | `dashboard/CLAUDE.md` |
| 🟢 `docs/` | active | python | 8080 | 🟢 | Dokumentacni portal a build pipeline. Disc... | `docs/CLAUDE.md` |
| 🟢 `fedoraOS/` | active | markdown/docs | 8081 | 🟢 | Referenční dokumentace pro nastavení OS, h... | `fedoraOS/CLAUDE.md` |
| 🟢 `git/` | active | markdown/docs | – | ❓ | Centrální dokumentace git setupu, workflow... | `git/CLAUDE.md` |
| 🟢 `ic-atf/` | active | python/testing-framework | – | ❓ | Automatizovaný testovací framework pro Ins... | `ic-atf/CLAUDE.md` |
| ❓ `nova/` | concept | sql/architecture | – | ❓ | PostgreSQL Holy Trinity architektura (OLTP... | `nova/CLAUDE.md` |
| ❓ `servicenow-ai-platform/` | analytical | markdown/research | – | ❓ | Analyza ServiceNow AI platformy (Now LLM, ... | `servicenow-ai-platform/CLAUDE.md` |
| 🟢 `web-edit/` | active | python | 8765 | 🟢 | Online Markdown editor pro IC dokumentaci ... | `web-edit/CLAUDE.md` |

<!-- PROJEKTY:END -->
