#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="backups"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/barq_tasks_${TIMESTAMP}.dump"

mkdir -p "$BACKUP_DIR"

echo "Creating PostgreSQL backup..."
echo "Output: $BACKUP_FILE"

docker compose exec -T postgres \
  pg_dump \
  -U "${POSTGRES_USER:-barq_app}" \
  -d "${POSTGRES_DB:-barq_tasks}" \
  -Fc \
  > "$BACKUP_FILE"

if [ ! -s "$BACKUP_FILE" ]; then
    echo "FAIL: Backup file is empty."
    rm -f "$BACKUP_FILE"
    exit 1
fi

echo "PASS: PostgreSQL backup created."
ls -lh "$BACKUP_FILE"
