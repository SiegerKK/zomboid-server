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
