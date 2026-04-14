"""Property-based tests for parser abstract declarator support.

**Validates: Requirements 1.1, 1.2, 1.3, 1.5**

Uses Hypothesis to verify that the parser correctly handles unnamed parameters
in function prototypes, including plain types with pointer levels, unnamed
function pointers, and mixed named/unnamed parameter lists.
"""
from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from pycc.lexer import Lexer
from pycc.parser import Parser
from pycc.ast_nodes import FunctionDecl, Declaration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_proto(code: str) -> FunctionDecl:
    """Parse a C function prototype and return the FunctionDecl AST node."""
    tokens = Lexer(code).tokenize()
    prog = Parser(tokens).parse()
    for decl in prog.declarations:
        if isinstance(decl, FunctionDecl):
            return decl
    raise AssertionError(f"No FunctionDecl found in: {code!r}")


# ---------------------------------------------------------------------------
# Strategies (smart generators)
# ---------------------------------------------------------------------------

# Valid C89 base type specifiers (no pointers, no qualifiers).
_C89_BASE_TYPES = [
    "int", "char", "short", "long", "float", "double", "void",
    "unsigned int", "unsigned char", "unsigned short", "unsigned long",
    "signed int", "signed char", "signed short", "signed long",
]

_base_type = st.sampled_from(_C89_BASE_TYPES)

# Pointer level: 0 to 3 stars.
_pointer_level = st.integers(min_value=0, max_value=3)

# Simple C identifier names for named parameters.
_param_name = st.sampled_from([
    "a", "b", "c", "x", "y", "z", "p", "q", "n", "m",
    "arg", "val", "ptr", "buf", "len", "idx", "cnt", "ret",
])

# Return types for function prototypes (subset that works well).
_return_type = st.sampled_from(["void", "int", "char", "long", "double"])

# Function name.
_func_name = st.sampled_from(["f", "g", "h", "func", "test_fn"])


def _type_with_stars(base: str, stars: int) -> str:
    """Build a type string like 'int **'."""
    return base + " " + "* " * stars if stars > 0 else base


# Strategy for a single unnamed parameter (type + optional pointer stars).
@st.composite
def _unnamed_param(draw):
    """Generate an unnamed parameter string and its expected properties."""
    base = draw(_base_type)
    stars = draw(_pointer_level)
    # void with 0 stars is only valid as sole parameter `(void)` meaning no params,
    # so avoid it as a regular unnamed param.
    if base == "void" and stars == 0:
        stars = 1
    param_str = _type_with_stars(base, stars)
    return param_str, base, stars


# Strategy for function pointer return types (simple types only).
_fp_return_type = st.sampled_from(["int", "char", "void", "long", "double"])

# Strategy for function pointer parameter count.
_fp_param_count = st.integers(min_value=0, max_value=4)

# Strategy for function pointer parameter types (simple).
_fp_inner_type = st.sampled_from(["int", "char", "long", "double", "void *"])


# ---------------------------------------------------------------------------
# Property 1: 未命名参数产生 name=None
# Feature: parser-semantics-hardening, Property 1: unnamed params produce name=None
# ---------------------------------------------------------------------------

class TestUnnamedParamNameNone:
    """Property 1: 未命名参数产生 name=None

    For any valid C89 type specifier (with any pointer level), when parsed
    as an unnamed parameter in a function prototype, the resulting Declaration
    node's name field should be None, and is_pointer should correctly reflect
    whether any * was present.

    **Validates: Requirements 1.1, 1.5**
    """

    @given(
        ret=_return_type,
        fname=_func_name,
        param=_unnamed_param(),
    )
    @settings(max_examples=200, deadline=None)
    def test_unnamed_param_has_none_name(self, ret: str, fname: str, param):
        """Unnamed parameter Declaration has name=None.

        **Validates: Requirements 1.1, 1.5**
        """
        param_str, base, stars = param
        code = f"{ret} {fname}({param_str});"
        fd = _parse_proto(code)

        assert len(fd.parameters) == 1, (
            f"Expected 1 parameter, got {len(fd.parameters)}.\n"
            f"Code: {code!r}"
        )
        p = fd.parameters[0]
        assert p.name is None, (
            f"Expected name=None for unnamed param, got {p.name!r}.\n"
            f"Code: {code!r}"
        )

        # Verify pointer status matches the number of stars.
        if stars > 0:
            assert p.type.is_pointer, (
                f"Expected is_pointer=True for {stars} star(s), got False.\n"
                f"Code: {code!r}"
            )
        else:
            assert not p.type.is_pointer, (
                f"Expected is_pointer=False for 0 stars, got True.\n"
                f"Code: {code!r}"
            )

    @given(
        ret=_return_type,
        fname=_func_name,
        base=_base_type,
        stars=st.integers(min_value=1, max_value=3),
    )
    @settings(max_examples=100, deadline=None)
    def test_unnamed_pointer_param_is_pointer(self, ret: str, fname: str, base: str, stars: int):
        """Unnamed pointer parameter has is_pointer=True.

        **Validates: Requirements 1.5**
        """
        param_str = _type_with_stars(base, stars)
        code = f"{ret} {fname}({param_str});"
        fd = _parse_proto(code)

        assert len(fd.parameters) == 1
        p = fd.parameters[0]
        assert p.name is None
        assert p.type.is_pointer, (
            f"Expected is_pointer=True for pointer param '{param_str}'.\n"
            f"Code: {code!r}"
        )


