#!/bin/sh
set -eu
mountpoint -q /srv/tallybinder || { echo "Persistent data volume is not mounted" >&2; exit 1; }
cd /opt/tallybinder
# Host lock supplements the database's persisted provider cooldowns and sync lock.
exec 9>/srv/tallybinder/daily.lock
flock -n 9 || exit 0
docker compose --env-file /srv/tallybinder/config/compose.env -f deploy/compose.yml run --rm --no-deps admin daily --config /data/daily-sets.json --execute
