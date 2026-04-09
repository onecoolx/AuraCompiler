"""Property-based tests for volatile code generation.

**Validates: Requirements 6.1, 6.2, 6.3**

Property 9: volatile 访问生成内存指令
For any volatile 限定的变量在循环中被读取或写入 N 次，生成的汇编代码中应包含
至少 N 条对应的内存加载或存储指令（不被优化消除或合并）。

Testing approach: use Hypothesis to generate a random count N (1-20),
generate C code with a volatile variable written N times (as N separate
assignment statements), compile to assembly using pycc, count the
``# volatile`` comment markers in the output, and verify there are at
least N markers (one per write, plus the initialisation write).
"""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from pycc.compiler import Compiler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_asm(code: str) -> str:
    """Compile *code* to assembly text via pycc (no optimisation)."""
    comp = Compiler(optimize=False)
    tokens = comp.get_tokens(code)
    ast = comp.get_ast(tokens)
    sema_ctx, _analyzer = comp.analyze_semantics(ast)
    ir = comp.get_ir(ast, sema_ctx=sema_ctx)
    return comp.get_assembly(ir, sema_ctx=sema_ctx)


def _count_volatile_markers(asm: str) -> int:
    """Return the number of ``# volatile`` comment lines in *asm*."""
    return sum(1 for line in asm.splitlines() if "# volatile" in line)


def _generate_volatile_writes(n: int) -> str:
    """Generate C code that writes to a volatile variable *n* times."""
    writes = "\n    ".join(f"x = {i};" for i in range(n))
    return (
        "int main(void) {\n"
        "    volatile int x = 0;\n"
        f"    {writes}\n"
        "    return x;\n"
        "}\n"
    )


# ---------------------------------------------------------------------------
# Property 9: volatile 访问生成内存指令
# ---------------------------------------------------------------------------

class TestVolatileAccessGeneratesMemoryInstructions:
    """Property 9: volatile 访问生成内存指令

    **Validates: Requirements 6.1, 6.2, 6.3**
    """

    @given(n=st.integers(min_value=1, max_value=20))
    @settings(max_examples=100, deadline=None)
    def test_volatile_writes_produce_at_least_n_markers(self, n: int):
        """For any N in [1, 20], writing to a volatile variable N times
        should produce at least N ``# volatile`` markers in the assembly.

        The initialisation ``volatile int x = 0`` itself counts as an
        additional volatile write, so the total is always >= N.

        **Validates: Requirements 6.1, 6.2, 6.3**
        """
        code = _generate_volatile_writes(n)
        asm = _get_asm(code)
        count = _count_volatile_markers(asm)
        assert count >= n, (
            f"Expected at least {n} '# volatile' markers for {n} writes, "
            f"got {count}.\n\nGenerated code:\n{code}"
        )
