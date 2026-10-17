# Story Director — read-only vehicle & damage survey (Build 42.21)

This feature extends **existing** `pz story scan-player`; it never changes the world.
Applies only to active `story_test` when deployed by the owner.

## Scan command

```bash
sudo pz story scan-player story_test GAME_LOGIN --side 51 --yes
sudo pz story scan-status story_test
sudo pz story scan-report story_test --output /var/tmp/route17-vehicles.json
```

- v2 requests 51/101 now perform an **additional vehicle pass** after visiting the squares.
  Cars are enumerated from `IsoCell.getVehicles():iterator()`; at most **128**
  vehicles whose center is inside the same survey square are inspected.
  No remote chunks are loaded and no car/spawn is created.
- `kind=vehicle`: numeric `vehicle_id`, exact `script` (e.g. Base.Van),
  floating-point world location, tile location and part count; optional
  Story tags in vehicle `modData` when present.
- `kind=vehicle_part`: `part_id`, `part_index`, condition, installed part
  `full_type`, whether a storage container exists.
- `kind=vehicle_container`: type (e.g. GloveBox or Trunk), part ID, item count.
- `kind=vehicle_item`: part ID, item slot, full type and name plus Story
  tags when present; **top-level items only**.
- Legacy v1 25×25×5 is unchanged and does **not** enumerate vehicles.
  Previously exported v2 snapshots remain valid historical files, but are
  not vehicle census snapshots.
- `vehicle_snapshot=complete` in the summary means the entire currently
  loaded `IsoCell.getVehicles` Set has been inspected, subject to the
  bounded center-area filter. This is NOT the same as scanning vehicles that
  exist in unloaded chunks, and vehicles can move during the scan.
- Limits: 128 cars, 160 parts/car, 200 items/part, total original 24 MiB and
  140k report records. Exceeding limits marks output `partial/truncated`.
  Java API failures mark partial and must NOT be considered a complete result.

Additional world state:
- v2 `square` rows may include boolean `blood_floor` and `blood_wall`.
- `IsoWindow` object rows include booleans for smashed, glass removed, open
  state, barricade on near/far side.
- Those fields are diagnostics, **not editable settings in this PR**.
  Even if an old window is broken, do not flip flags to repair it until a
  dedicated Build 42 multiplayer implementation is verified.

## How to use this for Route 17

1. Scan **Smokey's parking and rear yard** while it is loaded. Locate exact
   `BaseVehicle.script` / `vehicle_id` / parts and inspect the actual
   white van glovebox and any cargo container. Do not identify vehicles
   by script alone: multiple vans may use the same script.
2. Scan **Auto Shop parking/service yard** likewise, with special attention
   to any red sedan and salvage vehicle.
3. Export JSON files privately, include SHA-256, and share them with the
   story designer. H.'s Notes and photos belong in the white van glovebox
   **only after the exact vehicle+part are identified**.
4. Vehicle **creation** remains separate: a safe spawn adapter must validate
   no overlap, exact script, parking geometry, game version, server persistence,
   and visibility to two clients. `addVehicleDebug` is listed in the
   global engine API but its dedicated-server use is **not proven** by these
   offline tests. Do not deploy unreviewed vehicle creation code.
5. For barricades and blood, identify the correct `IsoWindow` selectors
   first, then implement narrowly scoped actions with protection from
   accidental damage to other windows.
6. `road_home` stays untouched; never reset or restore `story_test`.
   CI Lua mocks are not equivalent to the pinned game JVM acceptance.

All whole-world scans should stay outside the public Git repo by default.
