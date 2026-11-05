#!/usr/bin/env bash
# Safe pull on deploy hosts: drop untracked copies that block merges, then update dev.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BRANCH="${1:-dev}"

git merge --abort 2>/dev/null || true
git fetch origin "$BRANCH"

# Untracked files that also exist on the incoming branch make git pull abort.
while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  if [[ -e "$path" ]] && ! git ls-files --error-unmatch "$path" &>/dev/null; then
    echo "Removing untracked file that blocks merge: $path"
    rm -rf "$path"
  fi
done < <(
  comm -12 \
    <(git ls-files --others --exclude-standard | sort) \
    <(git ls-tree -r --name-only "origin/$BRANCH" | sort)
)

git checkout "$BRANCH"
git merge --ff-only "origin/$BRANCH"

echo "Running migrations..."
alembic upgrade head

echo "Updated to $(git rev-parse --short HEAD). Restart the API process (docker/systemd)."
echo "Ensure .env sets SERVER_PUBLIC_IP or CORS_ORIGINS for your frontend URL (fixes OPTIONS 400 on /auth/login)."
