#!/usr/bin/env bash
set -euo pipefail
archive="$(realpath "${1:?Usage: restore-check.sh /path/to/world-archive.tar.gz}")"
test -f "$archive.sha256"
sha256sum --check "$archive.sha256"
# Never restore over the live world. Keep the test directory for inspection.
umask 077
target="$(mktemp -d /var/tmp/pz-restore-check.XXXXXX)"
tar --acls --xattrs --numeric-owner -xzf "$archive" -C "$target"
printf 'Archive extracted for inspection: %s\n' "$target"
echo 'An isolated game boot with this data is still required for a full restore test.'
