"""pycc.target — Target platform type size and alignment information.

Provides TargetInfo, an immutable configuration object that centralizes
all platform-dependent type size and alignment values. Replaces the
hardcoded if/elif chains scattered across ir.py, codegen.py, semantics.py
and types.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from pycc.types import (
    CType, TypeKind, ArrayType, PointerType, StructType,
    IntegerType, FloatType, EnumType, ctype_to_ir_type,
)


def _normalize(name: str) -> str:
    """Strip and collapse whitespace in a type name string."""
    return " ".join(name.strip().split())


_MAX_TYPEDEF_DEPTH = 16


def _resolve_typedef_chain(name: str, typedefs: dict, _depth: int = 0) -> Optional[str]:
    """Resolve a typedef name to its underlying type name string.

    The *typedefs* dict maps ``str -> AST Type`` objects (with ``.base``
    and ``.is_pointer`` attributes).  Chains are followed recursively up
    to ``_MAX_TYPEDEF_DEPTH`` levels to guard against cycles.

    Returns the resolved type name string, or ``None`` if *name* is not
    a typedef or the chain cannot be resolved.
    """
    if _depth >= _MAX_TYPEDEF_DEPTH:
        return None
    td = typedefs.get(name)
    if td is None:
        return None
    # AST Type object: if it's a pointer, the resolved type is a pointer
    if getattr(td, "is_pointer", False):
        return name + " *"  # will match the '*' check in sizeof/alignof
    base = getattr(td, "base", None)
    if base is None:
        return None
    base = _normalize(base)
    if not base:
        return None
    return base


@dataclass(frozen=True)
class TargetInfo:
    """Immutable target platform type size and alignment configuration."""

    _sizes: Dict[str, int]
    _aligns: Dict[str, int]
    pointer_size: int

    # -- String-based queries ------------------------------------------------

    def sizeof(self, type_name: str, *, typedefs=None) -> int:
        """Return byte size for a type name string.

        Lookup order:
        1. Normalize input (strip + collapse whitespace)
        2. If contains '*', return pointer_size
        3. If starts with 'enum ', return enum size
        4. Lookup in _sizes
        5. If not found and typedefs provided, resolve through typedef chain
        6. Fallback to pointer_size (matches existing behaviour)
        """
        n = _normalize(type_name)
        if "*" in n:
            return self.pointer_size
        if n.startswith("enum "):
            return self._sizes.get("enum", self.pointer_size)
        val = self._sizes.get(n)
        if val is not None:
            return val
        if typedefs is not None:
            resolved = _resolve_typedef_chain(n, typedefs)
            if resolved is not None:
                return self.sizeof(resolved, typedefs=typedefs)
        return self.pointer_size

    def alignof(self, type_name: str, *, typedefs=None) -> int:
        """Return alignment requirement for a type name string."""
        n = _normalize(type_name)
        if "*" in n:
            return self.pointer_size
        if n.startswith("enum "):
            return self._aligns.get("enum", self.pointer_size)
        val = self._aligns.get(n)
        if val is not None:
            return val
        if typedefs is not None:
            resolved = _resolve_typedef_chain(n, typedefs)
            if resolved is not None:
                return self.alignof(resolved, typedefs=typedefs)
        return self.pointer_size

    # -- CType-based queries -------------------------------------------------

    def sizeof_ctype(self, ct: CType, layouts=None) -> int:
        """Return byte size for a CType object.

        For struct/union, delegates to layouts dict.
        For arrays, computes element_size * count.
        For scalars and pointers, maps TypeKind to the string-based lookup.
        """
        if ct.kind == TypeKind.VOID:
            return 0

        if ct.kind == TypeKind.POINTER:
            return self.pointer_size

        if ct.kind == TypeKind.ARRAY and isinstance(ct, ArrayType):
            if ct.element is not None and ct.size is not None:
                return self.sizeof_ctype(ct.element, layouts) * ct.size
            return 0

        if ct.kind in (TypeKind.STRUCT, TypeKind.UNION):
            tag = _struct_union_tag(ct)
            if tag and layouts is not None:
                layout = layouts.get(tag)
                if layout is not None:
                    sz = getattr(layout, "size", 0)
                    if sz:
                        return int(sz)
            return 0

        if ct.kind == TypeKind.ENUM:
            return self._sizes.get("enum", 4)

        # Scalar: convert to IR type string and look up
        ir_name = ctype_to_ir_type(ct)
        return self.sizeof(ir_name)

    def alignof_ctype(self, ct: CType, layouts=None) -> int:
        """Return alignment requirement for a CType object."""
        if ct.kind == TypeKind.VOID:
            return 0

        if ct.kind == TypeKind.POINTER:
            return self.pointer_size

        if ct.kind == TypeKind.ARRAY and isinstance(ct, ArrayType):
            if ct.element is not None:
                return self.alignof_ctype(ct.element, layouts)
            return 0

        if ct.kind in (TypeKind.STRUCT, TypeKind.UNION):
            tag = _struct_union_tag(ct)
            if tag and layouts is not None:
                layout = layouts.get(tag)
                if layout is not None:
                    al = getattr(layout, "align", 0)
                    if al:
                        return int(al)
            return 0

        if ct.kind == TypeKind.ENUM:
            return self._aligns.get("enum", 4)

        ir_name = ctype_to_ir_type(ct)
        return self.alignof(ir_name)

    # -- Factory methods -----------------------------------------------------

    @staticmethod
    def lp64() -> TargetInfo:
        """Create a TargetInfo for x86-64 SysV LP64 data model."""
        sizes: Dict[str, int] = {
            "char": 1, "signed char": 1, "unsigned char": 1,
            "short": 2, "short int": 2, "signed short": 2,
            "signed short int": 2, "unsigned short": 2, "unsigned short int": 2,
            "int": 4, "signed int": 4, "unsigned int": 4, "signed": 4,
            "long": 8, "long int": 8, "signed long": 8,
            "signed long int": 8, "unsigned long": 8, "unsigned long int": 8,
            "float": 4, "double": 8, "long double": 16,
            "void": 0,
            "__builtin_va_list": 24,
            "enum": 4,
        }
        aligns: Dict[str, int] = {
            "char": 1, "signed char": 1, "unsigned char": 1,
            "short": 2, "short int": 2, "signed short": 2,
            "signed short int": 2, "unsigned short": 2, "unsigned short int": 2,
            "int": 4, "signed int": 4, "unsigned int": 4, "signed": 4,
            "long": 8, "long int": 8, "signed long": 8,
            "signed long int": 8, "unsigned long": 8, "unsigned long int": 8,
            "float": 4, "double": 8, "long double": 16,
            "void": 0,
            "__builtin_va_list": 8,
            "enum": 4,
        }
        return TargetInfo(_sizes=sizes, _aligns=aligns, pointer_size=8)


def _struct_union_tag(ct: CType) -> Optional[str]:
    """Extract the full 'struct tag' or 'union tag' key from a CType."""
    if isinstance(ct, StructType):
        tag = getattr(ct, "tag", None)
        if tag:
            prefix = "union " if ct.kind == TypeKind.UNION else "struct "
            return prefix + tag
    return None
