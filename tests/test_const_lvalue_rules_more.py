from __future__ import annotations


from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_assign_to_const_array_element_is_error(tmp_path):
    # Element lvalue is non-modifiable when the array element type is const.
    code = r'''
int main(void){
  const int a[2] = {1,2};
  a[0] = 3;
  return 0;
}
'''.lstrip()
    res = _compile(tmp_path, code)
    assert not res.success


def test_assign_through_pointer_to_const_is_error(tmp_path):
    # Writing through `const int *` is invalid.
    # NOTE: parser/semantics now models pointee-const for pointer declarators.
    code = r'''
int main(void){
  int x = 1;
  const int *p = &x;
  *p = 2;
  return 0;
}
'''.lstrip()
    res = _compile(tmp_path, code)
    assert not res.success
