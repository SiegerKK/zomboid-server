# Existing vehicle administration — story_test only (PR #27)

**Status: DRAFT. Runtime `8dd58f6` installed on story_test; no edits to vehicle
ID 253. The corrections below still require deployment and game acceptance.**
This is a narrow, auditable root-operated tool, not a general Lua/RCON console.
Runtime must be mounted into the pinned B42.21 dedicated server before use.

Deployment review correction: the installed client and dedicated B42.21 JARs
have identical SHA-256 `e1a69eb743ede60b213a0fe7f8b83d4fcab773036d256cc4543a336f3b058a33`.
Their `DrainableComboItem` exposes `getCurrentUsesFloat()` and
`setCurrentUsesFloat(float)` for normalized battery charge; `getUsedDelta()`
does not exist. Inspect and battery mutation now use the actual B42 methods.
The removed item IDs `Base.WaterBottleEmpty` and `Base.Cigarettes` are replaced
by actual B42.21 script definitions `Base.WaterBottle` and `Base.CigaretteSingle`.
The other eight allowlisted types are unchanged. WaterBottle is the empty
container item, not a promise of filled drinking water.

`tests/story_vehicle_control.lua` exercises that exact battery ABI, occupied
vehicle refusal, expected-value/position/capacity guards, missing sync API,
new item add/remove synchronization and replay suppression across a reload.
These are offline mocks; client replication and persistence still require
in-game acceptance. No real car or inventory was modified during review.

## Workflow

1. Scan the currently loaded car and record **exact** vehicle ID, stock
   `Base.*` script and *floored* coordinates. Verify part IDs and contents.
2. Preview a command (default no write).
3. Repeat with `--yes` only after inspecting the target. The CLI queues one
   bounded server request and prints its 32-digit request ID.
4. Poll `sudo pz story vehicle status story_test` for an exact result.
   An ACK means the server-side handler returned, **not** that clients
   have verified the changed state. Rescan and test both clients, then save
   and restart a test copy to confirm persistence.

Example for the **hypothetical** scan of ID 253: substitute its measured
coordinates before executing anything (the values below are placeholders):

```bash
sudo pz story vehicle inspect story_test --id 253 --script Base.PickUpTruck --x X --y Y --z Z
sudo pz story vehicle condition story_test --id 253 --script Base.PickUpTruck --x X --y Y --z Z --part RearWindow --expect 98 --value 99
sudo pz story vehicle fuel story_test --id 253 --script Base.PickUpTruck --x X --y Y --z Z --expect 12 --value 15
sudo pz story vehicle battery story_test --id 253 --script Base.PickUpTruck --x X --y Y --z Z --expect 0.60 --value 0.90
sudo pz story vehicle add story_test --id 253 --script Base.PickUpTruck --x X --y Y --z Z --part GloveBox --item Base.Bandage --count 1
sudo pz story vehicle remove story_test --id 253 --script Base.PickUpTruck --x X --y Y --z Z --part GloveBox --item Base.Bandage --count 1
```

All commands are previews unless `--yes` is given. No mass-clear,
unrestricted item spawning or part installation API is exposed.

## Protocol safety and limitations

- Requires the exact loaded car ID, script and tile coordinates, and
  `story_test` active via its Story bundle; no forced chunk loads.
- Mutation refuses occupied vehicles. Condition/fuel/charge requires the
  exact last observed expected value. Item types and counts are allowlisted.
- File request/response, bounded loops, in-process replay suppression,
  durable one-request guard before first mutation, explicit failure reports.
- Missing Build 42 synchronization API causes refusal. For part condition
  it uses `transmitPartCondition`; for gas tank `transmitPartModData`,
  for battery `transmitPartUsedDelta`, for containers
  `sendAddItemToContainer` / `sendRemoveItemFromContainer`.
  These names/signatures and actual client replication **must be verified
  on the installed B42.21 server** before using `--yes`.
- Changes that throw after partial writes are **not transactional**:
  fail closed and manually audit. Repeated writes are not automatically
  requeued. If result or durable guard is uncertain, do not retry.
- Only installed inventory items can be changed in existing containers;
  other vehicle state (locks, ignition, part replacement) is out of scope.

## Acceptance required before deploying

Confirm on a disposable copy with a parked unoccupied car:
read-only inspection; intended part IDs and allowed item types;
condition/fuel/battery values; correct item add/remove in two clients;
save/restart persistence; mismatching IDs/coordinates/value refusal;
duplicate request and partial-error refusal. The test suite exercises
CLI safety and Lua syntax but does **not** replace multiplayer testing.
Do not apply to road_home or world/player saves.
