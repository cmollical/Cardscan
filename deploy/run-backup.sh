#!/bin/sh
set -eu
umask 077
mountpoint -q /srv/tallybinder || { echo "Persistent data volume is not mounted" >&2; exit 1; }
cd /opt/tallybinder
exec 9>/srv/tallybinder/backup.lock
flock -n 9 || exit 0
# Private root-owned file; configures a private encrypted OCI S3-compatible repository.
# The repo must already have been initialized deliberately; no automatic remote creation.
. /srv/tallybinder/config/backup.env
: "${RESTIC_REPOSITORY:?Set private off-VM repository}"
: "${RESTIC_PASSWORD_FILE:?Set a protected restic password file}"
export RESTIC_REPOSITORY RESTIC_PASSWORD_FILE AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_REGION
result=$(docker compose --env-file /srv/tallybinder/config/compose.env -f deploy/compose.yml run --rm --no-deps admin backup --destination /backups)
archive=$(printf '%s' "$result" | python3 -c 'import sys,json; print(json.load(sys.stdin)["path"])')
case "$archive" in /backups/tallybinder-*.tar) ;; *) echo 'Unexpected backup output' >&2; exit 1;; esac
archive_name=${archive##*/}
restic backup "/srv/tallybinder/backups/$archive_name" --tag tallybinder
# No automatic remote pruning. Monitor the 20 GB Always Free quota and explicitly
# approve any retention change; local archives alone are not disaster recovery.

# Keep two complete local archives only AFTER an off-VM snapshot commits successfully.
# Uncompressed tar lets restic deduplicate stable database/photo blocks across days.
python3 - <<'PYROTATE'
from pathlib import Path
archives=sorted(Path('/srv/tallybinder/backups').glob('tallybinder-*.tar'))
for archive in archives[:-2]:
    if archive.is_file() and not archive.is_symlink():archive.unlink()
PYROTATE
