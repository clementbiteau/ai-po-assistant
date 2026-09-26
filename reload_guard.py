"""Keep project modules in step with the files on disk across Streamlit reruns.

Streamlit reruns ``app.py`` inside a long-lived process that keeps every
imported module in ``sys.modules``. When a deploy updates the files without
restarting that process, ``app.py`` runs fresh while ``agents``, ``ui.style``…
can still be the old versions: a name added in the same commit then fails to
import (``ImportError``) until someone reboots the app. :func:`refresh` drops
every project module as soon as one of their files changed since it was
imported, so the next imports load the current code.

No Streamlit import here; the bookkeeping lives on ``sys`` so that it survives
a change of ``app.py`` itself.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_STATE = "_po_assistant_module_mtimes"


def _project_modules() -> dict[str, Path]:
    """Imported modules whose source file lives in the project (not in a virtualenv)."""
    found = {}
    for name, module in list(sys.modules.items()):
        file = getattr(module, "__file__", None)
        if not file or name in ("__main__", __name__):
            continue
        path = Path(file).resolve()
        if path.is_relative_to(_ROOT) and "site-packages" not in path.parts:
            found[name] = path
    return found


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _bytecode_is_stale(path: Path) -> bool:
    """Whether the bytecode cached when the module was imported no longer matches its source.

    A timestamp-based ``.pyc`` records the source's mtime and size (PEP 552):
    after a deploy rewrote the source, they differ. This covers modules imported
    before :func:`remember` ever ran in this process (e.g. the first run after
    this guard shipped). Without a readable ``.pyc``, nothing is assumed.
    """
    try:
        header = Path(importlib.util.cache_from_source(str(path))).read_bytes()[:16]
        stat = path.stat()
    except (OSError, NotImplementedError, ValueError):
        return False
    if len(header) < 16 or int.from_bytes(header[4:8], "little") != 0:  # hash-based pyc: no timestamp
        return False
    mtime, size = int.from_bytes(header[8:12], "little"), int.from_bytes(header[12:16], "little")
    return (mtime, size) != (int(stat.st_mtime) & 0xFFFFFFFF, stat.st_size & 0xFFFFFFFF)


def refresh() -> list[str]:
    """Forget all project modules if any of their files changed; return the names dropped."""
    seen: dict[str, float | None] = getattr(sys, _STATE, {})
    modules = _project_modules()

    def changed(name: str, path: Path) -> bool:
        return _mtime(path) != seen[name] if name in seen else _bytecode_is_stale(path)

    if not any(changed(name, path) for name, path in modules.items()):
        return []
    for name in modules:
        sys.modules.pop(name, None)
    return sorted(modules)


def remember() -> None:
    """Record the files of the project modules just imported (call after the imports)."""
    setattr(sys, _STATE, {name: _mtime(path) for name, path in _project_modules().items()})
