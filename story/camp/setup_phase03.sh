#!/usr/bin/env bash
# Farm settlement setup wrapper; uses the existing pz story build setup only.
set -Eeuo pipefail
umask 077
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
if (( $# < 1 )); then
  printf 'Usage: %s WORLD [PRIVATE_PLAN_DIR] [--survey CURRENT.json] [--backup EXISTING.tar.gz --yes] [--allow-existing] [--resume|--status]\n' "$0" >&2
  exit 2
fi
WORLD="$1"
shift
if (( $# > 0 )) && [[ "$1" != -* ]]; then
  PLAN_DIR="$1"
  shift
else
  PLAN_DIR="${PZ_CAMP_PLAN_DIR:-$HERE/private}"
fi
if [[ ! -d "$PLAN_DIR" ]]; then
  printf 'Private plan directory does not exist: %s\n' "$PLAN_DIR" >&2
  exit 2
fi
# Review flags only: the stage, source world and input names cannot be overridden.
for arg in "$@"; do
  case "$arg" in
    --file|--file=*|--stage|--stage=*|--batch|--batch=*|--source-world|--source-world=*)
      printf 'Cannot override reviewed stage/input field: %s\n' "$arg" >&2
      exit 2 ;;
  esac
done
PLAN_DIR="$(cd -- "$PLAN_DIR" && pwd -P)"

for filename in stages_build.json phase03_items_batch.json phase03_liquids_batch.json phase03_bedding_batch.json; do
  if [[ ! -f "$PLAN_DIR/$filename" || -L "$PLAN_DIR/$filename" ]]; then
    printf 'Required private plan missing/unsafe: %s\n' "$PLAN_DIR/$filename" >&2
    exit 2
  fi
done

args=(story build setup "$WORLD"
  --file "$PLAN_DIR/stages_build.json" --stage phase03
  --batch "$PLAN_DIR/phase03_items_batch.json"
  --batch "$PLAN_DIR/phase03_liquids_batch.json"
  --batch "$PLAN_DIR/phase03_bedding_batch.json"
)
exec "${PZ_BIN:-pz}" "${args[@]}" "$@"
