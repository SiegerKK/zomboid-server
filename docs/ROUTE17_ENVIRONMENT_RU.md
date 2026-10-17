# Route 17: barricades, blood and shattered windows — staged environment pass

**World:** only existing `story_test`; DO NOT restore, reset, wipe or switch
to road_home. Requires prior vehicle/window diagnostics PR and the existing
Story Director installed on this same world.

## Existing behavior vs proposed actions

- Existing server Story Director had `barricade` for offline/staged actions,
  but not approved in `apply-live`; this PR makes it an explicit opt-in
  **for IsoWindow selectors only**.
- New `blood` action invokes `IsoGridSquare.splatBlood(0,0.60)` 1–3
  times on a scanned, exact-matching floor sprite.
- New `window` operation `smash` invokes `IsoWindow.smashWindow(false,false)`
  on an exact class/index/sprite match, only if the window is intact and not
  barricaded. This is intentional environmental destruction and can affect
  traversal. **Do not do it while players are in the target room.**
- `window.operation=repair` validates in draft mode but is **refused** in
  ready/live mode: blindly calling `setSmashed(false)` does not recreate
  a vanilla glass pane, its item recipe, collision and MP state. Rebuilding
  and repairing windows needs a separately tested recipe/placement adapter
  for pinned B42.21.0. Some glass-pane types are already craftable or
  replacable in Build 42; verify in-game and do not assume every pane fits.
- All environment actions require a reviewed existing `story_test` live
  session and explicit `--allow-environment`; barricades require
  `--allow-barricades`. Mutations mark per-action attempt before altering
  the world; ambiguous crashes refuse automatic replays. After confirmed
  success, the square also stores the durable action idempotence marker.

## Route 17 authored scenery (separate files)

`story/scenes/smokeys_bar_06_fortification.json`

| Action | Location X,Y,Z | Material |
|---|---|---|
| west_window_late | 10616,9228,0 | 2 boards, `walls_commercial_01_80`, object #1 |
| west_window_south | 10616,9233,0 | 2 boards, same sprite, object #1 |
| service_window | 10626,9219,0 | 1 board, same sprite, object #1 |
| hall_dried_blood | 10618,9224,0 | 1 splat on `floor_carpet_motif_8` |
| entry_old_stain | 10624,9228,0 | 1 splat on `floor_carpet_motif_8` |

Smokey's remains a base abandoned **in order** on 7 November, not a
scene of a wholesale massacre. The boards are practical, not a sealed cage;
the important communal entrance remains passable pending live review.

`story/scenes/smokeys_shop_05_window_blood.json`

| Action | Location X,Y,Z | Material |
|---|---|---|
| service_bay_broken_window | 10605,9407,0 | smash exact `walls_commercial_02_4` IsoWindow #1 |
| office_defensive_window | 10601,9411,0 | 2 planks on `walls_commercial_02_0` IsoWindow #1 |
| bay_clue_north | 10606,9407,0 | 2 blood splats on concrete |
| bay_clue_south | 10610,9410,0 | 3 blood splats on concrete |
| office_small_smear | 10603,9408,0 | 1 blood splat on tiles |
| bathroom_blood_trace | 10602,9403,0 | 1 blood splat on tiles, same square as separate corpse/revolver scene |

These positions were checked against original 2026-10-17 survey JSON
floor and IsoWindow selector coordinates. **Original scans do not record
actual window smashed/glass/barricade flags.** The new vehicle/window
survey pass must verify these states immediately before application.
Never smash the office window you just boarded; the two scenes deliberately
use different windows.

## Deployment: explicit operator approval

- In review, run Python and Lua 5.1 tests + pinned Java Kahlua harness.
  CI/mock is not real dedicated MP replication.
- On a zero-player maintenance window create a verified cold baseline and
  restart only the existing `story_test` game container with updated Lua.
  Do not reboot VPS. Existing open Story live session must be inspected;
  if it is in a pending/failed state, STOP and reconcile it first.
- Scan the exact areas, confirm `window_smashed=false`,
  `window_glass_removed=false`, both `window_barricaded_*=false`,
  correct floor, unobstructed adjacent doorways. If any mismatch:
  **STOP, do not work around it by choosing another window.**
- Example read-only audit:
```bash
bash scripts/route17_smokeys.sh \
  --scan /var/tmp/bar-survey-101x101x5-20261017-17bbb716.json \
  --scene smokeys_bar_06_fortification
```
- Apply only after new runtime pinning, separate approval for any window
  modifications, and no nearby players:
```bash
sudo bash scripts/route17_smokeys.sh \
  --scan /var/tmp/bar-survey-101x101x5-20261017-17bbb716.json \
  --scene smokeys_bar_06_fortification \
  --apply --allow-barricades --allow-environment

sudo pz story live-status story_test
sudo pz story quest-status story_test smokeys_bar_06_fortification
```
- For Auto Shop use the corresponding shop wrapper and scene ID
  `smokeys_shop_05_window_blood`; do not apply shop barricades while
  spawning infected in the same loaded box.

## Verification

- After live apply: `blood_edits`, `window_edits` and
  `barricade_spawns` are counted by `quest-status` from append-only
  events. Signed modifications also survive as distinct world/actor
  `modData` tags, but blood appearance/decay is not a trackable entity.
- Two clients must inspect graphics, collisions, ability to climb broken
  window, durability/interaction with boards and whether blood splats
  persist after saving and a controlled server restart.
- These engine calls are based on published API docs, not yet proven on
  the owner's B42.21 dedicated server. A failure must be logged as
  FAIL/BLOCKED, not silently retried.
- Scene application **does not touch any cars**. Car spawn is a separate
  future test after surveying actual existing vehicles and safe parking
  spots; do not invent a van or relocate H.'s Notes to a random vehicle.

## Code notes

- Input protocol is fixed newline/tab encoded data, not arbitrary Lua.
- `type=blood`: floor sprite allowlist & 1–3 splats.
- `type=window`: exact IsoWindow selector; operation `smash` only.
- `type=barricade`: exact IsoWindow selector; 1–4 planks.
- Existing note/loot/infected/corpse behavior remains untouched.
