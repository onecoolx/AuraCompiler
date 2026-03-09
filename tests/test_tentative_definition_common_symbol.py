from __future__ import annotations

from pathlib import Path

from pycc.compiler import Compiler


def _compile_and_run(tmp_path: Path, c1: str, c2: str) -> int:
    import subprocess

    f1 = tmp_path / "a.c"
    f2 = tmp_path / "b.c"
    out = tmp_path / "a.out"
    f1.write_text(c1, encoding="utf-8")
    f2.write_text(c2, encoding="utf-8")

    comp = Compiler(optimize=False)
    res = comp.compile_files([str(f1), str(f2)], str(out))
    assert res.success, "compile/link failed: " + "\n".join(res.errors)

    run = subprocess.run([str(out)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return run.returncode


def _compile_to_objects(tmp_path: Path, c1: str, c2: str):
    f1 = tmp_path / "a.c"
    f2 = tmp_path / "b.c"
    o1 = tmp_path / "a.o"
    o2 = tmp_path / "b.o"
    f1.write_text(c1, encoding="utf-8")
    f2.write_text(c2, encoding="utf-8")

    comp = Compiler(optimize=False)
    r1 = comp.compile_file(str(f1), str(o1))
    assert r1.success, "compile a.o failed: " + "\n".join(r1.errors)
    r2 = comp.compile_file(str(f2), str(o2))
    assert r2.success, "compile b.o failed: " + "\n".join(r2.errors)
    return o1, o2


def test_tentative_definition_across_tus_links(tmp_path: Path):
    # C89: `int g;` at file scope is a tentative definition.
    # Across translation units, multiple tentative definitions should merge
    # into a single common symbol (as with gcc default -fcommon behavior).
    c1 = r"""
int g;
int main(void){
  g = 41;
  return g == 41 ? 0 : 1;
}
""".lstrip()

    c2 = r"""
int g;
""".lstrip()

    assert _compile_and_run(tmp_path, c1, c2) == 0


def test_tentative_definition_emits_common_symbol(tmp_path: Path):
    import subprocess

    c1 = "int g;\n"
    c2 = "int g;\n"

    o1, o2 = _compile_to_objects(tmp_path, c1, c2)

    # `.comm` is a GNU as directive and typically shows up as a 'C' (common)
    # symbol in `nm` output.
    nm1 = subprocess.run(["nm", "-g", str(o1)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    nm2 = subprocess.run(["nm", "-g", str(o2)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert nm1.returncode == 0, nm1.stderr
    assert nm2.returncode == 0, nm2.stderr
    assert " g" in nm1.stdout, nm1.stdout
    assert " g" in nm2.stdout, nm2.stdout
    assert " C g" in nm1.stdout or " c g" in nm1.stdout, nm1.stdout
    assert " C g" in nm2.stdout or " c g" in nm2.stdout, nm2.stdout


def test_extern_decl_does_not_allocate_storage(tmp_path: Path):
    import subprocess

    c1 = "extern int g;\n"
    c2 = "int g;\nint main(void){ return g; }\n"

    # Ensure sources exist on disk for the multi-file compile/link below.
    (tmp_path / "a.c").write_text(c1, encoding="utf-8")
    (tmp_path / "b.c").write_text(c2, encoding="utf-8")

    o1, o2 = _compile_to_objects(tmp_path, c1, c2)

    nm1 = subprocess.run(["nm", "-g", str(o1)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert nm1.returncode == 0, nm1.stderr
    # Should not define `g` in TU1.
    assert " C g" not in nm1.stdout and " B g" not in nm1.stdout and " D g" not in nm1.stdout, nm1.stdout

    # Link should still succeed because TU2 provides storage.
    out = tmp_path / "a.out"
    comp = Compiler(optimize=False)
    res = comp.compile_files([str(tmp_path / "a.c"), str(tmp_path / "b.c")], str(out))
    # Note: sources already exist due to _compile_to_objects
    assert res.success, "compile/link failed: " + "\n".join(res.errors)
