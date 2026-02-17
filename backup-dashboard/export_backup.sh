#!/bin/bash
# export_backup.sh
# Zazipuje soubory projektu Backup Dashboard do ~/Downloads
# Název: Backup-project-info_YYYYMMDD_HHMMSS.zip

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
ARCHIVE_NAME="Backup-project-info_${TIMESTAMP}"
DEST_DIR="/home/geo/Downloads"
TMP_DIR="/tmp/${ARCHIVE_NAME}"
PROJECT_DIR="/opt/backup-dashboard"

mkdir -p "${TMP_DIR}" "${DEST_DIR}"

echo "=== Export projektu: ${ARCHIVE_NAME} ==="

copy_file() {
    local src="$1"
    local dst_sub="$2"
    mkdir -p "${TMP_DIR}/${dst_sub}"
    if [ -f "${src}" ]; then
        cp "${src}" "${TMP_DIR}/${dst_sub}/"
        echo "  ✓ ${src}"
    else
        echo "  - ${src} (nenalezen, přeskočen)"
    fi
}

# Hlavní soubory projektu
copy_file "${PROJECT_DIR}/app.py"                          ""
copy_file "${PROJECT_DIR}/templates/dashboard.html"        "templates"
copy_file "${PROJECT_DIR}/templates/docs.html"             "templates"
copy_file "${PROJECT_DIR}/export_backup.sh"                ""
copy_file "${PROJECT_DIR}/requirements.txt"                ""
copy_file "${PROJECT_DIR}/README.md"                       ""

# Systémové soubory (pokud existují)
for f in /etc/systemd/system/backup-dashboard.service \
          /etc/systemd/system/borg-backup.service \
          /etc/systemd/system/borg-backup.timer \
          /etc/systemd/system/snapshot-sync.service \
          /etc/systemd/system/snapshot-sync.timer \
          /usr/local/bin/backup-snapshot-sync.sh; do
    [ -f "$f" ] && copy_file "$f" "system"
done

# Vytvořit ZIP
echo ""
echo "Vytvářím archiv..."
cd /tmp
zip -r "${DEST_DIR}/${ARCHIVE_NAME}.zip" "${ARCHIVE_NAME}/" \
    -x "*.pyc" -x "__pycache__/*" -x "*.log" -x ".git/*"

RC=$?
rm -rf "${TMP_DIR}"

if [ $RC -eq 0 ]; then
    SIZE=$(du -sh "${DEST_DIR}/${ARCHIVE_NAME}.zip" | cut -f1)
    echo "✓ Archiv: ${DEST_DIR}/${ARCHIVE_NAME}.zip (${SIZE})"
    echo "ZIPPATH:${DEST_DIR}/${ARCHIVE_NAME}.zip"
    exit 0
else
    echo "✗ Vytvoření archivu selhalo (rc=${RC})"
    exit 1
fi
