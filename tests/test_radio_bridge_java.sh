#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v javac >/dev/null || { echo "JDK javac required"; exit 2; }
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mapfile -t src < <(find tests/radio_bridge_java -type f -name '*.java' | sort)
javac --release 17 -d "$tmp/classes" "${src[@]}" mods/SiegerRadio/42/media/java/src/siegerradio/bridge/SiegerRadioBridge.java
java -cp "$tmp/classes" SiegerRadioBridgeTest

java -Dradio.test.spreadFails=true -cp "$tmp/classes" SiegerRadioSpreadFallbackTest stereo_3d_spread_failed
# Compile a second mock ABI without the optional method. Required methods stay
# identical; this must NOT be substituted into the shipped client bridge.
mkdir -p "$tmp/no-spread/fmod" "$tmp/no-spread-classes"
python3 - "$tmp/no-spread/fmod/javafmod.java" <<'PYCODE'
import pathlib,re,sys
source=pathlib.Path('tests/radio_bridge_java/fmod/javafmod.java').read_text()
source,count=re.subn(r'    public static int FMOD_Channel_Set3DSpread\(.*?\n    }\n','',source,flags=re.S)
assert count==1
pathlib.Path(sys.argv[1]).write_text(source)
PYCODE
javac --release 17 -cp "$tmp/classes" -d "$tmp/no-spread-classes" "$tmp/no-spread/fmod/javafmod.java"
java -cp "$tmp/no-spread-classes:$tmp/classes" SiegerRadioSpreadFallbackTest stereo_3d_spread_unavailable

java -Dradio.test.busFails=true -cp "$tmp/classes" SiegerRadioSpreadFallbackTest output=stereo_bus_failed
mkdir -p "$tmp/no-bus/fmod" "$tmp/no-bus-classes"
python3 - "$tmp/no-bus/fmod/javafmod.java" <<'PYCODE'
import pathlib,re,sys
source=pathlib.Path('tests/radio_bridge_java/fmod/javafmod.java').read_text()
source,count=re.subn(r'    public static long FMOD_System_CreateChannelGroup\(.*?\n    }\n','',source,flags=re.S)
assert count==1
pathlib.Path(sys.argv[1]).write_text(source)
PYCODE
javac --release 17 -cp "$tmp/classes" -d "$tmp/no-bus-classes" "$tmp/no-bus/fmod/javafmod.java"
java -cp "$tmp/no-bus-classes:$tmp/classes" SiegerRadioSpreadFallbackTest output=stereo_bus_unavailable

# Optional per-music priority must not break native 3D when rejected/missing.
java -Dradio.test.priorityFails=true -cp "$tmp/classes" SiegerRadioSpreadFallbackTest priority=failed
mkdir -p "$tmp/no-priority/fmod" "$tmp/no-priority-classes"
python3 - "$tmp/no-priority/fmod/javafmod.java" <<'PYCODE'
import pathlib,re,sys
source=pathlib.Path('tests/radio_bridge_java/fmod/javafmod.java').read_text()
source,count=re.subn(r'    public static int FMOD_Channel_SetPriority\(.*?\n    }\n','',source,flags=re.S)
assert count==1
pathlib.Path(sys.argv[1]).write_text(source)
PYCODE
javac --release 17 -cp "$tmp/classes" -d "$tmp/no-priority-classes" "$tmp/no-priority/fmod/javafmod.java"
java -cp "$tmp/no-priority-classes:$tmp/classes" SiegerRadioSpreadFallbackTest priority=unavailable
