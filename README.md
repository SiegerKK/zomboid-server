# SiegerKK Project Zomboid server

Private multiplayer gameplay; **public configuration, never public credentials or worlds**. New Build 42 world, 2–6 players, Contabo Ubuntu VPS (8 vCPU/~23 GiB RAM), ports 16261/16262 UDP. Java heap 8192m; container limit 12g.

## Status
Vanilla Build 42.21.0 has started on the VPS and passed a clean save/quit, container recreation, cold backup and archive extraction. Direct A2S and RakNet UDP replies were received from the local Ubuntu client. Production currently has no shared join password and no active mods; six staged mods passed a separate headless startup, with remaining warnings and multiplayer acceptance pending. This uses a [third-party image](https://github.com/meshi-team/project-zomboid-server) pinned by digest. See [actual status](docs/BOOTSTRAP_STATUS_RU.md), [operations](docs/OPERATIONS_RU.md), and the [two-player test](docs/MULTIPLAYER_TEST_RU.md).

## First steps on Ubuntu

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
bash scripts/diagnose.sh
docker compose stop -t 180 zomboid
bash scripts/backup.sh
docker compose up -d
```

Backups in `/srv/zomboid/backups` are local-only; keep independent external copies. SaaS should run in a separate Docker Compose project, using remaining RAM.

### ChatGPT-managed changes
Bootstrap uses a verified local SSH client session to the VPS; GitHub has no deployment identity or VPS secrets. Application changes remain in PR #1 for review. Add SSH deployment only with a dedicated restricted identity, verified host key, protected environment and manual approval. Public repos must never auto-deploy unreviewed pull requests or expose secrets to CI jobs.
