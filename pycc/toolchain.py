"""
Toolchain — encapsulates assembler/linker discovery and invocation.

pycc depends only on binutils (`as` + `ld`) and a C runtime (glibc-dev
preferred, newlib as fallback).  This module centralizes all path probing
so the rest of the compiler never shells out to `gcc` for linking.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Dict, List, Optional


class Toolchain:
    """Encapsulates the external toolchain (assembler + linker).

    Discovery order for each tool:
      1. Explicit constructor argument
      2. Environment variable (``PYCC_AS`` / ``PYCC_LD``)
      3. System PATH lookup for ``as`` / ``ld``
    """

    def __init__(
        self,
        *,
        assembler: Optional[str] = None,
        linker: Optional[str] = None,
    ) -> None:
        self.assembler = assembler or os.environ.get("PYCC_AS", "as")
        self.linker = linker or os.environ.get("PYCC_LD", "ld")

        # Lazily populated by probe_*() helpers.
        self._dyn_linker: Optional[str] = None
        self._crt_files: Optional[Dict[str, str]] = None
        self._lib_dirs: Optional[List[str]] = None

    # ------------------------------------------------------------------
    # Probing helpers
    # ------------------------------------------------------------------

    def probe_dynamic_linker(self) -> Optional[str]:
        """Return the path to the glibc dynamic linker, or *None*."""
        if self._dyn_linker is not None:
            return self._dyn_linker
        candidates = [
            "/lib64/ld-linux-x86-64.so.2",
            "/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2",
            "/lib/ld-linux-x86-64.so.2",
        ]
        self._dyn_linker = _first_existing(candidates)
        return self._dyn_linker

    def probe_crt_files(self) -> Dict[str, str]:
        """Return a dict with keys ``crt1``, ``crti``, ``crtn``,
        ``crtbegin``, ``crtend`` mapped to their absolute paths.

        Missing entries are omitted from the dict.
        """
        if self._crt_files is not None:
            return self._crt_files

        crt1 = _first_existing([
            "/usr/lib/x86_64-linux-gnu/crt1.o",
            "/usr/lib64/crt1.o",
            "/usr/lib/crt1.o",
        ])
        crti = _first_existing([
            "/usr/lib/x86_64-linux-gnu/crti.o",
            "/usr/lib64/crti.o",
            "/usr/lib/crti.o",
        ])
        crtn = _first_existing([
            "/usr/lib/x86_64-linux-gnu/crtn.o",
            "/usr/lib64/crtn.o",
            "/usr/lib/crtn.o",
        ])

        crtbegin, crtend = _probe_gcc_crt()

        result: Dict[str, str] = {}
        if crt1:
            result["crt1"] = crt1
        if crti:
            result["crti"] = crti
        if crtn:
            result["crtn"] = crtn
        if crtbegin:
            result["crtbegin"] = crtbegin
        if crtend:
            result["crtend"] = crtend

        self._crt_files = result
        return self._crt_files

    def probe_lib_dirs(self) -> List[str]:
        """Return library search directories (GCC runtime dirs first)."""
        if self._lib_dirs is not None:
            return self._lib_dirs

        gcc_libdirs = _probe_gcc_lib_dirs()
        system_libdirs = [
            "/lib/x86_64-linux-gnu",
            "/usr/lib/x86_64-linux-gnu",
            "/lib64",
            "/usr/lib64",
            "/lib",
            "/usr/lib",
        ]
        self._lib_dirs = gcc_libdirs + [d for d in system_libdirs if os.path.isdir(d)]
        return self._lib_dirs

    # ------------------------------------------------------------------
    # Command builders
    # ------------------------------------------------------------------

    def build_link_cmd(
        self,
        obj_paths: List[str],
        output: str,
        *,
        extra_libs: Optional[List[str]] = None,
        extra_lib_dirs: Optional[List[str]] = None,
        shared: bool = False,
    ) -> List[str]:
        """Build a full ``ld`` command line for linking *obj_paths*.

        Raises ``RuntimeError`` when the required toolchain components
        cannot be found.
        """
        ld_path = shutil.which(self.linker)
        if not ld_path:
            raise RuntimeError(
                f"linker '{self.linker}' not found on PATH; "
                "install binutils or set PYCC_LD"
            )

        dyn_linker = self.probe_dynamic_linker()
        crt = self.probe_crt_files()
        lib_dirs = self.probe_lib_dirs()

        have_glibc = (
            dyn_linker
            and "crt1" in crt
            and "crti" in crt
            and "crtn" in crt
            and "crtbegin" in crt
            and "crtend" in crt
        )

        if have_glibc:
            return self._glibc_link_cmd(
                obj_paths, output,
                dyn_linker=dyn_linker,  # type: ignore[arg-type]
                crt=crt,
                lib_dirs=lib_dirs,
                extra_libs=extra_libs,
                extra_lib_dirs=extra_lib_dirs,
                shared=shared,
            )

        # Fallback: static newlib-ish layout.
        libc_a = _first_existing([
            "/usr/lib/libc.a",
            "/usr/lib64/libc.a",
            "/usr/x86_64-unknown-elf/lib/libc.a",
            "/usr/local/x86_64-unknown-elf/lib/libc.a",
        ])
        if libc_a:
            libdir = os.path.dirname(libc_a)
            cmd: List[str] = [self.linker, "-o", output]
            cmd += obj_paths
            cmd += ["-L", libdir, "-lc"]
            return cmd

        raise RuntimeError(
            "No usable C runtime found for linking. "
            "Install glibc-dev / libc6-dev, or a newlib toolchain."
        )

    # ------------------------------------------------------------------
    # Runners
    # ------------------------------------------------------------------

    def run_assemble(self, asm_path: str, obj_path: str) -> None:
        """Assemble *asm_path* into *obj_path* using the system assembler."""
        _run_cmd([self.assembler, "-o", obj_path, asm_path], "assemble")

    def run_link(self, cmd: List[str]) -> None:
        """Execute a linker command (as returned by :meth:`build_link_cmd`)."""
        _run_cmd(cmd, "link")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _glibc_link_cmd(
        self,
        obj_paths: List[str],
        output: str,
        *,
        dyn_linker: str,
        crt: Dict[str, str],
        lib_dirs: List[str],
        extra_libs: Optional[List[str]] = None,
        extra_lib_dirs: Optional[List[str]] = None,
        shared: bool = False,
    ) -> List[str]:
        cmd: List[str] = [self.linker, "-o", output]

        if shared:
            cmd.append("-shared")
        else:
            cmd += ["-dynamic-linker", dyn_linker]
            cmd.append(crt["crt1"])

        cmd.append(crt["crti"])
        cmd.append(crt["crtbegin"])
        cmd += obj_paths

        # Library search directories.
        for d in (extra_lib_dirs or []):
            if os.path.isdir(d):
                cmd += ["-L", d]
        for d in lib_dirs:
            cmd += ["-L", d]

        # Default libraries.
        cmd += ["-lc", "-lgcc", "-lgcc_s"]

        # Extra libraries requested by the user (-l flags).
        for lib in (extra_libs or []):
            cmd.append(f"-l{lib}")

        cmd += [crt["crtend"], crt["crtn"]]
        return cmd


# ======================================================================
# Module-level helpers (not part of the public API)
# ======================================================================

def _first_existing(paths: List[str]) -> Optional[str]:
    """Return the first path that exists on disk, or *None*."""
    return next((p for p in paths if os.path.exists(p)), None)


def _probe_gcc_crt() -> tuple:
    """Probe for ``crtbegin.o`` / ``crtend.o`` under GCC lib dirs.

    Returns ``(crtbegin_path, crtend_path)`` or ``(None, None)``.
    """
    prefixes = [
        "/usr/lib/gcc/x86_64-linux-gnu",
        "/usr/lib/gcc/x86_64-pc-linux-gnu",
    ]
    for prefix in prefixes:
        if not os.path.isdir(prefix):
            continue
        try:
            vers = sorted(
                d for d in os.listdir(prefix)
                if os.path.isdir(os.path.join(prefix, d))
            )
        except OSError:
            continue
        for v in reversed(vers):
            cb = os.path.join(prefix, v, "crtbegin.o")
            ce = os.path.join(prefix, v, "crtend.o")
            if os.path.exists(cb) and os.path.exists(ce):
                return cb, ce
    return None, None


def _probe_gcc_lib_dirs() -> List[str]:
    """Return GCC runtime library directories (highest version first)."""
    prefixes = [
        "/usr/lib/gcc/x86_64-linux-gnu",
        "/usr/lib/gcc/x86_64-pc-linux-gnu",
    ]
    dirs: List[str] = []
    for prefix in prefixes:
        if not os.path.isdir(prefix):
            continue
        try:
            vers = sorted(
                d for d in os.listdir(prefix)
                if os.path.isdir(os.path.join(prefix, d))
            )
        except OSError:
            continue
        for v in reversed(vers):
            d = os.path.join(prefix, v)
            if os.path.isdir(d):
                dirs.append(d)
                break
    return dirs


def _run_cmd(cmd: List[str], what: str) -> None:
    """Run *cmd* and raise ``CalledProcessError`` on failure."""
    p = subprocess.run(
        cmd, check=False,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if p.returncode != 0:
        msg = p.stderr.strip() or p.stdout.strip() or "(no output)"
        raise subprocess.CalledProcessError(
            p.returncode, cmd, output=p.stdout, stderr=msg,
        )