# ---------------------------------------------------------------------------
# Property 2: 未命名函数指针参数正确解析
# Feature: parser-semantics-hardening, Property 2: unnamed function pointer params
# ---------------------------------------------------------------------------

class TestUnnamedFunctionPointerParam:
    """Property 2: 未命名函数指针参数正确解析

    For any valid function pointer signature ret (*)(param_types...),
    when parsed as an unnamed parameter, the resulting Declaration should
    have name=None and its type should be marked as a function pointer.

    **Validates: Requirements 1.2**
    """

    @given(
        outer_ret=_return_type,
        fname=_func_name,
        fp_ret=_fp_return_type,
        fp_param_count=_fp_param_count,
        fp_params=st.lists(_fp_inner_type, min_size=0, max_size=4),
    )
    @settings(max_examples=200, deadline=None)
    def test_unnamed_fnptr_has_none_name_and_is_pointer(
        self, outer_ret: str, fname: str, fp_ret: str,
        fp_param_count: int, fp_params: list,
    ):
        """Unnamed function pointer parameter has name=None and is_pointer=True.

        **Validates: Requirements 1.2**
        """
        # Use the actual drawn list length, not fp_param_count
        actual_params = fp_params[:fp_param_count] if fp_param_count < len(fp_params) else fp_params
        # Avoid void as a non-pointer param in the inner list (void alone means no params)
        actual_params = [p for p in actual_params if p != "void"]

        if actual_params:
            inner_params_str = ", ".join(actual_params)
        else:
            inner_params_str = "void"

        code = f"{outer_ret} {fname}({fp_ret} (*)({inner_params_str}));"
        fd = _parse_proto(code)

        assert len(fd.parameters) == 1, (
            f"Expected 1 parameter, got {len(fd.parameters)}.\n"
            f"Code: {code!r}"
        )
        p = fd.parameters[0]
        assert p.name is None, (
            f"Expected name=None for unnamed fnptr param, got {p.name!r}.\n"
            f"Code: {code!r}"
        )
        assert p.type.is_pointer, (
            f"Expected is_pointer=True for function pointer param.\n"
            f"Code: {code!r}"
        )
        # Function pointer should have fn_param_count set
        assert p.type.fn_param_count is not None, (
            f"Expected fn_param_count to be set for function pointer param.\n"
            f"Code: {code!r}"
        )

        # Verify fn_param_count matches the actual number of non-void params
        if inner_params_str == "void":
            expected_count = 0
        else:
            expected_count = len(actual_params)
        assert p.type.fn_param_count == expected_count, (
            f"Expected fn_param_count={expected_count}, got {p.type.fn_param_count}.\n"
            f"Code: {code!r}"
        )

    @given(
        outer_ret=_return_type,
        fname=_func_name,
        fp_ret=_fp_return_type,
    )
    @settings(max_examples=100, deadline=None)
    def test_unnamed_fnptr_void_params(
        self, outer_ret: str, fname: str, fp_ret: str,
    ):
        """Unnamed function pointer with (void) has fn_param_count=0.

        **Validates: Requirements 1.2**
        """
        code = f"{outer_ret} {fname}({fp_ret} (*)(void));"
        fd = _parse_proto(code)

        assert len(fd.parameters) == 1
        p = fd.parameters[0]
        assert p.name is None
        assert p.type.is_pointer
        assert p.type.fn_param_count == 0


