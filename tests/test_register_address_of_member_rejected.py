from pycc.compiler import Compiler


def test_register_struct_member_address_of_is_rejected(tmp_path):
    # C89: cannot take the address of a register object.
    # For this project, treat taking the address of any subobject of a register
    # object as also invalid (e.g. &s.x where `s` is register).
    code = r'''
struct S { int x; };
int main(){
  register struct S s;
  int *p = &s.x;
  return p ? 0 : 1;
}
'''.lstrip()

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert not res.success
