from __future__ import annotations

from pathlib import Path

from pycc.compiler import Compiler


def test_codegen_no_dynamic_stack_growth_in_function_body(tmp_path: Path):
    # Step-3 target: stop dynamically doing `subq $8, %rsp` during the function body
    # for temp spills. This keeps stack frames predictable and avoids ABI pitfalls.
    code = r'''
    int main(void) {
      int a = 1;
      int b = 2;
      int c = 3;
      int d = 4;
      int e = 5;
      int f = 6;
      int g = 7;
      int h = 8;
      int i = 9;
      int j = 10;
      int k = 11;
      int sum = a+b+c+d+e+f+g+h+i+j+k;
      return sum == 66 ? 0 : 1;
    }
    '''.lstrip()

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    asm = res.assembly or ""
    # Only forbid stack growth emitted for temp/local allocation in the body.
    # Calls may still use a temporary 8-byte pad for SysV ABI alignment.
    for line in asm.splitlines():
      s = line.strip()
      if s.startswith("subq $8, %rsp") and "pre_call_pad" not in s:
        raise AssertionError("dynamic stack growth found in assembly")
