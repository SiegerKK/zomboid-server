# SiegerKK Project Zomboid server

Private multiplayer gameplay; **public configuration, never public credentials or worlds**. New Build 42 world, 2–6 players, Contabo Ubuntu VPS (8 vCPU/~23 GiB RAM), ports 16261/16262 UDP. Java heap 8192m; container limit 12g.

## Status
Build 42.21.0 runs **road_home**, the TLOU SP/MP world, with six verified mods and no shared join password on **62.171.140.149:16261**. The Bash manager is `sudo pz`; original and legacy saves are preserved. Full Sandbox, live special-infected registry, cold backup/restore boot, empty-server pause and external UDP replies passed. Two-client authentication, infected behavior and driving synchronization still require real players. See [current deployment and connection instructions](docs/ROAD_HOME_STATUS_RU.md), [world management](docs/WORLD_MANAGER_RU.md), and the [two-player test](docs/MULTIPLAYER_TEST_RU.md).

## First steps on Ubuntu

These bootstrap commands apply only to a NEW VPS. On the deployed multiworld VPS use `sudo pz`; direct Compose commands bypass the selected world.

Install Docker Engine and Compose using the [official instructions](https://docs.docker.com/engine/install/ubuntu/). Do not disable SSH password login until SSH key login is verified in a second terminal. Prepare directories (with ownership for your intended Docker operator):

```bash
sudo mkdir -p /srv/zomboid/{data,workshop,backups}
git clone https://github.com/SiegerKK/zomboid-server.git
cd zomboid-server
cp .env.example .env
chmod 600 .env
nano .env
docker compose config --quiet
docker compose up -d
docker compose logs -f --tail=100 zomboid
```

Replace all placeholder passwords in VPS-only `.env` with independent strong secrets; never send passwords/SSH keys to ChatGPT or GitHub. Operator needs write access to `/srv/zomboid/`; `docker` group membership is root-equivalent.

Allow UDP ports **16261 and 16262** at the VPS provider firewall and system firewall. Do not expose RCON/27015, database ports, or Docker daemon. Docker port publication can bypass UFW rules. Join through the game's Join menu by public IPv4, port 16261, relay off for a direct-UDP test.

First boot is unmodded. Provide Workshop item links for verified Build 42 mods; populate both `WORKSHOP_ITEMS` and internal `MODS` in `config/mods.env`. Do not install/update mods mid-session.

## Operations
```bash
sudo pz status
sudo pz save
sudo pz logs
```

Backups in `/srv/zomboid/backups` are local-only; keep independent external copies. SaaS should run in a separate Docker Compose project, using remaining RAM.

### ChatGPT-managed changes
Bootstrap uses a verified local SSH client session to the VPS; GitHub has no deployment identity or VPS secrets. Application changes remain in PR #1 for review. Add SSH deployment only with a dedicated restricted identity, verified host key, protected environment and manual approval. Public repos must never auto-deploy unreviewed pull requests or expose secrets to CI jobs.

## Управление несколькими мирами (один репозиторий)

Менеджер `pz` реализован **на Bash** в корне этого репозитория. После безопасного
переноса текущего мира использовать:

```bash
sudo pz start                  # пронумерованный выбор и фоновый запуск
sudo pz stop
sudo pz save                   # cold snapshot + restart
sudo pz save-live              # RCON save без остановки
sudo pz load                   # восстановление backup в новый слот
sudo pz create horror tlou
sudo pz list
sudo pz status
sudo pz logs
```

Отдельный мир = отдельный `/srv/zomboid/worlds/<имя>/data`; глобальный
Workshop snapshots раздельны по модовому профилю. `PAUSE_EMPTY=true` замораживает игровое время,
но не выключает контейнер. Документация и безопасный план миграции:
[WORLD_MANAGER_RU.md](docs/WORLD_MANAGER_RU.md).
На VPS команда установлена символьной ссылкой на root-owned `/opt/zomboid-server/pz`; исходник, Compose и профили остаются в одном репозитории.

## Story Director (experimental)

Narrative scenes are JSON files under `story/scenes/`, with an isolated server-only Lua executor mounted **only** for a selected world containing an approved `story/bundle.lua`. No added network ports, no arbitrary Lua from prompts. Use `sudo pz story validate clinic_last_shift`, `preview`, `inspect`, and `apply` after a verified cold backup on a disposable world. The bundled clinic is an **unmapped draft**, not live content.

See [Story Director guide](docs/STORY_DIRECTOR_RU.md). Text notes and item placements are implemented; barricades require special approval and tested exact selectors. TLOU typed spawns and structural construction remain intentionally blocked until verified on Build 42.21. The prototype does not auto-apply to `road_home`.


### Story Director: player-centred inspection (experimental)

Once the read-only runtime is tested and installed in a disposable world, `sudo pz story scan-player story_test GAME_LOGIN --yes` captures **loaded** 25×25×5 squares around that connected account, including objects and container contents, as an exportable JSON report. No map mutations, no added ports. See [docs/STORY_PLAYER_SCAN_RU.md](docs/STORY_PLAYER_SCAN_RU.md). This requires Codex to test first in `story_test`, not to deploy directly to `road_home`.
