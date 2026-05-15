"""pycc.types — Structured C89 type representation.

Provides CType class hierarchy, type classification helpers,
integer promotion, UAC, and bridge functions to/from ast_nodes.Type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Set


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
    # Lazy import to avoid circular dependency (target.py imports from types.py)
    global _DEFAULT_TARGET
    if _DEFAULT_TARGET is None:
        from pycc.target import TargetInfo
        _DEFAULT_TARGET = TargetInfo.lp64()
    return _DEFAULT_TARGET.sizeof_ctype(t)


# Module-level default TargetInfo instance (lazily initialized)
_DEFAULT_TARGET = None

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


def ctype_to_ast_type(ct: CType):
    """Convert a CType back to an ast_nodes.Type for the _expr_type() compatibility layer.

    Handles IntegerType, FloatType, PointerType, ArrayType, StructType, EnumType.
    Returns an ast_nodes.Type instance with appropriate fields set.
    """
    from pycc.ast_nodes import Type as ASTType

    if ct is None:
        return None

    # --- PointerType: unwrap pointer chain to find base and pointer_level ---
    if isinstance(ct, PointerType):
        # Walk the pointer chain to determine depth and base type
        ptr_level = 0
        pointer_quals_list = []
        inner = ct
        while isinstance(inner, PointerType):
            ptr_level += 1
            # Collect qualifiers for this pointer level
            pq = set()
            if inner.quals.const:
                pq.add('const')
            if inner.quals.volatile:
                pq.add('volatile')
            pointer_quals_list.append(pq)
            inner = inner.pointee if inner.pointee is not None else CType(kind=TypeKind.VOID)

        # Convert the base (non-pointer) type
        base_ast = ctype_to_ast_type(inner)
        if base_ast is None:
            base_ast = ASTType(line=0, column=0, base='void')

        # Build the result with pointer wrapping
        base_ast.is_pointer = True
        base_ast.pointer_level = ptr_level
        base_ast.pointer_quals = pointer_quals_list
        return base_ast

    # --- ArrayType ---
    if isinstance(ct, ArrayType):
        elem_ast = ctype_to_ast_type(ct.element) if ct.element else ASTType(line=0, column=0, base='int')
        dims = [ct.size] if ct.size is not None else [None]
        return ASTType(
            line=0, column=0,
            base=elem_ast.base if elem_ast else 'int',
            is_array=True,
            array_element_type=elem_ast,
            array_dimensions=dims,
            is_unsigned=getattr(elem_ast, 'is_unsigned', False),
            is_const=ct.quals.const,
            is_volatile=ct.quals.volatile,
        )

    # --- IntegerType ---
    if isinstance(ct, IntegerType):
        names = {
            TypeKind.CHAR: 'char',
            TypeKind.SHORT: 'short',
            TypeKind.INT: 'int',
            TypeKind.LONG: 'long',
        }
        base = names.get(ct.kind, 'int')
        return ASTType(
            line=0, column=0,
            base=base,
            is_unsigned=ct.is_unsigned,
            is_const=ct.quals.const,
            is_volatile=ct.quals.volatile,
        )

    # --- FloatType ---
    if isinstance(ct, FloatType):
        base = 'float' if ct.kind == TypeKind.FLOAT else 'double'
        return ASTType(
            line=0, column=0,
            base=base,
            is_const=ct.quals.const,
            is_volatile=ct.quals.volatile,
        )

    # --- StructType (covers both struct and union) ---
    if isinstance(ct, StructType):
        prefix = 'union' if ct.kind == TypeKind.UNION else 'struct'
        tag = ct.tag or ''
        base = f'{prefix} {tag}' if tag else prefix
        return ASTType(
            line=0, column=0,
            base=base,
            is_const=ct.quals.const,
            is_volatile=ct.quals.volatile,
        )

    # --- EnumType ---
    if isinstance(ct, EnumType):
        tag = ct.tag or ''
        base = f'enum {tag}' if tag else 'int'
        return ASTType(
            line=0, column=0,
            base=base,
            is_const=ct.quals.const,
            is_volatile=ct.quals.volatile,
        )

    # --- FunctionTypeCType ---
    if isinstance(ct, FunctionTypeCType):
        # Function types in expression context should have been decayed to
        # pointer-to-function. If we reach here, represent as a void base
        # with function metadata (return type).
        ret_ast = ctype_to_ast_type(ct.return_type) if ct.return_type else ASTType(line=0, column=0, base='int')
        return ASTType(
            line=0, column=0,
            base=ret_ast.base if ret_ast else 'int',
            fn_param_count=len(ct.param_types) if ct.param_types else None,
            fn_return_type=ret_ast,
        )

    # --- VoidType ---
    if ct.kind == TypeKind.VOID:
        return ASTType(
            line=0, column=0,
            base='void',
            is_const=ct.quals.const,
            is_volatile=ct.quals.volatile,
        )

    # Fallback: treat as int
    return ASTType(line=0, column=0, base='int')


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


# -- Standalone typedef resolution -------------------------------------------

def resolve_typedefs(ct: CType, sema_ctx, _seen: Optional[Set[str]] = None) -> CType:
    """Recursively resolve typedef references in a CType to the underlying concrete type (standalone version).

    Resolution strategy:
    - StructType/EnumType: check if tag is a typedef name, resolve to underlying type
    - PointerType: recursively resolve pointee
    - ArrayType: recursively resolve element
    - Others: return as-is
    Uses a seen set to prevent circular typedef references.
    """
    if sema_ctx is None:
        return ct
    if _seen is None:
        _seen = set()

    # StructType whose tag might be a typedef name
    if isinstance(ct, StructType) and ct.tag is not None:
        resolved = _resolve_typedef_name(ct.tag, sema_ctx, _seen)
        if resolved is not None:
            if ct.quals.const or ct.quals.volatile:
                resolved = _merge_quals(resolved, ct.quals)
            return resolved

    # EnumType whose tag might be a typedef name
    if isinstance(ct, EnumType) and ct.tag is not None:
        resolved = _resolve_typedef_name(ct.tag, sema_ctx, _seen)
        if resolved is not None:
            if ct.quals.const or ct.quals.volatile:
                resolved = _merge_quals(resolved, ct.quals)
            return resolved

    # PointerType: recursively resolve pointee
    if isinstance(ct, PointerType) and ct.pointee is not None:
        resolved_pointee = resolve_typedefs(ct.pointee, sema_ctx, _seen)
        if resolved_pointee is not ct.pointee:
            return PointerType(
                kind=TypeKind.POINTER,
                quals=ct.quals,
                pointee=resolved_pointee,
            )
        return ct

    # ArrayType: recursively resolve element
    if isinstance(ct, ArrayType) and ct.element is not None:
        resolved_elem = resolve_typedefs(ct.element, sema_ctx, _seen)
        if resolved_elem is not ct.element:
            return ArrayType(
                kind=TypeKind.ARRAY,
                quals=ct.quals,
                element=resolved_elem,
                size=ct.size,
            )
        return ct

    return ct


def _resolve_typedef_name(name: str, sema_ctx, seen: Set[str]) -> Optional[CType]:
    """Recursively resolve a typedef name to CType via sema_ctx.typedefs.

    Returns None if name is not a typedef name.
    """
    typedefs = getattr(sema_ctx, 'typedefs', None)
    if typedefs is None:
        return None
    if name in seen:
        return None  # Circular typedef detected, stop resolution
    seen.add(name)

    ast_type = typedefs.get(name)
    if ast_type is None:
        return None

    ct = ast_type_to_ctype(ast_type)
    return resolve_typedefs(ct, sema_ctx, seen)


def _merge_quals(ctype: CType, quals: Qualifiers) -> CType:
    """Return a copy of ctype with merged qualifiers."""
    merged = Qualifiers(
        const=ctype.quals.const or quals.const,
        volatile=ctype.quals.volatile or quals.volatile,
    )
    if merged == ctype.quals:
        return ctype
    import copy
    result = copy.copy(ctype)
    object.__setattr__(result, 'quals', merged)
    return result


def ast_type_to_ctype_resolved(ast_type, sema_ctx=None) -> CType:
    """Convert an AST Type node to a fully resolved CType.

    Unlike ast_type_to_ctype, this recursively resolves typedef names.
    When the base name is a typedef (e.g. MyType -> long), the typedef
    is resolved before CType construction so that pointer/array wrappers
    are built around the correct underlying type.
    """
    if sema_ctx is not None and ast_type is not None and not isinstance(ast_type, str):
        base = getattr(ast_type, 'base', '') or ''
        typedefs = getattr(sema_ctx, 'typedefs', None)
        if (typedefs and base
                and base not in _KNOWN_BASE_NAMES
                and not base.startswith('struct ')
                and not base.startswith('union ')
                and not base.startswith('enum ')):
            td = typedefs.get(base)
            if td is not None:
                # Resolve the typedef base, preserving pointer/array wrapping
                # from the original AST type node.
                resolved_base = ast_type_to_ctype_resolved(td, sema_ctx)
                # If the typedef itself is an array typedef (e.g.
                # typedef int arr_t[23]), wrap in ArrayType from innermost
                # to outermost dimension.
                td_dims = getattr(td, 'array_dims', None)
                if td_dims:
                    for dim in reversed(td_dims):
                        resolved_base = ArrayType(
                            kind=TypeKind.ARRAY,
                            element=resolved_base,
                            size=int(dim) if dim is not None else None,
                        )
                # Re-apply pointer levels from the original declaration.
                is_ptr = getattr(ast_type, 'is_pointer', False)
                ptr_level = getattr(ast_type, 'pointer_level', 0)
                if ptr_level <= 0 and is_ptr:
                    ptr_level = 1
                pointer_quals_list = getattr(ast_type, 'pointer_quals', []) or []
                for i in range(ptr_level):
                    pq = Qualifiers()
                    if i < len(pointer_quals_list):
                        qs = pointer_quals_list[i]
                        pq = Qualifiers(const='const' in qs,
                                        volatile='volatile' in qs)
                    resolved_base = PointerType(kind=TypeKind.POINTER,
                                                quals=pq,
                                                pointee=resolved_base)
                return resolved_base
    ct = ast_type_to_ctype(ast_type)
    if sema_ctx is not None:
        ct = resolve_typedefs(ct, sema_ctx)
    return ct


# Set of known base type names that should NOT be treated as typedefs.
_KNOWN_BASE_NAMES = frozenset({
    'void', 'char', 'signed char', 'unsigned char',
    'short', 'short int', 'signed short', 'signed short int',
    'unsigned short', 'unsigned short int',
    'int', 'signed int', 'unsigned int', 'signed',
    'long', 'long int', 'signed long', 'signed long int',
    'unsigned long', 'unsigned long int',
    'float', 'double', 'long double',
})


# -- TypedSymbolTable --------------------------------------------------------

class TypedSymbolTable:
    """Centralized symbol-to-CType mapping with scope support.

    All typedefs are resolved to the underlying concrete type at insertion time.
    """

    def __init__(self, sema_ctx=None):
        self._sema_ctx = sema_ctx
        self._globals: Dict[str, CType] = {}
        self._scope_stack: List[Dict[str, CType]] = []
        # Flat archive of all function-local symbols across all scopes.
        # Populated by pop_scope() so that codegen can look up local symbols
        # after IR generation has finished (scopes are popped at function end).
        self._locals: Dict[str, CType] = {}
        # Per-function archive: func_name -> {symbol: CType}.
        # Populated by pop_scope(func_name=...) during IR generation.
        # Codegen calls activate_function() to restore the correct locals.
        self._func_locals: Dict[str, Dict[str, CType]] = {}
        # Flag: True after activate_function() is called, so insert() knows
        # to write into _locals (codegen runtime) rather than _globals.
        self._func_active: bool = False

    def push_scope(self) -> None:
        """Enter a new function scope."""
        self._scope_stack.append({})

    def pop_scope(self, func_name: str = None) -> None:
        """Leave the current function scope.

        All symbols from the popped scope are archived. If func_name is
        provided, the scope is stored in a per-function archive so codegen
        can restore it when processing that function's IR.
        """
        if self._scope_stack:
            popped = self._scope_stack.pop()
            if func_name is not None:
                self._func_locals[func_name] = dict(popped)
            # Also update _locals as a convenience for single-function lookups.
            self._locals = dict(popped)

    def activate_function(self, func_name: str) -> None:
        """Restore the archived locals for a specific function.

        Called by codegen when it begins processing a function's IR.
        """
        self._locals = self._func_locals.get(func_name, {})
        self._func_active = True

    def insert(self, name: str, ctype: CType) -> None:
        """Insert a symbol and its resolved CType.

        If inside a function scope, inserts into the current scope;
        otherwise inserts into the active locals (if any) or global scope.
        Typedefs are resolved to the underlying concrete type at insertion time.
        """
        resolved = self._resolve_typedef(ctype)
        if self._scope_stack:
            self._scope_stack[-1][name] = resolved
        elif self._func_active:
            # After activate_function(), insert into locals so codegen
            # runtime registrations override IR-generator archived types.
            self._locals[name] = resolved
        else:
            self._globals[name] = resolved

    def lookup(self, name: str) -> Optional[CType]:
        """Look up the CType for a symbol.

        Search order: active scopes (innermost first) → archived locals → globals.
        Returns None if not found.
        """
        for scope in reversed(self._scope_stack):
            if name in scope:
                return scope[name]
        if name in self._locals:
            return self._locals[name]
        return self._globals.get(name)

    def _resolve_typedef(self, ctype: CType, _seen: Optional[Set[str]] = None) -> CType:
        """Recursively resolve typedef references in a CType to the underlying concrete type.

        Resolution strategy:
        - StructType/EnumType: check if tag is a typedef name, resolve to underlying type
        - PointerType: recursively resolve pointee
        - ArrayType: recursively resolve element
        - Others: return as-is
        Uses a seen set to prevent circular typedef references.
        """
        if self._sema_ctx is None:
            return ctype
        if _seen is None:
            _seen = set()

        # StructType whose tag might be a typedef name
        if isinstance(ctype, StructType) and ctype.tag is not None:
            resolved = self._resolve_typedef_name(ctype.tag, _seen)
            if resolved is not None:
                # Preserve qualifiers from the original ctype
                if ctype.quals.const or ctype.quals.volatile:
                    resolved = self._with_quals(resolved, ctype.quals)
                return resolved

        # EnumType whose tag might be a typedef name
        if isinstance(ctype, EnumType) and ctype.tag is not None:
            resolved = self._resolve_typedef_name(ctype.tag, _seen)
            if resolved is not None:
                if ctype.quals.const or ctype.quals.volatile:
                    resolved = self._with_quals(resolved, ctype.quals)
                return resolved

        # PointerType: recursively resolve pointee
        if isinstance(ctype, PointerType) and ctype.pointee is not None:
            resolved_pointee = self._resolve_typedef(ctype.pointee, _seen)
            if resolved_pointee is not ctype.pointee:
                return PointerType(
                    kind=TypeKind.POINTER,
                    quals=ctype.quals,
                    pointee=resolved_pointee,
                )
            return ctype

        # ArrayType: recursively resolve element
        if isinstance(ctype, ArrayType) and ctype.element is not None:
            resolved_elem = self._resolve_typedef(ctype.element, _seen)
            if resolved_elem is not ctype.element:
                return ArrayType(
                    kind=TypeKind.ARRAY,
                    quals=ctype.quals,
                    element=resolved_elem,
                    size=ctype.size,
                )
            return ctype

        return ctype

    def _resolve_typedef_name(self, name: str, seen: Set[str]) -> Optional[CType]:
        """Recursively resolve a typedef name to CType via SemanticContext.typedefs.

        Returns None if name is not a typedef name.
        """
        typedefs = getattr(self._sema_ctx, 'typedefs', None)
        if typedefs is None:
            return None

        if name in seen:
            return None  # Circular typedef detected, stop resolution
        seen.add(name)

        ast_type = typedefs.get(name)
        if ast_type is None:
            return None

        # Convert AST Type to CType via the existing bridge
        ct = ast_type_to_ctype(ast_type)
        # Recursively resolve the result (it might itself contain typedefs)
        return self._resolve_typedef(ct, seen)

    @staticmethod
    def _with_quals(ctype: CType, quals: Qualifiers) -> CType:
        """Return a copy of ctype with merged qualifiers."""
        merged = Qualifiers(
            const=ctype.quals.const or quals.const,
            volatile=ctype.quals.volatile or quals.volatile,
        )
        if merged == ctype.quals:
            return ctype
        # Create a shallow copy with updated quals.
        # We need to handle each subclass since dataclasses don't have
        # a generic copy-with method.
        import copy
        result = copy.copy(ctype)
        object.__setattr__(result, 'quals', merged)
        return result
