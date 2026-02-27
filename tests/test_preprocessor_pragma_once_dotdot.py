import os
import subprocess
import sys


def test_pragma_once_dotdot_path_equivalence(tmp_path):
    """Same header, different include spellings that normalize via '..'.

    This catches implementations that key #pragma once by the raw include spelling
    (or a non-normalized path) rather than a normalized absolute path.
    """

    # Layout:
    #   inc/real/po.h          (#pragma once)
    #   inc/real/sub/          (added to -I)
    # main.c includes:
    #   - "po.h" via -I inc/real
    #   - "../po.h" via -I inc/real/sub
    inc_real = tmp_path / "inc" / "real"
    inc_sub = inc_real / "sub"
    inc_sub.mkdir(parents=True)

    (inc_real / "po.h").write_text(
        "#pragma once\n"
        "int once = 42;\n",
        encoding="utf-8",
    )

    (tmp_path / "main.c").write_text(
        "#include \"po.h\"\n"
        "#include \"../po.h\"\n",
        encoding="utf-8",
    )

    cmd = [
        sys.executable,
        os.fspath(os.path.join(os.getcwd(), "pycc.py")),
        "-E",
        "-I",
        os.fspath(inc_real),
        "-I",
        os.fspath(inc_sub),
        os.fspath(tmp_path / "main.c"),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, (r.stdout, r.stderr)

    out = r.stdout
    assert out.count("int once = 42;") == 1
