#!/usr/bin/env python3
"""Generate a FULL Build 42.21 SandboxVars.lua from the pinned image default.

Strict rules: use the exact server game's default, inspect the actual Steam
Workshop files (not older GitHub copies), fail on unknown vanilla/mod options,
and never execute third-party Lua while generating a preset.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ROOT_TABLE = "SandboxVars"
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
KEY = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^,\n]*?)(\s*,\s*(?:--.*)?|\s*)$")
TABLE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*[{]\s*(?:--.*)?$")
ROOT_START = re.compile(r"^\s*(?:SandboxVars\s*=\s*|return\s*)[{]\s*(?:--.*)?$")
OPTION = re.compile(r"(?m)^\s*option\s+([A-Za-z_]\w*\.[A-Za-z_]\w*)\s*\{(.*?)^\s*\}", re.S | re.M)
VALUE = re.compile(r"(?m)^\s*([A-Za-z_]\w*)\s*=\s*([^,\n}]+)")
INTEGER = re.compile(r"^-?\d+$")
FLOAT = re.compile(r"^-?\d+(?:\.\d+)?$")
STRING = re.compile(r"""^("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')$""")


def die(message: str) -> None:
    raise SystemExit("ERROR: " + message)


def decode_literal(value: str) -> tuple[str, float | bool | str]:
    value = value.strip()
    if value in ("true", "false"):
        return "boolean", value == "true"
    if INTEGER.fullmatch(value):
        return "integer", int(value)
    if FLOAT.fullmatch(value):
        return "double", float(value)
    if STRING.fullmatch(value):
        return "string", value
    die(f"Unsupported Lua literal {value!r}. Use booleans, numeric literals or quoted strings.")


def read_intent(path: Path) -> dict[str, str]:
    if not path.is_file():
        die(f"Missing intent: {path}")
    out: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != 2:
            die(f"{path}:{number}: require TAB-separated key and Lua literal")
        name, value = fields
        if not all(IDENT.fullmatch(p) for p in name.split(".")):
            die(f"{path}:{number}: unsafe key {name!r}")
        decode_literal(value)
        if name in out:
            die(f"Duplicate intent: {name}")
        out[name] = value
    return out


def parse_vanilla(lines: list[str]) -> dict[str, tuple[int, str]]:
    """Map dotted paths to source line indexes in full game-exported Lua.

    The *generated* game's format uses one key per line and nested tables.
    Reject ambiguity rather than trying to evaluate arbitrary Lua.
    """
    if not any(ROOT_START.match(line.strip()) for line in lines):
        die("Expected a full top-level 'SandboxVars = {' table, not an excerpt")
    found_root = False
    tables: list[str] = []
    result: dict[str, tuple[int, str]] = {}
    for lineno, line in enumerate(lines):
        raw = line.split("--", 1)[0].strip()
        if not raw:
            continue
        if not found_root:
            if ROOT_START.match(raw):
                found_root = True
                tables = []
            continue
        group = TABLE.match(raw)
        if group:
            tables.append(group.group(1))
            continue
        if raw in ("}", "},", "};"):
            if tables:
                tables.pop()
            continue
        m = KEY.match(line.rstrip("\n"))
        if not m:
            continue
        name = m.group(2)
        literal = m.group(3).strip()
        if not literal or literal.startswith("{"):
            continue
        try:
            decode_literal(literal)
        except SystemExit:
            continue
        dotted = ".".join(tables + [name])
        if dotted in result:
            die("Ambiguous duplicate vanilla option: " + dotted)
        result[dotted] = lineno, literal
    return result


