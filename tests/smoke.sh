#!/usr/bin/env bash
# Offline smoke test: a fake Docker CLI verifies slot isolation and rollback.
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TEST="$(mktemp -d)"
trap 'rm -rf -- "$TEST"' EXIT
mkdir -p "$TEST/repo/config" "$TEST/repo/config/server-rules" "$TEST/repo/config/presets" "$TEST/bin" "$TEST/store/data/Server" "$TEST/state"
mkdir -p "$TEST/store/mod-snapshot/content/108600" "$TEST/store/agent"
: > "$TEST/store/agent/ZombieBuddy.jar"
: > "$TEST/repo/compose.mods.yaml"
cp "$ROOT/pz" "$TEST/repo/pz"
: > "$TEST/repo/compose.yaml"
printf 'PAUSE_EMPTY=true\n' > "$TEST/repo/config/server.env"
printf 'PAUSE_EMPTY=true\nPVP=false\nMAX_PLAYERS=6\n' > "$TEST/repo/config/server-rules/default.env"
printf 'PAUSE_EMPTY=true\nPVP=false\nMAX_PLAYERS=3\n' > "$TEST/repo/config/server-rules/tlou-coop.env"
printf 'SandboxVars = { VERSION = 6, }\n' > "$TEST/repo/config/presets/TLOU_Year20.lua"
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
          if [[ "$PZ_MODS_FILE" == */mods.env ]]; then
            [[ "$*" == *compose.mods.yaml* && -n "${PZ_WORKSHOP_SNAPSHOT:-}" ]] || exit 11
          else
            [[ "$*" != *compose.mods.yaml* ]] || exit 12
          fi
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
  update) exit 0 ;;
  exec)
    cmd="${!#}"
    printf '%s\n' "$cmd" >> "$MOCK_DOCKER_STATE/rcon-calls"
    case "$cmd" in
      save) [[ ! -e "$MOCK_DOCKER_STATE/fail-save" ]] || exit 1; echo 'World saved' ;;
      quit) echo false > "$MOCK_DOCKER_STATE/running"; echo 'Quit' ;;
      players) echo 'Players connected (0):' ;;
      setaccesslevel*) echo 'Access Level granted' ;;
      *) exit 1 ;;
    esac ;;
  *) echo "unexpected mock docker: $*" >&2; exit 1 ;;
esac
MOCK
chmod +x "$TEST/bin/docker"
cat > "$TEST/bin/tar" <<'MOCK'
#!/usr/bin/env bash
[[ ! -e "$MOCK_DOCKER_STATE/fail-tar" ]] || exit 77
exec /usr/bin/tar "$@"
MOCK
chmod +x "$TEST/bin/tar"
export PZ_MANAGER_REPO_ROOT="$TEST/repo"
export PZ_MANAGER_STORE_ROOT="$TEST/store"
export PZ_MANAGER_LOCK_FILE="$TEST/manager.lock"
export MOCK_DOCKER_STATE="$TEST/state"
export PATH="$TEST/bin:$PATH"
run() { bash "$ROOT/pz" "$@"; }

