# Custom SandboxVars presets for Project Zomboid Build 42.21

Add complete, tested game-exported `NAME.lua` files here (example: `TLOU_Year20.lua`). Do not copy Build 41 templates into Build 42. Presets must be standalone complete `SandboxVars = { ... }` (or `return { ... }`) Lua tables from your installed Build 42.21 game or the server's exact pinned game build. Keep the full structure and mod-specific sections; do not reconstruct a minimal table by guessing enum numbers.

Create a new world with `sudo pz create ROADHOME tlou TLOU_Year20 tlou-coop`. The manager copies the Lua file to the world-specific `data/Server/SiegerZomboid_SandboxVars.lua` before first boot. `auto` instead means let the pinned server image generate its own default. It does not alter an existing world if the Git preset changes later.

SandboxVars.lua may contain executable Lua. Review source and load only trusted presets. Verify on a disposable world before production.

`TLOU_November_12Months.lua` is a full VERSION=6 export-derived preset from the pinned 42.21.0 image. Its helper `/defaults/default_SandboxVars.lua` is obsolete VERSION=5; do not relabel it. For regeneration pass `PZ_GAME_DEFAULT_EXPORT` and `PZ_GAME_DEFAULT_PROVENANCE` pointing to a stopped vanilla world's complete engine export and deployment.txt from that same image.

The exact MP/Forge source hashes in `TLOU_November_12Months.sources.json` are backed by the separate network-isolated `tests/tlou_registry.lua` run. This fork has `TLOU_infected.VanillaSpawn=false` / weight=0; Forge's absent sandbox switch is nil, so its guarded AddZomboids call does not run. Runtime server diagnostics also verify the final registered types. Changed source bytes or a changed registry test fail generation; re-audit rather than enabling the unverified flag in production.

The generated preset is already committed. The preparation script intentionally refuses to overwrite it: regenerate in a separate review copy, retain the old artifact, and compare the resulting settings before deployment. See `docs/ROAD_HOME_STATUS_RU.md` for the actual deployment and remaining client tests.
