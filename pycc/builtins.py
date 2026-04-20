"""GCC __builtin_* function registry.

Maintains a table of known GCC builtin functions and their C library
equivalents. The compiler recognizes these as valid function calls
(no "implicit declaration" warning) and lowers them to standard C
library calls in the IR.

Design:
- Semantic analysis consults this module to suppress implicit-declaration
  warnings for known builtins.
- IR generation consults this module to rewrite __builtin_foo(args) as
  foo(args) (the C library equivalent).
- Codegen emits a normal `call` to the C library function; the linker
  resolves it via -lm or libc.

To add a new builtin: add an entry to _BUILTIN_TABLE below.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass
class BuiltinInfo:
    """Descriptor for a single __builtin_* function."""
    name: str                # e.g. "__builtin_isnan"
    param_count: int         # number of parameters (-1 = variadic)
    return_type: str         # C return type string, e.g. "int", "double"
    c_library_name: str      # C library equivalent, e.g. "isnan"
    header: str = "<math.h>" # which header provides the C library function


# Registry: __builtin_name -> BuiltinInfo
_BUILTIN_TABLE: Dict[str, BuiltinInfo] = {}


def _register(name: str, params: int, ret: str, c_name: str, header: str = "<math.h>") -> None:
    _BUILTIN_TABLE[name] = BuiltinInfo(
        name=name, param_count=params, return_type=ret,
        c_library_name=c_name, header=header,
    )


# --- Math builtins (mapped to -lm functions) ---
_register("__builtin_isnan",        1, "int",    "isnan")
_register("__builtin_isinf",        1, "int",    "isinf")
_register("__builtin_isinf_sign",   1, "int",    "isinf")
_register("__builtin_isfinite",     1, "int",    "isfinite")
_register("__builtin_signbit",      1, "int",    "signbit")
_register("__builtin_signbitf",     1, "int",    "signbitf")
_register("__builtin_signbitl",     1, "int",    "signbitl")
_register("__builtin_nanf",         1, "float",  "nanf")
_register("__builtin_nan",          1, "double", "nan")
_register("__builtin_huge_val",     0, "double", "HUGE_VAL")
_register("__builtin_huge_valf",    0, "float",  "HUGE_VALF")
_register("__builtin_inff",         0, "float",  "HUGE_VALF")
_register("__builtin_inf",          0, "double", "HUGE_VAL")
_register("__builtin_fabs",         1, "double", "fabs")
_register("__builtin_fabsf",        1, "float",  "fabsf")
_register("__builtin_fabsl",        1, "long double", "fabsl")
_register("__builtin_sqrt",         1, "double", "sqrt")
_register("__builtin_sqrtf",        1, "float",  "sqrtf")
_register("__builtin_floor",        1, "double", "floor")
_register("__builtin_ceil",         1, "double", "ceil")
_register("__builtin_sin",          1, "double", "sin")
_register("__builtin_cos",          1, "double", "cos")
_register("__builtin_log",          1, "double", "log")
_register("__builtin_exp",          1, "double", "exp")
_register("__builtin_pow",          2, "double", "pow")

# --- Utility builtins (mapped to libc) ---
_register("__builtin_memcpy",       3, "void *", "memcpy",  "<string.h>")
_register("__builtin_memset",       3, "void *", "memset",  "<string.h>")
_register("__builtin_memmove",      3, "void *", "memmove", "<string.h>")
_register("__builtin_strlen",       1, "unsigned long", "strlen", "<string.h>")
_register("__builtin_strcmp",       2, "int",    "strcmp",   "<string.h>")
_register("__builtin_abort",        0, "void",   "abort",   "<stdlib.h>")
_register("__builtin_exit",         1, "void",   "exit",    "<stdlib.h>")
_register("__builtin_printf",      -1, "int",    "printf",  "<stdio.h>")


# --- Public API ---

def is_builtin(name: str) -> bool:
    """Return True if *name* is a known GCC __builtin_* function."""
    return name in _BUILTIN_TABLE


def get_builtin(name: str) -> Optional[BuiltinInfo]:
    """Return the BuiltinInfo for *name*, or None."""
    return _BUILTIN_TABLE.get(name)


def get_c_library_name(name: str) -> Optional[str]:
    """Return the C library function name for a builtin, or None."""
    info = _BUILTIN_TABLE.get(name)
    return info.c_library_name if info is not None else None


def get_return_type(name: str) -> Optional[str]:
    """Return the return type string for a builtin, or None."""
    info = _BUILTIN_TABLE.get(name)
    return info.return_type if info is not None else None


def get_all_builtins() -> Dict[str, BuiltinInfo]:
    """Return the full builtin table (read-only)."""
    return dict(_BUILTIN_TABLE)
