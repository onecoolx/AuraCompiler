"""Property-based tests for Parser array detection.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**

Property 2: For any valid C array declaration (local, global, struct member,
1D and multi-dimensional), parsing produces a Declaration whose type.is_array
is True, and type.array_element_type's base matches the declared element type.

Property 3: For any valid C pointer declaration (without array dimensions),
parsing produces a Declaration whose type.is_array is False.
"""

from hypothesis import given, settings, strategies as st

from pycc.ast_nodes import Declaration, FunctionDecl, StructDecl, Type
from pycc.lexer import Lexer
from pycc.parser import Parser


# --- Strategies ---

# Map from C source type specifier to the parser's normalized base name
BASE_TYPE_MAP = {
    "int": "int",
    "char": "char",
    "long": "long int",
    "short": "short int",
    "float": "float",
    "double": "double",
    "unsigned int": "unsigned int",
    "unsigned long": "unsigned long",
}

base_type_keys = st.sampled_from(list(BASE_TYPE_MAP.keys()))

# Array dimension sizes: 1-100
dim_size = st.integers(min_value=1, max_value=100)

# 1 to 3 dimensions
array_dims = st.lists(dim_size, min_size=1, max_size=3)

# Pointer levels 1-3
pointer_level = st.integers(min_value=1, max_value=3)

# Simple identifier names
var_names = st.sampled_from(["arr", "buf", "data", "matrix", "vals", "items"])


@st.composite
def global_array_decl(draw):
    """Generate a global array declaration string and expected base type."""
    src_base = draw(base_type_keys)
    expected_base = BASE_TYPE_MAP[src_base]
    name = draw(var_names)
    dims = draw(array_dims)
    dims_str = "".join(f"[{d}]" for d in dims)
    code = f"{src_base} {name}{dims_str};"
    return code, expected_base, name, dims


@st.composite
def local_array_decl(draw):
    """Generate a local array declaration inside a function."""
    src_base = draw(base_type_keys)
    expected_base = BASE_TYPE_MAP[src_base]
    name = draw(var_names)
    dims = draw(array_dims)
    dims_str = "".join(f"[{d}]" for d in dims)
    code = f"void test_fn(void) {{ {src_base} {name}{dims_str}; }}"
    return code, expected_base, name, dims


@st.composite
def struct_member_array_decl(draw):
    """Generate a struct with an array member."""
    src_base = draw(base_type_keys)
    expected_base = BASE_TYPE_MAP[src_base]
    name = draw(var_names)
    dims = draw(array_dims)
    dims_str = "".join(f"[{d}]" for d in dims)
    code = f"struct TestStruct {{ {src_base} {name}{dims_str}; }};"
    return code, expected_base, name, dims


@st.composite
def global_pointer_decl(draw):
    """Generate a global pointer declaration string."""
    src_base = draw(base_type_keys)
    expected_base = BASE_TYPE_MAP[src_base]
    name = draw(var_names)
    level = draw(pointer_level)
    stars = "*" * level
    code = f"{src_base} {stars}{name};"
    return code, expected_base, name, level


@st.composite
def local_pointer_decl(draw):
    """Generate a local pointer declaration inside a function."""
    src_base = draw(base_type_keys)
    expected_base = BASE_TYPE_MAP[src_base]
    name = draw(var_names)
    level = draw(pointer_level)
    stars = "*" * level
    code = f"void test_fn(void) {{ {src_base} {stars}{name}; }}"
    return code, expected_base, name, level


# --- Helpers ---

def _parse_global_decl(code: str, name: str) -> Declaration:
    """Parse code and return the Declaration with given name."""
    tokens = Lexer(code).tokenize()
    ast = Parser(tokens).parse()
    for decl in ast.declarations:
        if isinstance(decl, Declaration) and decl.name == name:
            return decl
    raise AssertionError(f"No Declaration named '{name}' found")


