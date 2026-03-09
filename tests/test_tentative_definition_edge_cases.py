from __future__ import annotations

from pathlib import Path

from pycc.compiler import Compiler


def _compile_multi(tmp_path: Path, sources: list[str]):
    paths = []
    for i, src in enumerate(sources):
        p = tmp_path / f"tu{i}.c"
        p.write_text(src, encoding="utf-8")
        paths.append(str(p))
    out = tmp_path / "a.out"
    comp = Compiler(optimize=False)
    res = comp.compile_files(paths, str(out))
    return res


def test_tentative_and_strong_definition_across_tus_links(tmp_path: Path):
    # C89: tentative definition `int g;` should be replaced by a single
    # external definition if some TU provides a real definition.
    res = _compile_multi(
        tmp_path,
        [
            "int g;\nint main(void){ return g; }\n",
            "int g = 7;\n",
        ],
    )
    assert res.success, "expected link success, got: " + "\n".join(res.errors)


def test_two_strong_definitions_across_tus_fails_to_link(tmp_path: Path):
    # Two external definitions with initializers should be a multiple-definition
    # error at link time.
    res = _compile_multi(
        tmp_path,
        [
            "int g = 1;\nint main(void){ return g; }\n",
            "int g = 2;\n",
        ],
    )
    assert not res.success


def test_static_definitions_in_two_tus_do_not_conflict(tmp_path: Path):
    # Internal linkage: each TU's `static int g;` is distinct.
    res = _compile_multi(
        tmp_path,
        [
            "static int g;\nint main(void){ g = 3; return g - 3; }\n",
            "static int g;\n",
        ],
    )
    assert res.success, "expected link success, got: " + "\n".join(res.errors)
