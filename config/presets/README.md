# Custom SandboxVars presets for Project Zomboid Build 42.21

Add complete, tested game-exported `NAME.lua` files here (example: `TLOU_Year20.lua`). Do not copy Build 41 templates into Build 42. Presets must be standalone complete `SandboxVars = { ... }` (or `return { ... }`) Lua tables from your installed Build 42.21 game or the server's exact pinned game build. Keep the full structure and mod-specific sections; do not reconstruct a minimal table by guessing enum numbers.

Create a new world with `sudo pz create ROADHOME tlou TLOU_Year20 tlou-coop`. The manager copies the Lua file to the world-specific `data/Server/SiegerZomboid_SandboxVars.lua` before first boot. `auto` instead means let the pinned server image generate its own default. It does not alter an existing world if the Git preset changes later.

SandboxVars.lua may contain executable Lua. Review source and load only trusted presets. Verify on a disposable world before production.
