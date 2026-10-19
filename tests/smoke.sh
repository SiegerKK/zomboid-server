#!/usr/bin/env bash
# Offline smoke test: a fake Docker CLI verifies slot isolation and rollback.
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TEST="$(mktemp -d)"
trap 'rm -rf -- "$TEST"' EXIT
mkdir -p "$TEST/repo/config" "$TEST/repo/config/server-rules" "$TEST/repo/config/presets" "$TEST/repo/story/scenes" "$TEST/bin" "$TEST/store/data/Server" "$TEST/state"
mkdir -p "$TEST/store/mod-snapshot/content/108600" "$TEST/store/agent"
: > "$TEST/store/agent/ZombieBuddy.jar"
: > "$TEST/repo/compose.mods.yaml"
cp "$ROOT/pz" "$TEST/repo/pz"
cp "$ROOT/story/storyctl.py" "$TEST/repo/story/storyctl.py"
cp "$ROOT/story/livectl.py" "$TEST/repo/story/livectl.py"
: > "$TEST/repo/compose.story.yaml"
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
    if [[ "${2:-}" == --format ]]; then
      python3 - <<'PY'
import json,os
m=os.environ["MOCK_DOCKER_STATE"]
w=open(m+"/mount").read().strip()
print(json.dumps({"State":{"Running":open(m+"/running").read().strip()=="true"},
 "Mounts":[{"Destination":"/root/Zomboid","Source":w},
           {"Destination":"/pzomboid-server/media/lua/server/SiegerStoryDirector.lua",
            "Source":os.environ["PZ_MANAGER_REPO_ROOT"]+"/story/runtime/SiegerStoryDirector.lua"},
           {"Destination":"/pzomboid-server/media/lua/server/ZZ_SiegerStoryScenes.lua",
            "Source":w+"/../story/bundle.lua"}]}))
PY
      exit 0
    fi
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
      players) if [[ -e "$MOCK_DOCKER_STATE/players-active" ]]; then
          echo 'Players connected (1):'; else echo 'Players connected (0):'; fi ;;
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
printf 'PING_LIMIT=0\n' > "$TEST/repo/config/server-rules/ping.env"
run create pingworld vanilla auto ping
grep -q '^PING_LIMIT=0$' "$TEST/store/worlds/pingworld/server-rules.env"
printf 'PING_LIMIT=-1\n' > "$TEST/repo/config/server-rules/badping.env"
if run create badpingworld vanilla auto badping; then echo 'ERROR: accepted negative ping limit' >&2; exit 1; fi
echo 'PASS: manager offline smoke test'

# Story archives are restored disabled, including archives of disabled restores.
run create story_source vanilla
mkdir -p "$TEST/store/worlds/story_source/story"
printf 'SiegerStoryScenes = {schema=1,world="story_source",scenes={},inspect={}}\n' > "$TEST/store/worlds/story_source/story/bundle.lua"
run save story_source
story_archive="$(find "$TEST/store/backups/worlds/story_source" -name 'world-*.tar.gz' | head -n 1)"
run load "$story_archive" story_copy
[[ ! -e "$TEST/store/worlds/story_copy/story/bundle.lua" ]]
[[ -s "$TEST/store/worlds/story_copy/story/bundle.lua.needs-review" ]]
run save story_copy
disabled_archive="$(find "$TEST/store/backups/worlds/story_copy" -name 'world-*.tar.gz' | head -n 1)"
run load "$disabled_archive" story_copy_again
[[ ! -e "$TEST/store/worlds/story_copy_again/story/bundle.lua" ]]
[[ -s "$TEST/store/worlds/story_copy_again/story/bundle.lua.needs-review" ]]
echo 'PASS: active and disabled Story archives restore without activation'

# Live begin must take a cold SHA-256 archive BEFORE activating Story on a new
# world, restart the same world, and refuse commit without server acknowledgment.
run create liveworld vanilla
run start liveworld
run story live-begin liveworld --yes
[[ -f "$TEST/store/worlds/liveworld/story/bundle.lua" ]]
[[ -f "$TEST/store/worlds/liveworld/story/live/session.json" ]]
[[ "$(cat "$TEST/state/running")" == true ]]
[[ "$(find "$TEST/store/backups/worlds/liveworld" -name 'world-*.tar.gz' | wc -l)" == 1 ]]
if run story live-commit liveworld --yes; then
  echo 'ERROR: committed Story live session without any applied actions' >&2; exit 1
fi
[[ "$(cat "$TEST/state/running")" == true ]]
run stop --yes
run create liveblocked vanilla
run start liveblocked
touch "$TEST/state/players-active"
if run story live-begin liveblocked --yes; then
  echo 'ERROR: interrupted connected players for Story pre-backup' >&2; exit 1
fi
[[ "$(cat "$TEST/state/running")" == true ]]
[[ ! -d "$TEST/store/backups/worlds/liveblocked" ]]
rm -f "$TEST/state/players-active"
run stop --yes
# A restored archive must never replay previously issued live requests.
mkdir -p "$TEST/store/worlds/liveworld/data/Lua"
printf 'v1\\told\\n' > "$TEST/store/worlds/liveworld/data/Lua/SiegerStoryLiveRequest.txt"
printf 'receipt\\n' > "$TEST/store/worlds/liveworld/data/Lua/SiegerStoryLiveResult.txt"
run save liveworld
new_live_backup="$(find "$TEST/store/backups/worlds/liveworld" -name 'world-*.tar.gz' | LC_ALL=C sort | tail -n 1)"
run load "$new_live_backup" live_restore
[[ ! -e "$TEST/store/worlds/live_restore/data/Lua/SiegerStoryLiveRequest.txt" ]]
[[ -f "$TEST/store/worlds/live_restore/data/Lua/SiegerStoryLiveRequest.txt.needs-review" ]]
[[ ! -e "$TEST/store/worlds/live_restore/story/live/session.json" ]]
[[ -f "$TEST/store/worlds/live_restore/story/live/session.json.needs-review" ]]
echo 'PASS: live Story checkpoints and safety gate for connected players'
