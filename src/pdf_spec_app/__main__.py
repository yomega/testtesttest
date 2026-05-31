from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _runtime_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def _prepend_env_path(path: Path) -> None:
    if not path.exists():
        return
    current_path = os.environ.get("PATH", "")
    path_text = str(path)
    parts = current_path.split(os.pathsep) if current_path else []
    if path_text not in parts:
        os.environ["PATH"] = f"{path_text}{os.pathsep}{current_path}" if current_path else path_text


def _configure_python_runtime() -> None:
    candidate_paths: list[Path] = []

    executable_path = Path(sys.executable).resolve()
    candidate_paths.append(executable_path.parent)

    prefix_path = Path(sys.prefix).resolve()
    candidate_paths.append(prefix_path)
    candidate_paths.append(prefix_path / "Scripts")
    candidate_paths.append(prefix_path / "DLLs")

    base_prefix_path = Path(sys.base_prefix).resolve()
    candidate_paths.append(base_prefix_path)
    candidate_paths.append(base_prefix_path / "Scripts")
    candidate_paths.append(base_prefix_path / "DLLs")

    seen: set[str] = set()
    for candidate_path in candidate_paths:
        normalized = str(candidate_path).casefold()
        if normalized in seen or not candidate_path.exists():
            continue
        seen.add(normalized)
        _prepend_env_path(candidate_path)
        add_dll_directory = getattr(os, "add_dll_directory", None)
        if add_dll_directory is not None:
            try:
                add_dll_directory(str(candidate_path))
            except (FileNotFoundError, OSError):
                pass

    os.environ.setdefault("VIRTUAL_ENV", str(prefix_path))


def _configure_tk_environment() -> None:
    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root:
        bundled_path = Path(bundled_root)
        bundled_tcl = bundled_path / "_tcl_data"
        bundled_tk = bundled_path / "_tk_data"
        if bundled_tcl.exists():
            os.environ.setdefault("TCL_LIBRARY", str(bundled_tcl))
        if bundled_tk.exists():
            os.environ.setdefault("TK_LIBRARY", str(bundled_tk))
            existing_tcllibpath = os.environ.get("TCLLIBPATH", "").strip()
            bundled_tk_tcl = bundled_tk.as_posix()
            if existing_tcllibpath:
                if bundled_tk_tcl not in existing_tcllibpath:
                    os.environ["TCLLIBPATH"] = f"{existing_tcllibpath} {{{bundled_tk_tcl}}}"
            else:
                os.environ["TCLLIBPATH"] = f"{{{bundled_tk_tcl}}}"
        return

    python_root = Path(sys.base_prefix)
    tcl_root = python_root / "tcl"
    tcl_library = tcl_root / "tcl8.6"
    tk_library = _prepare_tk_library(python_root)

    if tcl_library.exists():
        os.environ.setdefault("TCL_LIBRARY", str(tcl_library))
    if tk_library.exists():
        os.environ.setdefault("TK_LIBRARY", str(tk_library))
        existing_tcllibpath = os.environ.get("TCLLIBPATH", "").strip()
        tk_library_tcl = tk_library.as_posix()
        if existing_tcllibpath:
            if tk_library_tcl not in existing_tcllibpath:
                os.environ["TCLLIBPATH"] = f"{existing_tcllibpath} {{{tk_library_tcl}}}"
        else:
            os.environ["TCLLIBPATH"] = f"{{{tk_library_tcl}}}"


def _prepare_tk_library(python_root: Path) -> Path:
    source_tk_library = python_root / "tcl" / "tk8.6"
    source_pkg_index = source_tk_library / "pkgIndex.tcl"
    runtime_root = _runtime_base_dir() / ".runtime" / "tk"
    runtime_tk_library = runtime_root / "tk8.6"
    runtime_pkg_index = runtime_tk_library / "pkgIndex.tcl"
    tk_dll = (python_root / "DLLs" / "tk86t.dll").as_posix()

    if not source_tk_library.exists():
        return source_tk_library

    runtime_root.mkdir(parents=True, exist_ok=True)
    if not runtime_tk_library.exists():
        shutil.copytree(source_tk_library, runtime_tk_library)

    if source_pkg_index.exists():
        content = source_pkg_index.read_text(encoding="utf-8")
        patched = content.replace(
            '[list load [file join $dir .. .. bin tk86t.dll]]',
            f'[list load "{tk_dll}"]',
        ).replace(
            '[list load [file join $dir .. .. bin libtk8.6.dll]]',
            f'[list load "{tk_dll}"]',
        )
        runtime_pkg_index.write_text(patched, encoding="utf-8")

    return runtime_tk_library


from .app import main


if __name__ == "__main__":
    _configure_python_runtime()
    _configure_tk_environment()
    raise SystemExit(main())
