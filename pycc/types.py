"""pycc.types — Structured C89 type representation.

Provides CType class hierarchy, type classification helpers,
integer promotion, UAC, and bridge functions to/from ast_nodes.Type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional


class TypeKind(Enum):
    VOID = auto()
    CHAR = auto()
    SHORT = auto()
    INT = auto()
    LONG = auto()
    FLOAT = auto()
    DOUBLE = auto()
    POINTER = auto()
    ARRAY = auto()
    FUNCTION = auto()
    STRUCT = auto()
    UNION = auto()
    ENUM = auto()


@dataclass(frozen=True)
class Qualifiers:
    const: bool = False
    volatile: bool = False


@dataclass
class CType:
    kind: TypeKind
    quals: Qualifiers = field(default_factory=Qualifiers)


@dataclass
class IntegerType(CType):
    is_unsigned: bool = False


@dataclass
class FloatType(CType):
    pass


@dataclass
class PointerType(CType):
    pointee: Optional[CType] = None


@dataclass
class ArrayType(CType):
    element: Optional[CType] = None
    size: Optional[int] = None


@dataclass
class FunctionTypeCType(CType):
    """Named to avoid clash with ast_nodes.FunctionType."""
    return_type: Optional[CType] = None
    param_types: List[CType] = field(default_factory=list)
    is_prototype: bool = True
    is_variadic: bool = False


@dataclass
class StructType(CType):
    tag: Optional[str] = None


@dataclass
class EnumType(CType):
    tag: Optional[str] = None


# -- Type classification helpers ---------------------------------------------

def is_integer(t: CType) -> bool:
    return t.kind in {TypeKind.CHAR, TypeKind.SHORT, TypeKind.INT,
                      TypeKind.LONG, TypeKind.ENUM}

def is_floating(t: CType) -> bool:
    return t.kind in {TypeKind.FLOAT, TypeKind.DOUBLE}

def is_arithmetic(t: CType) -> bool:
    return is_integer(t) or is_floating(t)

def is_scalar(t: CType) -> bool:
    return is_arithmetic(t) or t.kind == TypeKind.POINTER

def is_object(t: CType) -> bool:
    return t.kind not in {TypeKind.FUNCTION, TypeKind.VOID}

def is_function(t: CType) -> bool:
    return t.kind == TypeKind.FUNCTION

def is_incomplete(t: CType) -> bool:
    if t.kind == TypeKind.VOID:
        return True
    if t.kind == TypeKind.ARRAY and isinstance(t, ArrayType) and t.size is None:
        return True
    return False

def is_modifiable_lvalue(t: CType) -> bool:
    if t.quals.const:
        return False
    if t.kind == TypeKind.ARRAY:
        return False
    if is_incomplete(t):
        return False
    return True


# -- Integer promotion & UAC ------------------------------------------------

_INTEGER_RANK = {
    TypeKind.CHAR: 1,
    TypeKind.SHORT: 2,
    TypeKind.INT: 3,
    TypeKind.LONG: 4,
}

def integer_rank(t: CType) -> int:
    return _INTEGER_RANK.get(t.kind, 0)

def type_sizeof(t: CType) -> int:
    """Size in bytes on LP64 (x86-64 SysV)."""
    _SIZES = {
        TypeKind.CHAR: 1, TypeKind.SHORT: 2, TypeKind.INT: 4,
        TypeKind.LONG: 8, TypeKind.FLOAT: 4, TypeKind.DOUBLE: 8,
        TypeKind.POINTER: 8, TypeKind.ENUM: 4,
    }
    if t.kind in _SIZES:
        return _SIZES[t.kind]
    if t.kind == TypeKind.ARRAY and isinstance(t, ArrayType):
        if t.element and t.size is not None:
            return type_sizeof(t.element) * t.size
    return 0

def integer_promote(t: CType) -> CType:
    """C89 integer promotion: narrow types -> int."""
    if not is_integer(t):
        return t
    if t.kind == TypeKind.ENUM:
        return IntegerType(kind=TypeKind.INT, is_unsigned=False)
    if integer_rank(t) < integer_rank(IntegerType(kind=TypeKind.INT)):
        return IntegerType(kind=TypeKind.INT, is_unsigned=False)
    return t

def usual_arithmetic_conversions(a: CType, b: CType) -> CType:
    """C89 usual arithmetic conversions."""
    if a.kind == TypeKind.DOUBLE or b.kind == TypeKind.DOUBLE:
        return FloatType(kind=TypeKind.DOUBLE)
    if a.kind == TypeKind.FLOAT or b.kind == TypeKind.FLOAT:
        return FloatType(kind=TypeKind.FLOAT)
    a, b = integer_promote(a), integer_promote(b)
    a_u = getattr(a, 'is_unsigned', False)
    b_u = getattr(b, 'is_unsigned', False)
    if a.kind == b.kind and a_u == b_u:
        return a
    if a_u == b_u:
        return a if integer_rank(a) >= integer_rank(b) else b
    unsigned_t = a if a_u else b
    signed_t = b if a_u else a
    if integer_rank(unsigned_t) >= integer_rank(signed_t):
        return unsigned_t
    if type_sizeof(signed_t) > type_sizeof(unsigned_t):
        return signed_t
    return IntegerType(kind=signed_t.kind, is_unsigned=True)


# -- Bridge: ast_nodes.Type <-> CType ---------------------------------------

def ast_type_to_ctype(ast_type) -> CType:
    """Convert an ast_nodes.Type (or string) to a CType."""
    if ast_type is None:
        return IntegerType(kind=TypeKind.INT, is_unsigned=False)
    if isinstance(ast_type, str):
        return _str_to_ctype(ast_type)

    base = getattr(ast_type, 'base', '') or ''
    is_ptr = getattr(ast_type, 'is_pointer', False)
    ptr_level = getattr(ast_type, 'pointer_level', 0)
    if ptr_level <= 0 and is_ptr:
        ptr_level = 1
    is_const = getattr(ast_type, 'is_const', False)
    is_volatile = getattr(ast_type, 'is_volatile', False)
    is_unsigned = getattr(ast_type, 'is_unsigned', False)
    is_signed = getattr(ast_type, 'is_signed', False)

    ct = _base_str_to_ctype(base, is_unsigned, is_signed,
                             Qualifiers(const=is_const, volatile=is_volatile))

    if ptr_level > 0:
        pointer_quals_list = getattr(ast_type, 'pointer_quals', []) or []
        for i in range(ptr_level):
            pq = Qualifiers()
            if i < len(pointer_quals_list):
                qs = pointer_quals_list[i]
                pq = Qualifiers(const='const' in qs, volatile='volatile' in qs)
            ct = PointerType(kind=TypeKind.POINTER, quals=pq, pointee=ct)
    return ct


def _base_str_to_ctype(base: str, is_unsigned: bool, is_signed: bool,
                        quals: Qualifiers) -> CType:
    b = ' '.join(base.strip().split())
    if b == 'void':
        return CType(kind=TypeKind.VOID, quals=quals)
    if b in ('char', 'signed char', 'unsigned char'):
        return IntegerType(kind=TypeKind.CHAR, quals=quals,
                           is_unsigned=is_unsigned or b == 'unsigned char')
    if b in ('short', 'short int', 'signed short', 'signed short int',
             'unsigned short', 'unsigned short int'):
        return IntegerType(kind=TypeKind.SHORT, quals=quals,
                           is_unsigned=is_unsigned or 'unsigned' in b)
    if b in ('long', 'long int', 'signed long', 'signed long int',
             'unsigned long', 'unsigned long int'):
        return IntegerType(kind=TypeKind.LONG, quals=quals,
                           is_unsigned=is_unsigned or 'unsigned' in b)
    if b in ('int', 'signed int', 'unsigned int', 'signed'):
        return IntegerType(kind=TypeKind.INT, quals=quals,
                           is_unsigned=is_unsigned or b == 'unsigned int')
    if b == 'float':
        return FloatType(kind=TypeKind.FLOAT, quals=quals)
    if b == 'double':
        return FloatType(kind=TypeKind.DOUBLE, quals=quals)
    if b.startswith('struct '):
        return StructType(kind=TypeKind.STRUCT, quals=quals, tag=b[7:].strip() or None)
    if b.startswith('union '):
        return StructType(kind=TypeKind.UNION, quals=quals, tag=b[6:].strip() or None)
    if b.startswith('enum '):
        return EnumType(kind=TypeKind.ENUM, quals=quals, tag=b[5:].strip() or None)
    return IntegerType(kind=TypeKind.INT, quals=quals, is_unsigned=is_unsigned)


def _str_to_ctype(s: str) -> CType:
    """Parse a type string like 'unsigned long *' into CType."""
    s = s.strip()
    ptr_level = 0
    while s.endswith('*'):
        ptr_level += 1
        s = s[:-1].strip()
    is_const = is_volatile = is_unsigned = is_signed = False
    filtered = []
    for tok in s.split():
        if tok == 'const':      is_const = True
        elif tok == 'volatile': is_volatile = True
        elif tok == 'unsigned': is_unsigned = True
        elif tok == 'signed':   is_signed = True
        else:                   filtered.append(tok)
    base = ' '.join(filtered) if filtered else 'int'
    ct = _base_str_to_ctype(base, is_unsigned, is_signed,
                             Qualifiers(const=is_const, volatile=is_volatile))
    for _ in range(ptr_level):
        ct = PointerType(kind=TypeKind.POINTER, pointee=ct)
    return ct


def ctype_to_ir_type(ct: CType) -> str:
    """Convert CType to a type string for IR/codegen compatibility."""
    if ct.kind == TypeKind.VOID:
        return 'void'
    if ct.kind == TypeKind.POINTER:
        if isinstance(ct, PointerType) and ct.pointee is not None:
            return ctype_to_ir_type(ct.pointee) + ' *'
        return 'void *'
    if ct.kind in (TypeKind.CHAR, TypeKind.SHORT, TypeKind.INT, TypeKind.LONG):
        prefix = 'unsigned ' if getattr(ct, 'is_unsigned', False) else ''
        names = {TypeKind.CHAR: 'char', TypeKind.SHORT: 'short',
                 TypeKind.INT: 'int', TypeKind.LONG: 'long'}
        return prefix + names[ct.kind]
    if ct.kind == TypeKind.FLOAT:
        return 'float'
    if ct.kind == TypeKind.DOUBLE:
        return 'double'
    if ct.kind == TypeKind.ENUM:
        tag = getattr(ct, 'tag', None)
        return f'enum {tag}' if tag else 'int'
    if ct.kind == TypeKind.STRUCT:
        tag = getattr(ct, 'tag', None)
        return f'struct {tag}' if tag else 'struct'
    if ct.kind == TypeKind.UNION:
        tag = getattr(ct, 'tag', None)
        return f'union {tag}' if tag else 'union'
    if ct.kind == TypeKind.ARRAY and isinstance(ct, ArrayType) and ct.element:
        return ctype_to_ir_type(ct.element)
    return 'int'
