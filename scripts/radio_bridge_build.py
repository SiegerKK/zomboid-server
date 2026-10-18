#!/usr/bin/env python3
"""Compile the opt-in CLIENT Java FMOD bridge against the owner's own PZ JAR.

Never download a random game JAR, ship test stubs, auto-enable ZombieBuddy, or
silently overwrite a previous client build. Requires Java 17+ compiler.
"""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "mods/SiegerRadio/42/media/java/src/siegerradio/bridge/SiegerRadioBridge.java"
OUTPUT = ROOT / "mods/SiegerRadio/42/media/java/client/SiegerRadioBridge.jar"

def build(jar: Path, output: Path):
    if not jar.is_file() or jar.is_symlink() or jar.suffix.lower() != ".jar":
        raise ValueError("Specify the installed Project Zomboid game JAR (not test stubs)")
    if output.exists() or output.is_symlink():
        raise ValueError("Output already exists: review/delete old bridge before rebuilding")
    javac = shutil.which("javac")
    jarbin = shutil.which("jar")
    if not javac or not jarbin:
        raise ValueError("Java JDK with javac and jar required")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="siegerradio-bridge-") as td:
        classes = Path(td) / "classes"; classes.mkdir()
        args = [javac, "--release", "17", "-classpath", str(jar.resolve()),
                "-d", str(classes), str(SOURCE)]
        result = subprocess.run(args, capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise ValueError("Bridge javac compile failed against your exact game JAR:\n" +
                             result.stderr[-2000:])
        expected = classes / "siegerradio/bridge/SiegerRadioBridge.class"
        if not expected.is_file():
            raise ValueError("Missing compiled client bridge class")
        subprocess.run([jarbin, "--create", "--file", str(output), "--no-manifest",
                        "-C", str(classes), "siegerradio"], check=True, timeout=30)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print("BUILT client-only JAR:", output, "SHA-256:", digest)
    print("Do not enable without inspecting the source and accepting ZombieBuddy's approval dialog.")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-jar", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    try: build(args.game_jar, args.output)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(2, "SiegerRadio Java build: " + str(error) + "\n")

if __name__ == "__main__": main()
