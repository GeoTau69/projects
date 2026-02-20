# AI_WORKFLOW.md — Postup pro generování dokumentace

> Tento soubor čte AI model (primárně Haiku) před tím, než generuje dokumentaci.
> Aktualizuj ho pokud najdeš nový problém nebo vylepšíš postup.
> Poslední update: 2026-02-20 · Sonnet 4.6

---

## Co je tvůj úkol

Generuješ **pouze** `docs/data/{projekt}.json`. Nic jiného.
Python (`build.py`) z toho vyrenderuje HTML — to není tvoje práce.

---

## Postup krok za krokem

**1. Přečti si kontext projektu**
```bash
# Před generováním vždy přečti:
{projekt}/CLAUDE.md        # co projekt dělá, jak je strukturovaný
{projekt}/project.yaml     # metadata (name, status, port, tech)
```

**2. Přečti schéma**
```
docs/schema/doc_schema.json   # povinná pole, typy, co je povoleno
```

**3. Vygeneruj JSON**
Ulož do `docs/data/{projekt}.json`. Struktura viz sekce níže.

**4. Validuj**
```bash
cd ~/projects/docs
python3 build.py --project {projekt} --check
```
Oprav všechny chyby před pokračováním.

**5. Builduj HTML**
```bash
python3 build.py --project {projekt} --force
```
Zkontroluj výstup — musí říct `OK  docs/output/{projekt}.html`.

**6. Ověř v prohlížeči**
```
http://localhost:8080        # sidebar — projekt musí mít ikonu 📖
http://localhost:8080/docs/{projekt}   # samotná stránka
```

---

## Struktura JSON

```json
{
  "project": "nazev-adresare",
  "display_name": "Zobrazovaný název",
  "version": "1.0.0",
  "updated": "2026-02-20",
  "description": "Krátký popis (1-2 věty).",
  "status": "active",
  "port": 8090,
  "tech": ["python", "fastapi"],
  "back_link": {"href": "/", "label": "🏠 Zpět na Dashboard"},
  "access": {
    "local": "http://localhost:8090",
    "lan": "http://192.168.0.101:8090",
    "tailscale": "http://fedora:8090"
  },
  "modules": [...],
  "sections": [...]
}
```

Pole `port`, `tech`, `access`, `back_link`, `modules`, `sections` jsou volitelná.

---

## Moduly (`modules`)

Jeden záznam = jeden soubor nebo logická komponenta.

```json
{
  "id": "helpers",
  "name": "helpers.py",
  "file": "helpers.py",
  "purpose": "Co modul dělá — jedna věta.",
  "status": "stable",
  "public_methods": [
    {
      "name": "run_cmd",
      "params": "cmd: list[str]",
      "returns": "str",
      "description": "Spustí příkaz, vrátí stdout."
    }
  ],
  "dependencies": ["helpers.get_borg_env"],
  "notes": "Důležité poznámky, known issues."
}
```

`status` musí být jedno z: `stable` / `beta` / `wip` / `deprecated`

---

## Sekce (`sections`) a bloky (`blocks`)

Každá sekce má `id`, `title`, volitelně `icon`, a seznam `blocks`.

### Typy bloků

| type | Povinná pole | Poznámka |
|------|-------------|----------|
| `text` | `text` | Odstavec, může obsahovat inline HTML |
| `heading` | `text` | Podnadpis h3 |
| `code` | `text`, `lang` | Kódový blok, lang = bash/python/sql/... |
| `list` | `entries` | `ordered: true` pro číslovaný seznam |
| `table` | `headers`, `rows` | `rows` je pole polí stringů |
| `card` | `variant`, `title` | Varianty: info/warning/danger/success |

### Příklady

```json
{"type": "text", "text": "Popis funkce s <code>inline kódem</code>."}

{"type": "code", "lang": "bash", "text": "agent billing --today"}

{"type": "list", "entries": ["první položka", "druhá položka"]}

{"type": "list", "ordered": true, "entries": ["Krok 1", "Krok 2"]}

{"type": "table",
 "headers": ["Název", "Popis"],
 "rows": [["<code>foo</code>", "Dělá foo"], ["<code>bar</code>", "Dělá bar"]]}

{"type": "card", "variant": "warning", "title": "⚠️ Pozor",
 "text": "Popis.", "entries": ["bod 1", "bod 2"], "code": "příkaz"}
```

---

## ⚠️ Časté chyby (trap list)

### 1. `items` místo `entries` — NEJČASTĚJŠÍ CHYBA
```json
// ✗ ŠPATNĚ — způsobí chybu v Jinja2
{"type": "list", "items": ["a", "b"]}

// ✓ SPRÁVNĚ
{"type": "list", "entries": ["a", "b"]}
```
`items` je rezervované jméno Pythonu. Jinja2 ho zachytí jako `dict.items()` metodu.
Platí i pro `card` s položkami — vždy `entries`.

### 2. Unicode uvozovky v JSON
```json
// ✗ ŠPATNĚ — způsobí JSON parse error
"text": "Ollama má v „paměti" data"

// ✓ SPRÁVNĚ
"text": "Ollama má v 'paměti' data"
```
Používej pouze standardní uvozovky `"` a `'`.

### 3. Chybějící povinná pole
Povinná jsou pouze: `project` a `updated`.
Ale `build.py --check` ti řekne co konkrétně chybí.

### 4. Neplatný `status`
```json
// ✗ ŠPATNĚ
"status": "done"

// ✓ SPRÁVNĚ — jen tyto hodnoty
"status": "active"       // pro projekt
"status": "stable"       // pro modul
```
Projekt: `active` / `wip` / `planned` / `archived`
Modul: `stable` / `beta` / `wip` / `deprecated`

### 5. Escapování v `code` blocích
V `code` blocích se HTML escapuje automaticky — piš čistý kód, ne HTML entity.
```json
// ✓ SPRÁVNĚ — piš < a >, ne &lt; a &gt;
{"type": "code", "text": "if a < b: return True"}
```

---

## Checklist před odevzdáním

- [ ] JSON validuje bez chyb: `python3 build.py --project X --check`
- [ ] Build proběhl: `python3 build.py --project X --force` → `OK`
- [ ] Soubor existuje: `ls docs/output/X.html`
- [ ] Žádné `"items"` klíče — pouze `"entries"`
- [ ] Žádné Unicode uvozovky `„"` v JSON stringách
- [ ] Všechna `status` pole mají platné hodnoty

---

## Minimální funkční příklad

Pokud si nejsi jistý, začni tímto a postupně rozšiřuj:

```json
{
  "project": "muj-projekt",
  "display_name": "Můj Projekt",
  "updated": "2026-02-20",
  "description": "Co projekt dělá.",
  "status": "active",
  "sections": [
    {
      "id": "prehled",
      "title": "Přehled",
      "icon": "📋",
      "blocks": [
        {"type": "text", "text": "Popis projektu."}
      ]
    }
  ]
}
```

Validuj, builduj, pak teprve rozšiřuj o další sekce a moduly.
