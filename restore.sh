#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "Usage: ./restore.sh <backup-file>"
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "FAIL: Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "Restoring PostgreSQL backup..."
echo "Input: $BACKUP_FILE"

docker compose exec -T postgres \
  pg_restore \
  -U "${POSTGRES_USER:-barq_app}" \
  -d "${POSTGRES_DB:-barq_tasks}" \
  --clean \
  --if-exists \
  --no-owner \
  --exit-on-error \
  < "$BACKUP_FILE"

echo "PASS: PostgreSQL restore completed."
