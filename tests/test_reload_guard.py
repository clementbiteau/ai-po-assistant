"""A deploy that rewrites project files under a running server must not leave stale modules."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import reload_guard

PROBE = Path(__file__).parent / "fixtures" / "guard_probe.py"


def _write(value: int, bump: int) -> None:
    PROBE.write_text(f"VALUE = {value}\n", encoding="utf-8")
    stamp = PROBE.stat().st_mtime + bump
    os.utime(PROBE, (stamp, stamp))


def test_changed_files_are_reimported_with_or_without_prior_bookkeeping() -> None:
    modules, state = dict(sys.modules), getattr(sys, reload_guard._STATE, None)
    sys.path.insert(0, str(PROBE.parent))
    try:
        _write(1, 0)
        assert importlib.import_module("guard_probe").VALUE == 1
        reload_guard.remember()
        assert reload_guard.refresh() == []  # nothing changed

        _write(2, 10)  # a deploy rewrites the file
        assert "guard_probe" in reload_guard.refresh()
        assert importlib.import_module("guard_probe").VALUE == 2

        # First run after the guard shipped: no bookkeeping yet, the bytecode cache tells.
        delattr(sys, reload_guard._STATE)
        _write(3, 20)
        assert "guard_probe" in reload_guard.refresh()
        assert importlib.import_module("guard_probe").VALUE == 3
    finally:
        sys.path.remove(str(PROBE.parent))
        sys.modules.clear()
        sys.modules.update(modules)
        if state is None:
            if hasattr(sys, reload_guard._STATE):
                delattr(sys, reload_guard._STATE)
        else:
            setattr(sys, reload_guard._STATE, state)
        PROBE.unlink(missing_ok=True)