def _parse_local_decl(code: str, name: str) -> Declaration:
    """Parse code and return a local Declaration with given name."""
    tokens = Lexer(code).tokenize()
    ast = Parser(tokens).parse()
    for decl in ast.declarations:
        if isinstance(decl, FunctionDecl):
            for stmt in decl.body.statements:
                if isinstance(stmt, Declaration) and stmt.name == name:
                    return stmt
                if isinstance(stmt, list):
                    for d in stmt:
                        if isinstance(d, Declaration) and d.name == name:
                            return d
    raise AssertionError(f"No local Declaration named '{name}' found")


def _parse_struct_member(code: str, name: str) -> Declaration:
    """Parse code and return the struct member Declaration with given name."""
    tokens = Lexer(code).tokenize()
    ast = Parser(tokens).parse()
    for decl in ast.declarations:
        if isinstance(decl, StructDecl):
            for member in decl.members:
                if member.name == name:
                    return member
    raise AssertionError(f"No struct member named '{name}' found")


# --- Property Tests ---

class TestProperty2ParserArrayDetection:
    """Property 2: Parser 对数组声明设置 is_array

    **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**
    """

    @settings(max_examples=100)
    @given(data=global_array_decl())
    def test_global_array_is_array_true(self, data):
        """Global array declarations have type.is_array=True."""
        code, base, name, dims = data
        decl = _parse_global_decl(code, name)
        assert decl.type.is_array is True
        assert decl.type.array_element_type is not None
        # Leaf element type base should match declared base
        elem = decl.type.array_element_type
        while elem.is_array:
            elem = elem.array_element_type
        assert elem.base == base

    @settings(max_examples=100)
    @given(data=global_array_decl())
    def test_global_array_dimensions_match(self, data):
        """Global array declarations have correct array_dimensions."""
        code, base, name, dims = data
        decl = _parse_global_decl(code, name)
        assert decl.type.array_dimensions == dims

    @settings(max_examples=100)
    @given(data=local_array_decl())
    def test_local_array_is_array_true(self, data):
        """Local array declarations have type.is_array=True."""
        code, base, name, dims = data
        decl = _parse_local_decl(code, name)
        assert decl.type.is_array is True
        assert decl.type.array_element_type is not None
        elem = decl.type.array_element_type
        while elem.is_array:
            elem = elem.array_element_type
        assert elem.base == base

    @settings(max_examples=100)
    @given(data=local_array_decl())
    def test_local_array_dimensions_match(self, data):
        """Local array declarations have correct array_dimensions."""
        code, base, name, dims = data
        decl = _parse_local_decl(code, name)
        assert decl.type.array_dimensions == dims

    @settings(max_examples=100)
    @given(data=struct_member_array_decl())
    def test_struct_member_array_is_array_true(self, data):
        """Struct member array declarations have type.is_array=True."""
        code, base, name, dims = data
        member = _parse_struct_member(code, name)
        assert member.type.is_array is True
        assert member.type.array_element_type is not None
        elem = member.type.array_element_type
        while elem.is_array:
            elem = elem.array_element_type
        assert elem.base == base

    @settings(max_examples=100)
    @given(data=struct_member_array_decl())
    def test_struct_member_array_dimensions_match(self, data):
        """Struct member array declarations have correct array_dimensions."""
        code, base, name, dims = data
        member = _parse_struct_member(code, name)
        assert member.type.array_dimensions == dims


class TestProperty3ParserPointerNotArray:
    """Property 3: Parser 对指针声明不设置 is_array

    **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**
    """

    @settings(max_examples=100)
    @given(data=global_pointer_decl())
    def test_global_pointer_is_not_array(self, data):
        """Global pointer declarations have type.is_array=False."""
        code, base, name, level = data
        decl = _parse_global_decl(code, name)
        assert decl.type.is_array is False
        assert decl.type.is_pointer is True
        assert decl.type.pointer_level == level

    @settings(max_examples=100)
    @given(data=local_pointer_decl())
    def test_local_pointer_is_not_array(self, data):
        """Local pointer declarations have type.is_array=False."""
        code, base, name, level = data
        decl = _parse_local_decl(code, name)
        assert decl.type.is_array is False
        assert decl.type.is_pointer is True
        assert decl.type.pointer_level == level
