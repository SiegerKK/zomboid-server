# Instructions for ChatGPT Work

Read `docs/WORK_DEPLOYMENT_BRIEF_RU.md` before making VPS changes. Project host Contabo Ubuntu 24.04.5 LTS, 24 GB RAM, 62.171.140.149. Two separate Docker Compose projects: PZ and SaaS; host Nginx for SaaS ingress, inner SaaS Nginx via localhost only. Two human users kyrylo and ihor, each with independent public-key SSH identity.

Do NOT commit passwords, private SSH keys, runtime .env, game saves, user databases or backup archives. Never expose RCON/27015, PostgreSQL/5432, Redis/6379 or Docker daemon. Public game: UDP 16261 and 16262 only. SaaS: HTTPS via system Nginx -> 127.0.0.1:18080 -> container Nginx. No domain or SaaS code yet; wait rather than invent.

Do not disable current SSH access until testing a replacement login and the provider rescue console. No destructive volume deletes, forced world resets, major OS upgrades or unattended mod updates. GitHub rights do not imply VPS shell access; distinguish drafted changes from commands actually run. New world, no migration. Changes via reviewed PR and manual approval, backup, health checks and rollback.

## Multiworld operational contract

A single root-owned repository carries `pz` (Bash manager), Compose, configs and
offline tests. See `docs/WORLD_MANAGER_RU.md`. Once the manager is deployed,
do NOT run `docker compose up` directly or use the legacy
`scripts/backup.sh`, since those default to the old data path. Import the
existing world via an OFFLINE COPY with an EXPLICIT mod profile after a valid
cold backup. Do not restart live users or select a different mod profile
without verifying current Mod IDs. All world lifecycle actions share a lock,
retain old saves and require manual confirmation when disconnecting players.
Do not claim the Bash manager is active on VPS until installation and game
smoke tests are verified via SSH.

## Story Director integration

Review `docs/STORY_DIRECTOR_RU.md` before touching scenes. New scripts:
`story/storyctl.py`, `story/runtime/SiegerStoryDirector.lua`, `story/scenes/*.json`,
`compose.story.yaml`. Do not invent map coordinates/containers or TLOU spawn
adapters. First test on a **separate restored copy** of the world, with no
active players; do not enable or stage the draft clinic in `road_home`
without actual B42 coordinates and the owner's approval. `pz story apply`
requires a recent cold backup. Existing world slots without `story/bundle.lua`
must not mount Story Director at all. Keep changes in one repository; never
publish secrets or save data. Ensure CI and real Compose mounts on VPS match.


## Story Player AreaScan (experimental)

The PR feature/story-player-area-scan is stacked on fix/story-director-road-home-integration, not on an outdated main. New read-only scripts: `story/scanctl.py`, `story/runtime/SiegerStoryAreaScan.lua`. The scan reads fixed request/response files in the chosen world's `data/Lua/` and captures at most 25×25×5 loaded cells around a connected user's current position. Never introduce arbitrary remote Lua execution, unbounded OnTick scans, forced chunk generation, or public diagnostic ports. Do not upload scans of players' inventories or private base locations to public GitHub. Verify the exact pinned Build 42.21 engine file I/O APIs and Lua 5.1 harness, then deploy ONLY in `story_test` with a manual maintenance window. Road_home and other worlds remain unchanged by a mere Git update.


### Story live mode review gate

Study `docs/STORY_LIVE_SESSIONS_RU.md`. Live scene updates can mutate loaded map cells. PR #8 is opt-in and untested in real game clients. Only `note` and `loot` are supported, never arbitrary RCON Lua, zombies, structures or delete operations. `live-begin` and `live-commit` must verify RCON players=0, stop cleanly, SHA-256 cold backup and restart same slot. No public report of private inventory/scene data. Do not merge or deploy PR #8 into production until tested with two players on disposable `story_test`, cold restore, duplicate prevention and negative-path failure. Do not use merge/rebase to erase PR #4 exact TLOU sandbox fixes.

### Current owner-authorized development acceptance (2026-10-17)

For PR #8 acceptance use the existing story_test only; preserve every test
mutation and leave it running. Do not switch to road_home, restore checkpoints,
create restored worlds or reset progress. Archive verification does not imply
authorization to restore. Ask before each maintenance window; require RCON=0.
Mark incompatible/unsafe acceptance matrix steps BLOCKED. Two-client checks
remain required for MP claims; do not merge automatically. This supersedes
older test-plan directions to restore copies and return road_home.

### SiegerRadio checksum packaging (balanced-checksum1)

For radio-enabled story_test, compose.radio.yaml replaces vanilla Lua injections
with checksum-identical packaged server Lua in SiegerRadio/42/media/lua/server.
Do not restore an additional vanilla station mount or publish private world
bundles in client packs. Private scene data is a read-only .txt mount parsed by
the restricted literal reader, never eval. Keep generated runtime copies in
sync via radio_assets.render/check. DoLuaChecksum=true and AntiCheatChecksum=2
are the intended normal configuration; ordinary-player login must be tested.
See docs/STORY_RADIO_CHECKSUM_LOUDNESS_RU.md. Music/normalized WAV/client ZIPs
stay local. Legacy non-radio worlds are not migrated by this overlay.

### Independent administration (SiegerAdmin migration)

Administrative Lua and checksum-identical client copies now belong to
mods/SiegerAdmin, generated from story/runtime by scripts/admin_assets.py.
Keep SiegerRadio limited to station/audio/airtime code; never move admin code
back into its pack or inject vanilla Lua. See docs/SIEGER_ADMIN_RU.md.
Migrate clean client folders and server atomically in an authorized maintenance
window; stale SiegerRadio administrative Lua must not coexist with the new
Admin pack. Preserve world data and DoLuaChecksum=true. Online clock uses
bounded host-only requests, OnTickEvenPaused, expiry and a durable replay guard;
never expose arbitrary Lua/RCON or disable PauseEmpty to process a request.
