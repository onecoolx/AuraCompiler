"""Property-based tests for function pointer type compatibility checking.

**Validates: Requirements 7.1, 7.2, 7.3**

Property 10: Function pointer type compatibility checking
For any two function pointer types, assignment should be accepted if and only if
their return types are compatible and all corresponding parameter types are
compatible; otherwise the compiler should report a type incompatibility error
indicating the mismatch location.

Testing approach: use Hypothesis to generate pairs of function signatures
(return type + parameter types), then:
1. For compatible pairs: generate C code with function + function pointer
   assignment, verify compilation succeeds
2. For incompatible pairs: generate C code with mismatched types, verify
   compilation fails with appropriate error
"""
from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from pycc.compiler import Compiler


# ---------------------------------------------------------------------------
# Type pools
# ---------------------------------------------------------------------------

RETURN_TYPES = ["int", "void", "char", "long"]
PARAM_TYPES = ["int", "char", "long", "int*", "char*"]

# Types that are considered compatible with each other under C89 rules.
# int and signed int are the same canonical type; everything else must match
# exactly (for non-pointer scalars) or have compatible pointee types.
_COMPAT_GROUPS = {
    "int": "int",
    "char": "char",
    "long": "long",
    "void": "void",
    "int*": "int*",
    "char*": "char*",
}


def _types_compatible(t1: str, t2: str) -> bool:
    """Return True if *t1* and *t2* are compatible under simplified C89 rules."""
    return _COMPAT_GROUPS.get(t1, t1) == _COMPAT_GROUPS.get(t2, t2)


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

@st.composite
def compatible_signature_pair(draw):
    """Generate a pair of compatible function signatures.

    Both signatures share the same return type and parameter types.
    """
    n_params = draw(st.integers(min_value=0, max_value=3))
    ret = draw(st.sampled_from(RETURN_TYPES))
    params = [draw(st.sampled_from(PARAM_TYPES)) for _ in range(n_params)]
    return (ret, params, ret, list(params))


@st.composite
def incompatible_return_pair(draw):
    """Generate a pair of signatures that differ only in return type."""
    n_params = draw(st.integers(min_value=0, max_value=3))
    ret1 = draw(st.sampled_from(RETURN_TYPES))
    ret2 = draw(st.sampled_from(RETURN_TYPES))
    assume(not _types_compatible(ret1, ret2))
    params = [draw(st.sampled_from(PARAM_TYPES)) for _ in range(n_params)]
    return (ret1, params, ret2, list(params))


@st.composite
def incompatible_param_pair(draw):
    """Generate a pair of signatures that differ in at least one parameter type."""
    n_params = draw(st.integers(min_value=1, max_value=3))
    ret = draw(st.sampled_from(RETURN_TYPES))
    params1 = [draw(st.sampled_from(PARAM_TYPES)) for _ in range(n_params)]
    params2 = list(params1)
    # Mutate at least one parameter to be incompatible
    idx = draw(st.integers(min_value=0, max_value=n_params - 1))
    new_type = draw(st.sampled_from(PARAM_TYPES))
    assume(not _types_compatible(params1[idx], new_type))
    params2[idx] = new_type
    return (ret, params1, ret, params2)


# ---------------------------------------------------------------------------
# C code generation helpers
# ---------------------------------------------------------------------------

def _format_param_list(types: list[str]) -> str:
    """Format a parameter list for a function declaration."""
    if not types:
        return "void"
    return ", ".join(f"{t} p{i}" if not t.endswith("*") else f"{t}p{i}"
                     for i, t in enumerate(types))


def _format_fnptr_param_list(types: list[str]) -> str:
    """Format a parameter list for a function pointer type."""
    if not types:
        return "void"
    return ", ".join(types)


def _make_return_expr(ret_type: str) -> str:
    """Generate a return expression for the given return type."""
    if ret_type == "void":
        return ""
    return "return 0;"


