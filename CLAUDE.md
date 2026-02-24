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
| backup-dashboard | :8090 | 192.168.0.101:8090 | fedora:8090 |
| dashboard | :8099 | 192.168.0.101:8099 | fedora:8099 |
| docs | :8080 | 192.168.0.101:8080 | fedora:8080 |
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
      → Opus: review → OK nebo REWORK
```

**Pravidla pro workery (Sonnet, Haiku):**
1. **Nereinterpretuj** Opus specifikaci — implementuj přesně jak je zadáno
2. **Neměň design** — pokud nesouhlasíš, zapiš `ESCALATION: důvod` do MEMORY.md a ČEKEJ
3. **Hlásit dokončení** — po implementaci zapiš do MEMORY.md co jsi udělal
4. **Neinformuj jiný worker po svém** — Haiku dostává instrukce od Opuse, ne od Sonnetu

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
<!-- generováno: 2026-02-24 04:04 -->

| Projekt | Status | Tech | Port | Popis | Detail |
|---------|--------|------|------|-------|--------|
| 🟢 `agent-ui/` | active | ? | 8100 | Webové rozhraní pro orchestrátor (Flask + HTMX). Das... | `agent-ui/CLAUDE.md` |
| 🟢 `ai/` | active | ? | None | Sada nástrojů pro optimalizaci práce s AI v rámci wo... | `ai/CLAUDE.md` |
| 🟢 `backup-dashboard/` | active | python | 8090 | Webové rozhraní pro správu 3-vrstvového backup systé... | `backup-dashboard/CLAUDE.md` |
| 🟢 `dashboard/` | active | python | 8099 | Živý přehled stavu všech projektů, služeb a systémov... | `dashboard/CLAUDE.md` |
| 🟢 `fedoraOS/` | active | markdown/docs/docs | 8081 | Referenční dokumentace pro nastavení OS, hardware, v... | `fedoraOS/CLAUDE.md` |
| 🟢 `git/` | active | markdown/docs | – | Centrální dokumentace git setupu, workflow a integra... | `git/CLAUDE.md` |
| 🟢 `ic-atf/` | active | python/testing-framework | – | Automatizovaný testovací framework pro Instance Cont... | `ic-atf/CLAUDE.md` |
| 🟢 `web-edit/` | active | python | 8765 | Online Markdown editor pro IC dokumentaci s real-tim... | `web-edit/CLAUDE.md` |

<!-- PROJEKTY:END -->