def patch_vanilla(text: str, wanted: dict[str, str]) -> str:
    lines = text.splitlines(keepends=True)
    existing = parse_vanilla(lines)
    version = existing.get("VERSION")
    if version is None or int(version[1]) != 6:
        die("This is NOT the expected Build 42 VERSION = 6 full SandboxVars.lua")
    missing = sorted(set(wanted) - set(existing))
    if missing:
        die("Vanilla 42.21 template does not contain keys: " + ", ".join(missing))
    for key, literal in wanted.items():
        index, previous = existing[key]
        old_type, _ = decode_literal(previous)
        new_type, _ = decode_literal(literal)
        if old_type == "boolean" or new_type == "boolean":
            if old_type != new_type:
                die(f"Type mismatch: {key} ({old_type} -> {new_type})")
        elif old_type == "string" or new_type == "string":
            if old_type != new_type:
                die(f"Type mismatch: {key} ({old_type} -> {new_type})")
        old_line = lines[index]
        # Replace value but keep indentation, comma and comments.
        m = KEY.match(old_line.rstrip("\n"))
        if not m:
            die(f"Could not locate exact source line for {key}")
        start = old_line.find(m.group(3))
        end = start + len(m.group(3))
        lines[index] = old_line[:start] + literal + old_line[end:]
    return "".join(lines)


def option_schemas(snapshot: Path, workshop_id: str, expected_mod_id: str) -> dict[str, dict[str, str]]:
    pkg = snapshot / "content" / "108600" / workshop_id
    if not pkg.is_dir():
        die(f"Workshop item missing under snapshot: {pkg}")
    info = list(pkg.rglob("mod.info"))
    ids = set()
    for file in info:
        for line in file.read_text(encoding="utf-8", errors="replace").splitlines():
            match = re.fullmatch(r"\s*id\s*=\s*([^\s#]+)\s*", line)
            if match:
                ids.add(match.group(1))
    if expected_mod_id not in ids:
        die(f"Workshop {workshop_id}: expected Mod ID {expected_mod_id} not found (found {sorted(ids)})")
    options: dict[str, dict[str, str]] = {}
    for file in pkg.rglob("sandbox-options.txt"):
        source = file.read_text(encoding="utf-8", errors="replace")
        source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
        for name, body in OPTION.findall(source):
            opts = dict((k, v.strip()) for k, v in VALUE.findall(body))
            if name in options:
                die(f"Duplicate option {name} in Workshop item {workshop_id}")
            if "type" not in opts or "default" not in opts:
                die(f"Missing type/default for {name}")
            options[name] = opts
    return options


def validate_mod_value(name: str, literal: str, schema: dict[str, str]) -> None:
    typ = schema["type"]
    our_type, our_value = decode_literal(literal)
    if typ == "boolean" and our_type != "boolean":
        die(f"{name}: expected boolean")
    if typ in ("integer", "enum") and our_type != "integer":
        die(f"{name}: expected integer/enum")
    if typ == "double" and our_type not in ("integer", "double"):
        die(f"{name}: expected decimal")
    if typ == "string" and our_type != "string":
        die(f"{name}: expected string")
    if typ not in ("boolean", "integer", "enum", "double", "string"):
        die(f"{name}: unknown mod schema type {typ!r}")
    if isinstance(our_value, (int, float)) and not isinstance(our_value, bool):
        if "min" in schema and float(our_value) < float(schema["min"]):
            die(f"{name}: {our_value} < min {schema['min']}")
        if "max" in schema and float(our_value) > float(schema["max"]):
            die(f"{name}: {our_value} > max {schema['max']}")
        if "numValues" in schema and (our_value < 1 or our_value > int(schema["numValues"])):
            die(f"{name}: invalid enum index {our_value}")