def _generate_compatible_code(ret: str, params: list[str]) -> str:
    """Generate C code where a function is assigned to a compatible function pointer."""
    param_decl = _format_param_list(params)
    fnptr_params = _format_fnptr_param_list(params)
    ret_expr = _make_return_expr(ret)

    body = f"{{ {ret_expr} }}" if ret_expr else "{ }"

    lines = [
        f"{ret} target_fn({param_decl}) {body}",
        "",
        "int main(void) {",
        f"    {ret} (*fp)({fnptr_params}) = target_fn;",
    ]
    # Call the function pointer to ensure it's used (avoid unused warnings)
    if params:
        args = ", ".join("0" for _ in params)
    else:
        args = ""
    if ret == "void":
        lines.append(f"    fp({args});")
        lines.append("    return 0;")
    else:
        lines.append(f"    return (int)fp({args});")
    lines.append("}")
    return "\n".join(lines)


def _generate_incompatible_code(fn_ret: str, fn_params: list[str],
                                 fp_ret: str, fp_params: list[str]) -> str:
    """Generate C code where a function is assigned to an incompatible function pointer."""
    fn_param_decl = _format_param_list(fn_params)
    fp_param_list = _format_fnptr_param_list(fp_params)
    ret_expr = _make_return_expr(fn_ret)

    body = f"{{ {ret_expr} }}" if ret_expr else "{ }"

    lines = [
        f"{fn_ret} target_fn({fn_param_decl}) {body}",
        "",
        "int main(void) {",
        f"    {fp_ret} (*fp)({fp_param_list}) = target_fn;",
        "    return 0;",
        "}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Compile helper
# ---------------------------------------------------------------------------

def _compile(tmp_path, code: str):
    """Compile C code with pycc and return the CompilationResult."""
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


# ---------------------------------------------------------------------------
# Property 10: Function pointer type compatibility checking
# ---------------------------------------------------------------------------

class TestFnPtrTypeCompatProperties:
    """Property 10: Function pointer type compatibility checking

    **Validates: Requirements 7.1, 7.2, 7.3**
    """

    @given(data=compatible_signature_pair())
    @settings(max_examples=100, deadline=None)
    def test_compatible_fnptr_assignment_accepted(self, tmp_path_factory, data):
        """For any two function pointer types with compatible return type and
        all compatible parameter types, assignment should be accepted.

        **Validates: Requirements 7.1**
        """
        ret, params, _, _ = data
        tmp_path = tmp_path_factory.mktemp("test")
        code = _generate_compatible_code(ret, params)
        res = _compile(tmp_path, code)
        assert res.success, (
            f"Expected compatible assignment to succeed for "
            f"{ret}({', '.join(params)}) but got errors: {res.errors}\n\n"
            f"Generated code:\n{code}"
        )

    @given(data=incompatible_return_pair())
    @settings(max_examples=100, deadline=None)
    def test_incompatible_return_type_rejected(self, tmp_path_factory, data):
        """For any two function pointer types with incompatible return types,
        assignment should be rejected with a return type mismatch error.

        **Validates: Requirements 7.3**
        """
        fn_ret, fn_params, fp_ret, fp_params = data
        tmp_path = tmp_path_factory.mktemp("test")
        code = _generate_incompatible_code(fn_ret, fn_params, fp_ret, fp_params)
        res = _compile(tmp_path, code)
        assert not res.success, (
            f"Expected incompatible return type assignment to fail for "
            f"fn={fn_ret}({', '.join(fn_params)}) vs "
            f"fp={fp_ret}({', '.join(fp_params)})\n\n"
            f"Generated code:\n{code}"
        )

    @given(data=incompatible_param_pair())
    @settings(max_examples=100, deadline=None)
    def test_incompatible_param_type_rejected(self, tmp_path_factory, data):
        """For any two function pointer types with at least one incompatible
        parameter type, assignment should be rejected with a parameter type
        mismatch error.

        **Validates: Requirements 7.2**
        """
        fn_ret, fn_params, fp_ret, fp_params = data
        tmp_path = tmp_path_factory.mktemp("test")
        code = _generate_incompatible_code(fn_ret, fn_params, fp_ret, fp_params)
        res = _compile(tmp_path, code)
        assert not res.success, (
            f"Expected incompatible param type assignment to fail for "
            f"fn={fn_ret}({', '.join(fn_params)}) vs "
            f"fp={fp_ret}({', '.join(fp_params)})\n\n"
            f"Generated code:\n{code}"
        )
