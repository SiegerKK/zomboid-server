#!/usr/bin/env bash
# Offline smoke test: a fake Docker CLI verifies slot isolation and rollback.
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TEST="$(mktemp -d)"
trap 'rm -rf -- "$TEST"' EXIT
mkdir -p "$TEST/repo/config" "$TEST/bin" "$TEST/store/data/Server" "$TEST/state"
cp "$ROOT/pz" "$TEST/repo/pz"
: > "$TEST/repo/compose.yaml"
printf 'PAUSE_EMPTY=true\n' > "$TEST/repo/config/server.env"
for item in vanilla tlou mp-test; do
  case "$item" in vanilla) name=mods.vanilla.env;; tlou) name=mods.env;; mp-test) name=mods.mp-test.env;; esac
  : > "$TEST/repo/config/$name"
done
printf 'DUMMY=1\n' > "$TEST/repo/.env"
printf 'Original legacy world content\n' > "$TEST/store/data/Server/SiegerZomboid.ini"
echo false > "$TEST/state/running"
echo 0 > "$TEST/state/exit_code"
: > "$TEST/state/mount"
cat > "$TEST/bin/docker" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
: "${MOCK_DOCKER_STATE:?}"
case "${1:-}" in
  inspect)
    if [[ ! -e "$MOCK_DOCKER_STATE/exists" ]]; then exit 1; fi
    if [[ "$2" == -f ]]; then
      case "$3" in
        '{{.State.Running}}') cat "$MOCK_DOCKER_STATE/running" ;;
        '{{.State.ExitCode}}') cat "$MOCK_DOCKER_STATE/exit_code" ;;
        *) cat "$MOCK_DOCKER_STATE/mount" ;;
      esac
    fi ;;
  compose)
    for x in "$@"; do
      case "$x" in
        config) exit 0 ;;
        up)
          touch "$MOCK_DOCKER_STATE/exists"
          printf '%s\n' "${PZ_WORLD_DATA_DIR:?}" > "$MOCK_DOCKER_STATE/mount"
          echo true > "$MOCK_DOCKER_STATE/running"
          echo 0 > "$MOCK_DOCKER_STATE/exit_code"
          exit 0
          ;;
        stop)
          echo false > "$MOCK_DOCKER_STATE/running"
          echo 0 > "$MOCK_DOCKER_STATE/exit_code"
          exit 0
          ;;
        logs) exit 0 ;;
      esac
    done ;;
  exec)
    echo 'RCON command accepted' ;;
  *) echo "unexpected mock docker: $*" >&2; exit 1 ;;
esac
MOCK
chmod +x "$TEST/bin/docker"
export PZ_MANAGER_REPO_ROOT="$TEST/repo"
export PZ_MANAGER_STORE_ROOT="$TEST/store"
export PZ_MANAGER_LOCK_FILE="$TEST/manager.lock"
export MOCK_DOCKER_STATE="$TEST/state"
export PATH="$TEST/bin:$PATH"
run() { bash "$ROOT/pz" "$@"; }

# Legacy world must not be forgotten.
if run create newworld && run start newworld; then echo 'ERROR: unexpectedly started before importing legacy data' >&2; exit 1; fi
run import-legacy original
[[ -s "$TEST/store/data/Server/SiegerZomboid.ini" ]]
[[ -s "$TEST/store/worlds/original/data/Server/SiegerZomboid.ini" ]]
run start original
[[ "$(cat "$TEST/state/mount")" == "$TEST/store/worlds/original/data" ]]
run save-live
run save --yes
[[ "$(cat "$TEST/state/running")" == true ]]
[[ "$(find "$TEST/store/backups/worlds/original" -name 'world-*.tar.gz' | wc -l)" == 2 ]]
run stop --yes
[[ "$(cat "$TEST/state/running")" == false ]]
run create bleak tlou
run start bleak
[[ "$(cat "$TEST/state/mount")" == "$TEST/store/worlds/bleak/data" ]]
run stop --yes
archive="$(find "$TEST/store/backups/worlds/original" -name 'world-*.tar.gz' | head -n 1)"
run load "$archive" restored
[[ "$(cat "$TEST/store/worlds/restored/data/Server/SiegerZomboid.ini")" == 'Original legacy world content' ]]
[[ "$(cat "$TEST/store/worlds/restored/profile")" == vanilla ]]
run start restored
[[ "$(cat "$TEST/state/mount")" == "$TEST/store/worlds/restored/data" ]]
run status
run list
run stop --yes
# Restore must never overwrite an existing slot.
if run load "$archive" original; then echo 'ERROR: restore overwrote original' >&2; exit 1; fi
[[ -s "$TEST/store/data/Server/SiegerZomboid.ini" ]]
echo 'PASS: manager offline smoke test'