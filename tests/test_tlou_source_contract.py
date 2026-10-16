#!/usr/bin/env python3
"""Verify real snapshot acceptance and fail-closed behavior on isolated copies."""
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('generator', root / 'scripts/generate_tlou_preset.py')
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)
snapshot = Path(sys.argv[1])
assert gen.audited_registry_contract(snapshot)
proof = json.loads((root / 'config/presets/TLOU_November_12Months.sources.json').read_text())
with tempfile.TemporaryDirectory() as directory:
    copied = Path(directory)
    for name in proof['files']:
        target = copied / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(snapshot / name, target)
    assert gen.audited_registry_contract(copied)
    target = next(copied.rglob('*.lua'))
    target.write_text(target.read_text() + '\n-- unreviewed change\n')
    try:
        gen.audited_registry_contract(copied)
    except SystemExit:
        pass
    else:
        raise AssertionError('Unreviewed Workshop mutation was accepted')
    shutil.copyfile(snapshot / target.relative_to(copied), target)
    extra = copied / 'content/108600/3776274080/mods/ZomboidForge_B42_20/common/media/lua/shared/Unexpected.lua'
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text('-- unreviewed common overlay\n')
    try:
        gen.audited_registry_contract(copied)
    except SystemExit:
        pass
    else:
        raise AssertionError('Unreviewed common Lua overlay was accepted')
print('PASS: exact sources accepted; modified files and new common overlays refused')