# ---------------------------------------------------------------------------
# Property 3: 混合参数顺序保持
# Feature: parser-semantics-hardening, Property 3: mixed parameter order preserved
# ---------------------------------------------------------------------------

# Strategy for a single parameter that is either named or unnamed.
@st.composite
def _mixed_param(draw):
    """Generate a parameter that is either named or unnamed.

    Returns (param_str, expected_name) where expected_name is None for unnamed.
    """
    base = draw(st.sampled_from(["int", "char", "long", "short", "double", "float"]))
    stars = draw(st.integers(min_value=0, max_value=2))
    is_named = draw(st.booleans())
    name = draw(_param_name) if is_named else None

    type_str = _type_with_stars(base, stars)
    if name is not None:
        param_str = f"{type_str} {name}"
    else:
        param_str = type_str

    return param_str, name


@st.composite
def _mixed_param_list(draw):
    """Generate a list of 2-5 mixed named/unnamed parameters.

    Ensures unique names to avoid parser conflicts, and at least one named
    and one unnamed parameter.
    """
    count = draw(st.integers(min_value=2, max_value=5))
    params = []
    used_names = set()
    has_named = False
    has_unnamed = False

    all_names = ["a", "b", "c", "x", "y", "z", "p", "q", "n", "m",
                 "arg", "val", "ptr", "buf", "len", "idx"]

    for i in range(count):
        base = draw(st.sampled_from(["int", "char", "long", "short", "double"]))
        stars = draw(st.integers(min_value=0, max_value=2))

        # Force at least one named and one unnamed
        if i == count - 1 and not has_named:
            is_named = True
        elif i == count - 1 and not has_unnamed:
            is_named = False
        else:
            is_named = draw(st.booleans())

        type_str = _type_with_stars(base, stars)

        if is_named:
            # Pick a unique name
            available = [n for n in all_names if n not in used_names]
            if not available:
                is_named = False
            else:
                name = draw(st.sampled_from(available))
                used_names.add(name)
                param_str = f"{type_str} {name}"
                params.append((param_str, name))
                has_named = True
                continue

        params.append((type_str, None))
        has_unnamed = True

    return params


class TestMixedParameterOrderPreserved:
    """Property 3: 混合参数顺序保持

    For any parameter list containing a mix of named and unnamed parameters,
    the parsed Declaration list should maintain the same order as the source,
    with each Declaration's name field correctly reflecting whether it has a name.

    **Validates: Requirements 1.3**
    """

    @given(
        ret=_return_type,
        fname=_func_name,
        param_list=_mixed_param_list(),
    )
    @settings(max_examples=200, deadline=None)
    def test_mixed_params_order_and_names_preserved(
        self, ret: str, fname: str, param_list: list,
    ):
        """Mixed named/unnamed parameters preserve order and name correctness.

        **Validates: Requirements 1.3**
        """
        param_strs = [p[0] for p in param_list]
        expected_names = [p[1] for p in param_list]

        code = f"{ret} {fname}({', '.join(param_strs)});"
        fd = _parse_proto(code)

        assert len(fd.parameters) == len(expected_names), (
            f"Expected {len(expected_names)} parameters, got {len(fd.parameters)}.\n"
            f"Code: {code!r}"
        )

        for i, (param, expected_name) in enumerate(zip(fd.parameters, expected_names)):
            assert param.name == expected_name, (
                f"Parameter {i}: expected name={expected_name!r}, got {param.name!r}.\n"
                f"Code: {code!r}\n"
                f"All expected names: {expected_names}"
            )

    @given(
        ret=_return_type,
        fname=_func_name,
        count=st.integers(min_value=1, max_value=6),
    )
    @settings(max_examples=100, deadline=None)
    def test_all_unnamed_params_count_preserved(
        self, ret: str, fname: str, count: int,
    ):
        """A prototype with all unnamed parameters preserves the count.

        **Validates: Requirements 1.1, 1.3**
        """
        types = ["int", "char", "long", "short", "double", "float"]
        param_strs = [types[i % len(types)] for i in range(count)]
        code = f"{ret} {fname}({', '.join(param_strs)});"
        fd = _parse_proto(code)

        assert len(fd.parameters) == count, (
            f"Expected {count} parameters, got {len(fd.parameters)}.\n"
            f"Code: {code!r}"
        )
        for i, p in enumerate(fd.parameters):
            assert p.name is None, (
                f"Parameter {i}: expected name=None, got {p.name!r}.\n"
                f"Code: {code!r}"
            )
