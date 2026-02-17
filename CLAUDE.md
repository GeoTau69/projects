# Projektový workspace

> Auto-generováno: 2026-02-17 21:58
> Počet projektů: 1

## Globální konvence

- **Jazyk kódu/komentářů**: čeština
- **Kódování**: UTF-8 (vždy)
- **Izolace**: každý projekt je self-contained, žádné cross-imports
- **Metadata**: každý projekt má `project.yaml` + vlastní `CLAUDE.md`
- **Git**: monorepo, projekty jako adresáře v rootu

## Projekty

### 🟢 Fedora Backup Dashboard (`backup-dashboard/`)

- **Stav**: active
- **Typ**: web-app | **Jazyk**: python
- **Port**: 8090
- **Služba**: `backup-dashboard`
- **Popis**: Webové rozhraní pro správu 3-vrstvového backup systému (Snapper + Btrfs sync + Borg)
- **Tagy**: backup, btrfs, snapper, borg, fastapi
