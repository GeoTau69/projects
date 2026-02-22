# Archive: TODO DONE
# Generováno: 2026-02-22


<!-- Archivováno: 2026-02-22 -->

### [2] TOKENOVÉ ÚČETNICTVÍ
**Priorita: VYSOKÁ**
**Status: HOTOVO**

**Co implementovat:**

Soubor `_meta/token_tracker.py` — transparentní wrapper kolem Anthropic API volání.

**SQLite schéma** (`~/.ai-agent/tokens.db`):
```sql
CREATE TABLE token_log (
    id          INTEGER PRIMARY KEY,
    timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP,
    project     VARCHAR(50),
    operation   VARCHAR(50),
    model       VARCHAR(30),
    tokens_in   INTEGER,
    tokens_out  INTEGER,
    cost_usd    DECIMAL(10,6),
    prompt_hash VARCHAR(64)
);
```

**Ceny — ověřit aktuální na anthropic.com před implementací:**
- `claude-sonnet-4-6`: input $3/M, output $15/M tokenů
- `claude-opus-4-6`: input $15/M, output $75/M tokenů

**CLI příkazy:**
```bash
agent billing --week
agent billing --project backup-dashboard
agent billing --model sonnet
agent billing --top-operations
```

**Kroky:**
- [x] Vytvořit `~/.ai-agent/` adresář + inicializovat SQLite
- [x] Napsat `_meta/token_tracker.py` (wrapper + CLI)
- [x] Ověřit aktuální ceny modelů (sonnet $3/$15, opus $15/$75, haiku $0.8/$4 za 1M tokenů)
- [x] `~/bin/agent` wrapper (PATH přes ~/.bashrc, funguje ihned)
- [ ] Integrovat do skriptů volajících Anthropic API (až budou existovat)

### [3] PROMPT CACHE / DEDUPLICATION
**Priorita: STŘEDNÍ**
**Status: HOTOVO**

Na základě `prompt_hash` z SQLite:
- Stejný hash v posledních N hodinách → vrátit cached odpověď
- TTL per typ operace: `doc_update` 24h, `boilerplate` 48h, `code_review` 0 (bez cache)
- Cache uložena jako rozšíření `token_log` tabulky (sloupce `response_text`, `cache_hit`)

**Kroky:**
- [x] Rozšířit `token_tracker.py` o cache lookup/store + DB migrace
- [x] Definovat TTL pravidla (`CACHE_TTL` dict v kódu)
- [x] `call_api()` — Python wrapper pro skripty (cache + log v jednom)
- [x] `agent cache --stats / --list / --clear [--all]`
- [x] `billing` zobrazuje cache hity + ušetřenou částku
- [ ] Otestovat na reálném API volání (až budou skripty)

### [4] VEKTOROVÁ DB — VLASTNÍ (SQLite + numpy)
**Priorita: STŘEDNÍ**
**Status: HOTOVO**

**Poznámka:** chromadb nekompatibilní s Python 3.14 (pydantic v1 crash) → vlastní implementace.

**Stack:** SQLite `~/.ai-agent/code_index.db` + numpy BLOB embeddingy + nomic-embed-text přes Ollama
**Chunking:** Python → per funkce/třídy; Markdown → per sekce; ostatní → sliding window 60 řádků
**Re-indexace:** mtime-based (skip beze-změny), `--diff` pro git-changed only

```bash
agent index                       # celý workspace
agent index --project dashboard   # jen projekt
agent index --diff                # jen git-změněné soubory
agent index --force               # přeindexuj vše
agent search "retry logika"
agent search "záloha borg" --project backup-dashboard --top 10
agent search "co projekt dělá" --scope docs
```

**Kroky:**
- [x] `nomic-embed-text` stažen do Ollama
- [x] `_meta/chroma_indexer.py` — indexer + search (SQLite+numpy, bez chromadb)
- [x] `~/bin/agent` router aktualizován (index/search → chroma_indexer.py)
- [x] Otestováno: 87 chunků z 18 souborů, cross-project search funkční
- [ ] Napojit na git post-commit hook (volitelně)

### [5] MODEL ROUTING
**Priorita: NÍZKÁ**
**Status: HOTOVO**

**Poznámka:** LiteLLM přeskočen (pravděpodobný pydantic problém jako chromadb) → přímé HTTP Ollama API.

Automatické přepínání: `call_api(..., model='auto')` → `ROUTING_RULES[operation]` → Ollama nebo Anthropic.

```python
ROUTING_RULES = {
    'doc_update':    'local',    # Ollama qwen2.5-coder:14b
    'boilerplate':   'local',    # Ollama
    'info_sync':     'local',    # Ollama
    'code_review':   'sonnet',   # Claude Sonnet
    'architecture':  'opus',     # Claude Opus
    'debug_complex': 'sonnet',   # Claude Sonnet
    '_default':      'sonnet',
}
```

**Kroky:**
- [x] `resolve_model(operation, model)` — resolves 'auto'/'local'/alias na cílový model
- [x] `call_api_ollama()` — Ollama `/api/chat` HTTP, vrací tokeny + text
- [x] `call_api()` rozšířen o routing větev (ollama/ prefix → lokální, jinak Anthropic)
- [x] `agent route --show / --test <operation>` CLI
- [x] `billing` zobrazuje Ollama volání s $0.00 odděleně
- [x] Oprava billing JOIN bug → subquery přístup
- [ ] Reálné ověření úspor na skutečných API skriptech (až budou)

