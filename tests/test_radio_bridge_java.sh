#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v javac >/dev/null || { echo "JDK javac required"; exit 2; }
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mapfile -t src < <(find tests/radio_bridge_java -type f -name '*.java' | sort)
javac --release 17 -d "$tmp/classes" "${src[@]}" mods/SiegerRadio/42/media/java/src/siegerradio/bridge/SiegerRadioBridge.java
java -cp "$tmp/classes" SiegerRadioBridgeTest
