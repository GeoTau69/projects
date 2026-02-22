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
| **Opus 4.6** | Architekt | Návrh architektury, audit, složité problémy, specifikace | Nové systémy, architektonická rozhodnutí, review |
| **Sonnet 4.6** | SW inženýr | Implementace dle specifikace, vývoj, refactoring, kód + **vlastník všech `CLAUDE.md`** | Psaní kódu, úpravy souborů, aktualizace kontextu projektu |
| **Haiku 4.5** | Dokumentarista | **Pouze** generování `docs/data/{projekt}.json` z CLAUDE.md → HTML | `docs/data/{projekt}.json` pipeline — čte, negeneruje CLAUDE.md |

Workflow:
1. **Opus** navrhne architekturu → zapíše specifikaci do MEMORY.md / MODEL.md
2. **Sonnet** implementuje dle specifikace + **aktualizuje `{projekt}/CLAUDE.md`**
3. **Haiku** čte CLAUDE.md → generuje `docs/data/{projekt}.json` → `build.py` renderuje HTML
4. Dokumentace se automaticky zobrazí v portálu s 📖 ikonou

**Pravidlo vlastnictví CLAUDE.md:**
- `{projekt}/CLAUDE.md` = **výhradně Sonnet** — píše, aktualizuje, refaktoruje
- Haiku smí číst CLAUDE.md pro JSON generování, ale **NESMÍ ho modifikovat**
- Výjimka: MEMORY.md soubory při `štafeta`/`konec zvonec` — všechny modely

Cenový princip: Opus ($75/M out) jen na architektonické rozhodování. Sonnet ($15/M out) na implementaci + CLAUDE.md. Haiku ($4/M out) na JSON/HTML pipeline.

## Kontextové soubory

| Soubor | Načítání | Účel |
|--------|----------|------|
| `MODEL.md` | Manuálně | Session log (posledních 5 záznamů) + aktuální stav |
| `todo.md` | Manuálně | Centrální backlog |
| `docs/INFO.md` | Manuálně | Portál průvodce — viz **ℹ️ Info** (http://localhost:8080) |
| `memory/MEMORY.md` | **Auto** | Volatile session state — aktuální úkol, next steps |

**Auto-memory cesty** (závisí na CWD při startu Claude):
- Start z `/home/geo/projects/` → `~/.claude/projects/-home-geo-projects/memory/MEMORY.md`
- Start z `/home/geo/` → `~/.claude/projects/-home-geo/memory/MEMORY.md`
- **Oba soubory synchronizovat** při `konec zvonec`

## Zlaté pravidlo — Session persistence

<!-- DOKUMENTACE: Dvě signální fráze řídí ukládání kontextu mezi sessions/modely.
     "štafeta" = lehký handoff (v rámci session, bez git). Typicky před /model switch.
     "konec zvonec" = plný checkpoint (git commit+push). Před odhlášením.
     Obě fráze jsou case-insensitive. Platí pro všechny modely bez výjimky. -->

### Signální fráze

| Fráze | Kdy | Co model udělá |
|-------|-----|-----------------|
| **`štafeta`** | Předání jinému modelu (před `/model`) | Aktualizuje oba MEMORY.md se shrnutím + specifikací pro dalšího. Bez git, bez sanitace. Napíše: *"Štafeta předána — přepni model."* |
| **`konec zvonec`** | Konec práce, odhlášení | Sanitace + oba MEMORY.md + MODEL.md session log + git commit + push. Napíše: *"Vše synchronizováno — můžeš se odhlásit."* |

### `štafeta` — postup

<!-- Lehký handoff: žádný git, žádná sanitace. Cíl = předat kontext dalšímu modelu. -->

1. Aktualizuje **oba** MEMORY.md (cesty viz tabulka v Kontextové soubory)
   - Co jsem udělal (3-5 bodů)
   - Co má příští model udělat (konkrétní specifikace)
   - Rozpracované soubory (cesty)
2. Napíše: *"Štafeta předána — přepni model."*

### `konec zvonec` — postup

<!-- Plný checkpoint: sanitace + git. Cíl = bezpečné odhlášení bez ztráty kontextu. -->

1. Spustí sanitaci pokud MODEL.md > 100 řádků: `python3 tools/sanitize.py --target all --keep 5`
2. Aktualizuje **oba** MEMORY.md
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
<!-- generováno: 2026-02-19 21:40 -->

| Projekt | Status | Tech | Port | Popis | Detail |
|---------|--------|------|------|-------|--------|
| 🟢 `ai/` | active | ? | None | Sada nástrojů pro optimalizaci práce s AI v rámci wo... | `ai/CLAUDE.md` |
| 🟢 `backup-dashboard/` | active | python | 8090 | Webové rozhraní pro správu 3-vrstvového backup systé... | `backup-dashboard/CLAUDE.md` |
| 🟢 `dashboard/` | active | python | 8099 | Živý přehled stavu všech projektů, služeb a systémov... | `dashboard/CLAUDE.md` |
| 🟢 `git/` | active | markdown/docs | – | Centrální dokumentace git setupu, workflow a integra... | `git/CLAUDE.md` |
| 🟢 `web-edit/` | active | python | 8765 | Online Markdown editor pro IC dokumentaci s real-tim... | `web-edit/CLAUDE.md` |

<!-- PROJEKTY:END -->