def add_mod_tables(vanilla: str, schemas: dict[str, dict[str, str]],
                   changes: dict[str, str], forge: dict[str, dict[str, str]]) -> tuple[str, bool]:
    # Only inject real mod sandbox keys. A full, exact-game base is required.
    missing = sorted(set(changes) - set(schemas))
    if missing:
        die("Installed SP/MP TLOU mod does not define: " + ", ".join(missing))
    for name, value in changes.items():
        validate_mod_value(name, value, schemas[name])

    tables: dict[str, dict[str, str]] = {}
    for name, rule in schemas.items():
        group, key = name.split(".")
        if group != "TLOU_infected":
            continue
        default = rule["default"]
        decode_literal(default)
        tables.setdefault(group, {})[key] = default

    for name, value in changes.items():
        group, key = name.split(".")
        tables[group][key] = value

    # Zero vanilla ZF type IF THIS WORKSHOP MOD REALLY EXPOSES THIS OPTION.
    # Otherwise, do not invent it. Must verify live mod's ZTypes separately.
    plain_type_control = False
    for name, value in (("ZomboidForge.ZomboidSpawn", "false"),
                        ("ZomboidForge.ZomboidChance", "0")):
        if name not in forge:
            continue
        validate_mod_value(name, value, forge[name])
        plain_type_control = True
        group, key = name.split(".")
        if group not in tables:
            tables[group] = {}
            # Populate Forge defaults only once; don't clobber a previous
            # user override when the next setting is applied.
            for other, rule in forge.items():
                prefix, suffix = other.split(".")
                if prefix == group:
                    default = rule["default"]
                    decode_literal(default)
                    tables[group][suffix] = default
        tables[group][key] = value

    # Refuse conflicting keys if the base template has mod sections already.
    existing = parse_vanilla(vanilla.splitlines(keepends=True))
    for group, keys in tables.items():
        if any(k.startswith(group + ".") for k in existing):
            die(f"Default template already has {group} keys; use fresh image default, not a live world")

    chunks = []
    for group in sorted(tables):
        chunks.append(f"    {group} = {{")
        for key, value in sorted(tables[group].items()):
            chunks.append(f"        {key} = {value},")
        chunks.append("    },")
    lines = vanilla.splitlines(keepends=True)
    closing = max((i for i, ln in enumerate(lines) if ln.strip() in ("}", "};")), default=-1)
    if closing < 0:
        die("Missing closing brace for full SandboxVars")
    lines[closing:closing] = [chunk + "\n" for chunk in chunks]
    return "".join(lines), plain_type_control


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-default", type=Path, required=True, help="Pinned image /defaults/default_SandboxVars.lua")
    parser.add_argument("--workshop", type=Path, required=True, help="Exact read-only Workshop snapshot root")
    parser.add_argument("--out", type=Path, required=True, help="New full preset output")
    parser.add_argument("--allow-unverified-vanilla", action="store_true",
                        help="Only for isolated testing: verify manually that Forge never selects vanilla ZTypes")
    args = parser.parse_args()

    base = args.game_default.read_text(encoding="utf-8")
    vanilla_intent = read_intent(BASE / "config/presets/TLOU_November_12Months.intent.tsv")
    infected_intent = read_intent(BASE / "config/presets/TLOU_November_12Months.infected.tsv")
    if vanilla_intent.get("ZombieRespawn") != "4":
        die("Expected B42 ZombieRespawn=4, which disables respawn")
    if vanilla_intent.get("MultiplierConfig.GlobalToggle") != "false":
        die("Global XP toggle must be false to honor per-skill XP")
    if "Zombies" in vanilla_intent and vanilla_intent["Zombies"] == "6":
        die("Setting Zombies=None prevents TLOU infected from having a population to convert")

    mod = option_schemas(args.workshop, "3781448194", "TLOU_Infected_MP")
    forge = option_schemas(args.workshop, "3776274080", "ZomboidForge")
    option_schemas(args.workshop, "3378285185", "StarlitLibrary")
    full = patch_vanilla(base, vanilla_intent)
    full, vanilla_control = add_mod_tables(full, mod, infected_intent, forge)
    if not vanilla_control and not args.allow_unverified_vanilla:
        die("Installed Forge exposes no ZomboidSpawn/ZomboidChance switch. "
            "Inspect actual ZTypes and verify no ZF_Zomboid is registered; "
            "ONLY on disposable test world rerun --allow-unverified-vanilla.")
    if args.out.exists():
        die(f"Output exists; will not overwrite automatically: {args.out}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_suffix(args.out.suffix + ".tmp")
    tmp.write_text(full, encoding="utf-8")
    tmp.replace(args.out)
    print("Wrote full SandboxVars preset:", args.out)
    print(f"Vanilla options applied: {len(vanilla_intent)}")
    print(f"Infected options validated: {len(infected_intent)}")
    print("Forge vanilla ZType disabled by verified sandbox option:", vanilla_control)
    if not vanilla_control:
        print("WARNING: vanilla ZType absence remains unverified; do NOT use for production.")


if __name__ == "__main__":
    main()
