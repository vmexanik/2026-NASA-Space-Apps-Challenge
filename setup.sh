#!/usr/bin/env bash
# One command from a fresh clone to a running app with data:
#
#   ./setup.sh                      # the Ukraine test package (parser/testdata/test-ukraine)
#   ./setup.sh path/to/package      # another FIRMS dump package (a folder with manifest.json and restore.sh)
#   ./setup.sh --no-data            # app only, keep whatever is in the database
#
# Safe to run again: it skips what is already done, and restores the data package only when
# the database holds a different one (compares name and built_at with manifest.json).
set -euo pipefail

cd "$(dirname "$0")"

PACKAGE=parser/testdata/test-ukraine
LOAD_DATA=1
case "${1:-}" in
    --no-data) LOAD_DATA=0 ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    "") ;;
    *) PACKAGE="${1%/}" ;;
esac

step() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
php() { docker compose exec -T php "$@"; }
psql_db() { docker compose exec -T db psql -U we_charge -d we_charge -v ON_ERROR_STOP=1 "$@"; }

command -v docker >/dev/null || { echo "docker not found: install and start Docker Desktop first." >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker is not running: start Docker Desktop first." >&2; exit 1; }
if [ "$LOAD_DATA" = 1 ] && [ ! -f "$PACKAGE/manifest.json" ]; then
    echo "No data package at $PACKAGE (expected $PACKAGE/manifest.json)." >&2
    exit 1
fi

step "1/6 Containers"
docker compose up -d --build --wait db php nginx

step "2/6 Laravel: .env, packages, key"
[ -f web/.env ] || cp web/.env.example web/.env
php composer install --no-interaction --prefer-dist --no-progress
grep -q '^APP_KEY=base64:' web/.env || php php artisan key:generate --force

step "3/6 Database: migrations and seed (admin, FIRMS products)"
php php artisan migrate --seed --force

step "4/6 Frontend build"
docker compose run --rm --no-deps node sh -c "npm ci --no-audit --no-fund && npm run build"

step "5/6 FIRMS data"
if [ "$LOAD_DATA" = 1 ]; then
    field() { grep -o "\"$1\": *\"[^\"]*\"" "$PACKAGE/manifest.json" | head -1 | cut -d'"' -f4; }
    want="$(field name) $(field built_at)"
    have=$(psql_db -tAc "select name || ' ' || to_char(built_at at time zone 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') from firms.dataset limit 1" 2>/dev/null || true)
    if [ "$want" = "$have" ]; then
        echo "The database already holds $want, skipping the restore."
    else
        echo "Restoring $PACKAGE ($want), about a minute for the Ukraine package..."
        docker compose exec -T db rm -rf /tmp/firms-dump
        docker compose cp "$PACKAGE/." db:/tmp/firms-dump
        docker compose exec -T db bash -c 'cd /tmp/firms-dump && PGUSER=we_charge PGDATABASE=we_charge ./restore.sh --jobs 4'
        docker compose exec -T db rm -rf /tmp/firms-dump
    fi
else
    echo "Skipped (--no-data)."
fi

step "6/6 Caches"
php php artisan optimize:clear

cat <<EOF

Done.
  App:    http://localhost   (or http://we-charge.test after adding it to /etc/hosts, see README)
  Admin:  http://localhost/admin   admin@we-charge.test / admin  (change the password after the first login)
EOF
