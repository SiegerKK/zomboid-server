#!/usr/bin/env python3
"""Smoke-test strict TLOU generator WITHOUT Steam or running Docker."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "scripts/generate_tlou_preset.py"
spec = importlib.util.spec_from_file_location("generator", FILE)
gen = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(gen)

with tempfile.TemporaryDirectory() as td:
    d = Path(td)
    mod_root = d / "snapshot"
    specs = {
        "3781448194": ("TLOU_Infected_MP", ROOT / "config/presets/TLOU_November_12Months.infected.tsv"),
        "3776274080": ("ZomboidForge", None),
        "3378285185": ("StarlitLibrary", None),
    }
    for wk, (modid, intent_file) in specs.items():
        pkg = mod_root / "content/108600" / wk / "mods" / modid
        (pkg / "media").mkdir(parents=True)
        (pkg / "mod.info").write_text(f"id={modid}\n", encoding="utf-8")
        options = []
        if intent_file is not None:
            for name, value in gen.read_intent(intent_file).items():
                kind, _ = gen.decode_literal(value)
                typ = "boolean" if kind == "boolean" else "integer" if kind == "integer" else "double"
                options.append(f"option {name}\n{{\n type = {typ},\n default = {value},\n")
                if typ != "boolean":
                    options.append(" min = 0,\n max = 1000,\n")
                options.append("}\n")
        if wk == "3776274080":
            options.append("option ZomboidForge.ZomboidSpawn\n{\n type = boolean,\n default = true,\n}\n")
            options.append("option ZomboidForge.ZomboidChance\n{\n type = integer,\n default = 500,\n min = 0,\n max = 1000,\n}\n")
        if options:
            (pkg / "media/sandbox-options.txt").write_text("".join(options), encoding="utf-8")
    vanilla = gen.read_intent(ROOT / "config/presets/TLOU_November_12Months.intent.tsv")
    flat = {}
    nested = {}
    for dotted, value in vanilla.items():
        typ, _ = gen.decode_literal(value)
        default = "false" if typ == "boolean" else "1" if typ in ("integer", "double") else value
        if "." not in dotted:
            flat[dotted] = default
        else:
            section, name = dotted.split(".", 1)
            nested.setdefault(section, {})[name] = default
    lines = ["SandboxVars = {", "    VERSION = 6,"]
    for name, value in flat.items():
        lines.append(f"    {name} = {value},")
    for section, keys in nested.items():
        lines.append(f"    {section} = {{")
        for key, value in keys.items():
            lines.append(f"        {key} = {value},")
        lines.append("    },")
    lines.append("}")
    game = d / "pinned-default.lua"
    game.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out = d / "generated.lua"
    command = [sys.executable, str(FILE), "--game-default", str(game),
               "--workshop", str(mod_root), "--out", str(out)]
    r = subprocess.run(command, capture_output=True, text=True)
    if r.returncode:
        raise AssertionError(f"Generator failed: {r.stdout}\n{r.stderr}")
    final = out.read_text(encoding="utf-8")
    assert "    StartMonth = 11," in final
    assert "        Strength = 10.0," in final
    assert "        Fitness = 10.0," in final
    assert "        Mechanics = 4.0," in final
    assert "        Woodwork = 5.0," in final
    assert "        ClickerSpawnWeight = 110," in final
    assert "        BloaterSpawnWeight = 0," in final
    assert "        ZomboidSpawn = false," in final
    assert "        ZomboidChance = 0," in final
    assert "    TLOU_infected = {" in final
    assert "    ZomboidForge = {" in final
    assert "Forge vanilla ZType disabled" in r.stdout
    assert gen.parse_vanilla(final.splitlines(keepends=True)).get("TLOU_infected.RunnerSpawnWeight")
    # Can't silently overwrite any verified generated world.
    assert subprocess.run(command, capture_output=True).returncode != 0
    # Different mod build: never silently invent missing options.
    mp = mod_root / "content/108600/3781448194/mods/TLOU_Infected_MP/media/sandbox-options.txt"
    mp.write_text("option TLOU_infected.RunnerSpawn\n{\n type = boolean,\n default = true,\n}\n", encoding="utf-8")
    assert subprocess.run(command[:-1] + [str(d / "bad.lua")], capture_output=True).returncode != 0
    # Bad build version => also refuse.
    game.write_text(game.read_text().replace("VERSION = 6", "VERSION = 5"), encoding="utf-8")
    assert subprocess.run(command[:-1] + [str(d / "bad2.lua")], capture_output=True).returncode != 0
print("PASS: exact-game sandbox generation and exact-Workshop validation")
