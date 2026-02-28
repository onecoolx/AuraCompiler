from __future__ import annotations

from pathlib import Path

from pycc.compiler import Compiler


def test_usual_arithmetic_conversions_unsigned_char_vs_int(tmp_path: Path):
    # C89: usual arithmetic conversions should convert both operands to a common type.
    # Here: (unsigned char)255 + 1 should be 256.
    code = r'''
    int main(void) {
      unsigned char x = 255;
      int y = x + 1;
      return y == 256 ? 0 : 1;
    }
    '''.lstrip()

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    import subprocess

    p = subprocess.run([str(out_path)], check=False)
    assert p.returncode == 0
