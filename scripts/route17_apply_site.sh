#!/usr/bin/env bash
# Route 17 guarded one-scene-at-a-time tool. Default is READ-ONLY preview.
# No automatic world restart, no live-begin, no merge, no restoration or cleanup.
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd -- "$here/.." && pwd)"

usage() {
  cat >&2 <<'EOF'
Usage:
  bash scripts/route17_apply_site.sh bar|shop --scan JSON --scene SCENE
  sudo bash scripts/route17_apply_site.sh bar|shop --scan JSON --scene SCENE --apply
  sudo bash scripts/route17_apply_site.sh shop --scan JSON --scene smokeys_shop_03_infected --apply --allow-infected
  sudo bash scripts/route17_apply_site.sh shop --scan JSON --scene smokeys_shop_04_bathroom_corpse --apply --allow-corpses

No --apply: read-only SHA-pinned scan audit plus scene validate/preview.
--apply: ONE scene only; requires root, existing open Story live session and explicit --yes inside pz.
--allow-infected: required only for the shop enemy scene; never implied.
--allow-corpses: required only for the shop bathroom body+revolver scene; never implied.
--allow-environment/--allow-barricades: required together only for scene 06 (bar) / 05 (shop).
The new server Lua corpse adapter must be installed/restarted before --apply.
EOF
  exit 2
}

(( $# >= 1 )) || usage
site="$1"; shift
case "$site" in
  bar)
    scenes=(
      smokeys_bar_01_public
      smokeys_bar_02_service
      smokeys_bar_03_upstairs
      smokeys_bar_04_lived_in
      smokeys_bar_05_departure
      smokeys_bar_06_fortification
    )
    ;;
  shop)
    scenes=(
      smokeys_shop_01_aftermath
      smokeys_shop_02_details
      smokeys_shop_03_infected
      smokeys_shop_04_bathroom_corpse
      smokeys_shop_05_window_blood
    )
    ;;
  *) usage ;;
esac
scan=""
scene=""
apply=0
allow_infected=0
allow_corpses=0
allow_environment=0
allow_barricades=0
while (( $# > 0 )); do
  case "$1" in
    --scan) (( $# >= 2 )) || usage; scan="$2"; shift 2 ;;
    --scene) (( $# >= 2 )) || usage; scene="$2"; shift 2 ;;
    --apply) apply=1; shift ;;
    --allow-infected) allow_infected=1; shift ;;
    --allow-corpses) allow_corpses=1; shift ;;
    --allow-environment) allow_environment=1; shift ;;
    --allow-barricades) allow_barricades=1; shift ;;
    *) usage ;;
  esac
done
[[ -f "$scan" && -n "$scene" ]] || usage
allowed=0
for id in "${scenes[@]}"; do [[ "$id" == "$scene" ]] && allowed=1; done
(( allowed == 1 )) || { echo "Scene is not part of $site" >&2; exit 2; }
[[ "$site" == shop || ( $allow_infected -eq 0 && $allow_corpses -eq 0 ) ]] ||
  { echo "Bar never accepts --allow-infected or --allow-corpses" >&2; exit 2; }
if [[ "$scene" == smokeys_shop_03_infected ]]; then
  if (( apply == 1 && allow_infected == 0 )); then
    echo "Enemy scene requires explicit --allow-infected" >&2; exit 2
  fi
elif (( allow_infected == 1 )); then
  echo "Only smokeys_shop_03_infected accepts --allow-infected" >&2; exit 2
fi

if [[ "$scene" == smokeys_shop_04_bathroom_corpse ]]; then
  if (( apply == 1 && allow_corpses == 0 )); then
    echo "Corpse scene requires explicit --allow-corpses" >&2; exit 2
  fi
elif (( allow_corpses == 1 )); then
  echo "Only smokeys_shop_04_bathroom_corpse accepts --allow-corpses" >&2; exit 2
fi
if [[ "$scene" == smokeys_bar_06_fortification || "$scene" == smokeys_shop_05_window_blood ]]; then
  if (( apply == 1 && ( allow_environment == 0 || allow_barricades == 0 ) )); then
    echo "Environment scenes require --allow-environment and --allow-barricades" >&2
    exit 2
  fi
elif (( allow_environment == 1 || allow_barricades == 1 )); then
  echo "Only reviewed environment scenes accept --allow-environment/--allow-barricades" >&2
  exit 2
fi
# Audit ALL scenes for the site against the original owner SHA-pinned export.
python3 "$repo/story/campaign/route17_scan_audit.py" \
  --site "$site" --scan "$scan" "${scenes[@]}"
python3 "$repo/story/storyctl.py" validate "$scene"
python3 "$repo/story/storyctl.py" preview "$scene"

if (( apply == 0 )); then
  echo "READ-ONLY preview complete; no requests queued. Use --apply for ONE scene."
  exit 0
fi

[[ "$(id -u)" -eq 0 ]] || { echo "--apply must run as root" >&2; exit 2; }
command -v pz >/dev/null || { echo "Root-owned pz manager command not installed" >&2; exit 2; }
pz story live-status story_test
echo "Applying exactly one reviewed $site scene to existing story_test: $scene"
if (( allow_infected == 1 )); then
  pz story apply-live story_test "$scene" --allow-infected --yes
elif (( allow_corpses == 1 )); then
  pz story apply-live story_test "$scene" --allow-corpses --yes
elif (( allow_environment == 1 && allow_barricades == 1 )); then
  pz story apply-live story_test "$scene" --allow-environment --allow-barricades --yes
else
  pz story apply-live story_test "$scene" --yes
fi
echo "Game remains online. Wait for scene ACK before applying another:"
echo "  sudo pz story live-status story_test"
