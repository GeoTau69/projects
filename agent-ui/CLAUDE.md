# Agent UI

Webové rozhraní pro orchestrátor (`_meta/`). Flask + HTMX, dark theme, port 8100.

## Přístupy

| Síť | URL |
|-----|-----|
| Lokální | http://localhost:8100 |
| LAN | http://192.168.0.101:8100 |
| Tailscale | http://fedora:8100 |

## Tech stack

- **Backend**: Flask (Python 3.14), port 8100
- **Frontend**: HTMX 2.0.4 (CDN), dark theme monospace
- **Databáze**: SQLite `~/.ai-agent/tokens.db` (sdílená s billing)
- **Orchestrátor**: `_meta/` via `sys.path` (nadřazený adresář)
- **Závislosti**: `flask`, `anthropic` (pip)

## Soubory

```
app.py                              — Flask server, entry point (450+ řádků)
requirements.txt                    — flask, anthropic
templates/
  base.html                         — Layout, HTMX CDN, dark CSS, nav, RAM bar, spinner JS
  index.html                        — Dashboard: backend status + memory + billing dnes
  ask.html                          — Request builder: prompt, konverzace, šablony, operace, model, backend
  stats.html                        — Statistiky: billing historie, denní přehled, cache hit rate
  conversations.html                — Seznam konverzací: nová, uzavřít, přejmenovat, stav souhrnů
  templates_list.html               — Správa šablon: seznam, přidat, smazat
  template_edit.html                — Editace šablony
  partials/
    status.html                     — Backend karty (HTMX polling 10s)
    response.html                   — Odpověď orchestrátoru (backend badge, tokeny, čas)
    memory.html                     — RAM/GPU/Ollama detail panel
    memory_header.html              — Kompaktní RAM bar do hlavičky
    conv_messages.html              — Historie zpráv konverzace
    summaries.html                  — Stav generování souhrnů (polling 5s)
```

## Routes

| Route | Method | Popis |
|-------|--------|-------|
| `/` | GET | Dashboard — backend status + paměť + billing dnes |
| `/status` | GET | HTMX partial: dostupnost backendů (polling 10s) |
| `/memory` | GET | HTMX partial: RAM/GPU/Ollama stats (detail) |
| `/memory/header` | GET | HTMX partial: kompaktní RAM bar do hlavičky (polling 15s) |
| `/stats` | GET | Billing statistiky — posledních 50 requestů + 7 denní přehled |
| `/ask` | GET | Request builder (`?conv=<id>` pro aktivní konverzaci) |
| `/ask` | POST | HTMX partial: orchestrátor → response.html |
| `/templates` | GET | Seznam šablon |
| `/templates/new` | POST | Vytvoření nové šablony |
| `/templates/<id>/edit` | GET/POST | Editace šablony |
| `/templates/<id>/delete` | POST | Smazání šablony |
| `/conversations` | GET | Seznam konverzací |
| `/conversations/new` | POST | Nová konverzace → redirect `/ask?conv=<id>` |
| `/conversations/<id>/messages` | GET | HTMX partial: historie zpráv |
| `/conversations/<id>/close` | POST | Uzavření + spuštění generování souhrnů |
| `/conversations/<id>/summaries` | GET | HTMX partial: stav souhrnů (polling 5s) |
| `/conversations/<id>/rename` | POST | Přejmenování konverzace |

## Funkce

### Request builder (`/ask`)
- Výběr **konverzace** (dropdown) — URL param `?conv=<id>`
- Výběr **šablony** (system prompt uložený v DB)
- Výběr **operace** — každá položka zobrazuje model + cache TTL (např. `code_review (Sonnet, bez cache)`)
- Výběr **modelu** — auto / sonnet / opus / haiku / qwen / deepseek
- Výběr **backendu** — auto (Pro→API→Ollama) / Claude Code / Claude API / Ollama
- **Unanswered prompt** — pokud konverzace má nezodpovězený prompt, načte se automaticky s upozorněním
- Uzavřená konverzace → výběr **souhrnu** (haiku/qwen/deepseek, počet slov/znaků, čas generování)
- Spinner s kontextovým textem (`⟳ Ollama / qwen2.5-coder:14b zpracovává… (30–120s)`)

### Backendy
| Backend | ID | Priorita | Podmínka |
|---------|-----|---------|----------|
| Claude Code (Pro/Max) | `claude-code` | 1. | `claude` CLI dostupný |
| Claude API | `claude` | 2. | `ANTHROPIC_API_KEY` nastaven |
| Ollama | `ollama` | 3. | `localhost:11434` dostupný |

### Konverzace
- **Nová konverzace** → prázdný záznam v DB, redirect na `/ask?conv=<id>`
- **Šablona jako root** — první zpráva s `is_template=1` (bez zobrazení v kontextu pro AI jako běžná zpráva)
- **Message chain** — `parent_id` řetězí user → assistant páry
- **Auto-název** — po první odpovědi Haiku (`claude-haiku-4-5`) navrhne název (max 5 slov, česky)
- **Konec konverzace** — uzavře záznam + spustí 3 background vlákna pro souhrny

### Souhrny konverzací
Po uzavření konverzace se paralelně generují 3 kontextové souhrny (max 200 slov):

| Model | ID | Účel |
|-------|-----|------|
| `qwen2.5-coder:14b` | `qwen` | Lokální, zdarma |
| `deepseek-coder:33b` | `deepseek` | Lokální, alternativa |
| `claude-haiku-4-5` | `haiku` | Placený, nejrychlejší |

Každý souhrn ukládá: `word_count`, `char_count`, `gen_time_ms` — pro porovnání modelů.

### Memory indikátor
- **Hlavička** — kompaktní RAM bar (color-coded: zelená/žlutá/červená), refresh 15s
- **Dashboard** — detail panel: RAM GB, GPU VRAM (nvidia-smi), načtené Ollama modely (`ollama ps`)

### Odpověď
Barevný badge dle backendu:
- 🟢 `Claude Code (Pro)` — zelená
- 🟡 `Claude API (pay-as-you-go)` — žlutá
- 🔵 `Ollama (lokální)` — modrá
- Tokeny (u Claude Code označeny `(odhad)`, u API přesné)
- Čas odpovědi v ms

## Databáze

Sdílená SQLite `~/.ai-agent/tokens.db`. Tabulky:

```sql
templates       — id, name, content, created_at
conversations   — id, name, created_at, closed_at, is_closed
messages        — id, conversation_id, parent_id, role, content,
                  is_template, model, backend, tokens_in, tokens_out,
                  cost_usd, response_time_ms, timestamp
conv_summaries  — id, conversation_id, model, content,
                  word_count, char_count, gen_time_ms, created_at
token_log       — (billing, spravuje _meta/billing.py)
```

## Spuštění

```bash
cd /home/geo/projects/agent-ui
export ANTHROPIC_API_KEY=sk-ant-...   # pro Claude API backend
python app.py
# → http://localhost:8100
```

## Závislosti

- `flask` — pip
- `anthropic` — pip (Claude API backend)
- HTMX 2.0.4 — CDN (bez build stepu)
- `_meta/` moduly: `orchestrator`, `billing`, `router`, `conversations`, `plugins/*`

<!-- SYNC:START -->
<!-- aktualizováno: 2026-03-07 12:22 -->

**Živý stav** *(info-sync.py)*

- Port 8100: 🔴 neodpovídá
- Poslední commit: `ba00557` — fedoraOS docs 10 sekcí + Worker Self-Check Protocol (DELTA MANIFEST)

<!-- SYNC:END -->
