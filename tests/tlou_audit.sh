#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TEST="$(mktemp -d)"
trap 'rm -rf -- "$TEST"' EXIT
for pair in 3781448194:TLOU_Infected_MP 3776274080:ZomboidForge 3378285185:StarlitLibrary; do
  id="${pair%%:*}" name="${pair#*:}"
  dir="$TEST/content/108600/$id/mods/$name"
  mkdir -p "$dir/media"
  printf 'id=%s\n' "$name" > "$dir/mod.info"
  if [[ "$id" == 3781448194 ]]; then
    printf 'option TLOU_infected.HideIndoors\n{\n default = true,\n}\n' > "$dir/media/sandbox-options.txt"
    printf '%s\n' 'if SandboxVars.TLOU_infected.HideIndoors then end' > "$dir/media/stalker.lua"
  fi
done
bash "$ROOT/scripts/audit-tlou-snapshot.sh" "$TEST" > "$TEST/output.txt"
grep -q 'TLOU_infected.HideIndoors => default=true' "$TEST/output.txt"
rm -f "$TEST/content/108600/3781448194/mods/TLOU_Infected_MP/media/sandbox-options.txt"
if bash "$ROOT/scripts/audit-tlou-snapshot.sh" "$TEST" >/dev/null 2>&1; then
  printf 'ERROR: audit should refuse MP edition without sandbox definitions\n' >&2
  exit 1
fi
printf 'PASS: Workshop source audit requires exact IDs and MP sandbox definitions\n'