# Legacy world must not be forgotten.
if run create newworld && run start newworld; then echo 'ERROR: unexpectedly started before importing legacy data' >&2; exit 1; fi
touch "$TEST/state/fail-tar"
if run import-legacy partial vanilla; then echo 'ERROR: import reported success after backup failure' >&2; exit 1; fi
[[ ! -e "$TEST/store/manager/legacy-imported" ]]
rm "$TEST/state/fail-tar"
run import-legacy original vanilla
[[ -s "$TEST/store/data/Server/SiegerZomboid.ini" ]]
[[ -s "$TEST/store/worlds/original/data/Server/SiegerZomboid.ini" ]]
run start original
[[ "$(cat "$TEST/state/mount")" == "$TEST/store/worlds/original/data" ]]
run save-live
touch "$TEST/state/fail-save"
if run stop --yes; then echo 'ERROR: stopped after save failure' >&2; exit 1; fi
[[ "$(cat "$TEST/state/running")" == true ]]
rm "$TEST/state/fail-save"
run save --yes
[[ "$(cat "$TEST/state/running")" == true ]]
[[ "$(find "$TEST/store/backups/worlds/original" -name 'world-*.tar.gz' | wc -l)" == 2 ]]
run stop --yes
[[ "$(cat "$TEST/state/running")" == false ]]
# Never silently reinterpret the profile of an existing modded legacy world.
printf 'Mods=UnexpectedMod\nWorkshopItems=999\n' >> "$TEST/store/data/Server/SiegerZomboid.ini"
if run import-legacy mismatched vanilla; then echo 'ERROR: imported mismatched profile' >&2; exit 1; fi
run create bleak tlou
run start bleak
[[ "$(cat "$TEST/state/mount")" == "$TEST/store/worlds/bleak/data" ]]
[[ "$(cat "$TEST/store/worlds/bleak/preset")" == auto ]]
grep -q '^MAX_PLAYERS=6$' "$TEST/store/worlds/bleak/server-rules.env"
run admin grant kyrylo
run admin revoke kyrylo
run stop --yes
run create cinematic tlou TLOU_Year20 tlou-coop
[[ "$(cat "$TEST/store/worlds/cinematic/preset")" == TLOU_Year20 ]]
cmp "$TEST/repo/config/presets/TLOU_Year20.lua" "$TEST/store/worlds/cinematic/data/Server/SiegerZomboid_SandboxVars.lua"
grep -q '^MAX_PLAYERS=3$' "$TEST/store/worlds/cinematic/server-rules.env"
run start cinematic
[[ "$(cat "$TEST/state/mount")" == "$TEST/store/worlds/cinematic/data" ]]
run save --yes
run stop --yes
custom_archive="$(find "$TEST/store/backups/worlds/cinematic" -name 'world-*.tar.gz' | head -n 1)"
run load "$custom_archive" cinematic_restored
[[ "$(cat "$TEST/store/worlds/cinematic_restored/preset")" == TLOU_Year20 ]]
cmp "$TEST/store/worlds/cinematic/server-rules.env" "$TEST/store/worlds/cinematic_restored/server-rules.env"
cmp "$TEST/store/worlds/cinematic/data/Server/SiegerZomboid_SandboxVars.lua" "$TEST/store/worlds/cinematic_restored/data/Server/SiegerZomboid_SandboxVars.lua"
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
grep -q '^save$' "$TEST/state/rcon-calls"
grep -q '^quit$' "$TEST/state/rcon-calls"
grep -q '^setaccesslevel "kyrylo" admin$' "$TEST/state/rcon-calls"
grep -q '^setaccesslevel "kyrylo" user$' "$TEST/state/rcon-calls"
# A second process must never mutate slots while the operation lock is held.
exec 8>"$PZ_MANAGER_LOCK_FILE"
flock 8
if run create locked; then echo 'ERROR: lock bypassed' >&2; exit 1; fi
flock -u 8
# Valid checksums do not make link-based archives safe for root extraction.
mkdir -p "$TEST/hostile/data"
printf 'vanilla\n' > "$TEST/hostile/profile"
ln -s /tmp "$TEST/hostile/data/escape"
bad="$TEST/store/backups/worlds/original/world-hostile.tar.gz"
tar -czf "$bad" -C "$TEST/hostile" profile data
(cd "$(dirname "$bad")" && sha256sum "${bad##*/}" > "${bad##*/}.sha256")
if run load "$bad" hostile; then echo 'ERROR: restored symlink archive' >&2; exit 1; fi
[[ ! -e "$TEST/store/worlds/hostile" ]]
# A sidecar must match this archive, not an unrelated file in its directory.
printf '%064d  unrelated.tar.gz\n' 0 > "$bad.sha256"
if run load "$bad" wrongsum; then echo 'ERROR: accepted unrelated checksum' >&2; exit 1; fi
run create unprepared mp-test
if run start unprepared; then echo 'ERROR: started unaudited MP snapshot' >&2; exit 1; fi
printf 'ADMIN_PASSWORD=bad\n' > "$TEST/repo/config/server-rules/evil.env"
if run create evilworld vanilla auto evil; then echo 'ERROR: accepted secret in world rules' >&2; exit 1; fi
echo 'PASS: manager offline smoke test'
