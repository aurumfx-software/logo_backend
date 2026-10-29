#!/usr/bin/env bash
# Safe pull on deploy hosts: drop untracked copies that block merges, then update dev.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BRANCH="${1:-dev}"

BLOCKERS=(
  app/api/v1/endpoints/complaint.py
  app/db/models/complaint.py
  app/schemas/complaint.py
  app/services/complaint_service.py
  alembic/versions/014_complaints_table.py
)

for path in "${BLOCKERS[@]}"; do
  if [[ -e "$path" ]] && ! git ls-files --error-unmatch "$path" &>/dev/null; then
    echo "Removing untracked file that blocks merge: $path"
    rm -rf "$path"
  fi
done

git merge --abort 2>/dev/null || true
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git merge --ff-only "origin/$BRANCH"

echo "Running migrations..."
alembic upgrade head

echo "Updated to $(git rev-parse --short HEAD). Restart the API process (docker/systemd)."
