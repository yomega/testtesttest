from __future__ import annotations

import os
import sys
from pathlib import Path


def _set_if_exists(env_name: str, path: Path) -> None:
    if path.exists():
        os.environ.setdefault(env_name, str(path))


bundle_root = Path(getattr(sys, "_MEIPASS", Path.cwd()))
_set_if_exists("TCL_LIBRARY", bundle_root / "_tcl_data")
_set_if_exists("TK_LIBRARY", bundle_root / "_tk_data")
