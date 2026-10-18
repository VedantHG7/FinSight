#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ ! -f deploy/.env ]; then
    echo 'First run: python3 deploy/configure.py YOUR_HOSTNAME' >&2
    exit 1
fi
dc() { docker compose --env-file deploy/.env -f compose.yaml "$@"; }
dc config --quiet
dc build
# Fail before starting public services if native libraries/models do not work.
dc run --rm --no-deps api python -m app.check_runtime
dc run --rm --no-deps web caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
dc up -d --wait --wait-timeout 240
dc ps
echo 'Services started. Verify HTTPS login, a workbook analysis and PDF download.'
echo 'Worker logs: docker compose --env-file deploy/.env logs --tail=100 worker'
