#!/usr/bin/env bash
# Read-only audit of EXACT installed Workshop snapshots, not upstream B41 code.
# Usage: sudo bash scripts/audit-tlou-snapshot.sh /srv/zomboid/mod-snapshot-mp-test
# Does not execute any downloaded mod code or change any files.
set -Eeuo pipefail
ROOT="${1:-/srv/zomboid/mod-snapshot-mp-test}"
[[ -d "$ROOT" ]] || { printf 'Workshop snapshot missing: %s\n' "$ROOT" >&2; exit 2; }
ROOT="$(realpath -e -- "$ROOT")"
declare -A WANT=(
  [3781448194]=TLOU_Infected_MP
  [3776274080]=ZomboidForge
  [3378285185]=StarlitLibrary
)
found=0
for id in 3781448194 3776274080 3378285185; do
  expected="${WANT[$id]}"
  printf '\n=== Workshop %s / expected Mod ID: %s ===\n' "$id" "$expected"
  pkg=''
  while IFS= read -r -d '' file; do
    dir="$(dirname -- "$file")"
    if [[ "$dir" == */"$id"/* || "$dir" == */"$id" ]]; then
      pkg="$dir"
      break
    fi
  done < <(find "$ROOT" -type f -name mod.info -print0)
  if [[ -z "$pkg" ]]; then
    printf 'MISSING: no mod.info under Workshop %s\n' "$id" >&2
    found=1
    continue
  fi
  printf 'Package directory: %s\n' "$pkg"
  # A Workshop item can ship variants; list all mod.info in this item's tree.
  matched_id=0
  while IFS= read -r -d '' info; do
    idline="$(grep -im1 '^[[:space:]]*id[[:space:]]*=' "$info" || true)"
    printf 'mod.info: %s : %s\n' "$info" "$idline"
    if [[ "$idline" =~ ^[[:space:]]*id[[:space:]]*=[[:space:]]*([^[:space:]]+) ]]; then
      [[ "${BASH_REMATCH[1]}" != "$expected" ]] || matched_id=1
    fi
  done < <(find "$ROOT" -type f -name mod.info -path "*/$id/*" -print0)
  if ((matched_id == 0)); then
    printf 'ERROR: expected Mod ID %s not found in Workshop %s mod.info files\n' "$expected" "$id" >&2
    found=1
  fi
  printf '%s\n' 'Available sandbox-option keys / defaults:'
  count=0
  while IFS= read -r -d '' opts; do
    printf '  SOURCE %s\n' "$opts"
    # Keys+defaults only. No original mod source files are saved to Git.
    awk '
      /^[[:space:]]*option[[:space:]]+[[:alnum:]_.-]+[[:space:]]*$/ {
        name=$2; active=1; next
      }
      active && /^[[:space:]]*default[[:space:]]*=/ {
        sub(/^[[:space:]]*default[[:space:]]*=[[:space:]]*/, "", $0)
        sub(/[[:space:]]*,[[:space:]]*$/, "", $0)
        print "    " name " => default=" $0
        active=0
      }
    ' "$opts"
    count=$((count+1))
  done < <(find "$ROOT" -type f -path "*/$id/*" -name 'sandbox-options.txt' -print0)
  if ((count == 0)); then
    printf '%s\n' '  NONE in this Workshop item: inspect dependent mod documentation.'
    if [[ "$id" == 3781448194 ]]; then
      printf '%s\n' 'ERROR: MP edition has no sandbox-options.txt; do not guess spawn settings.' >&2
      found=1
    fi
  fi
  if [[ "$id" == 3781448194 ]]; then
    printf '%s\n' 'TLOU indoor/spawn behavior references (review the actual Lua around each match):'
    # Printing only matching line references, not whole mod source files.
    find "$ROOT" -type f -path "*/$id/*" -name '*.lua' -print0 |
      xargs -0 -r grep -InE 'HideIndoors|OnlyUnexplored|WanderAtNight|StalkerSpawnWeight|ClickerSpawnWeight|BloaterSpawnWeight|RunnerSpawnWeight' |
      sed -n '1,65p' || true
  fi
done
printf '\nReminder: B42.20 SP/MP fork files must be checked against active 42.21.0 client/server.\n'
printf 'Do NOT enable both TLOU_Infected_MP and TLOU_Infected_42_20.\n'
exit "$found"
