"""Integration tests for compiling source files that include system headers.

Validates Requirements 4.1 and 4.2: the compiler can parse and semantically
analyse real glibc headers (<stdio.h>, <stdlib.h>) without errors when
use_system_cpp=True is enabled.

These tests require gcc on the system PATH; they are automatically skipped
when gcc is not available.
"""

import shutil
import pytest
from pycc.compiler import Compiler

_has_gcc = shutil.which("gcc") is not None


@pytest.mark.skipif(not _has_gcc, reason="gcc not available")
class TestSystemHeaderIntegration:
    """Tests that compile C source files including system headers."""

    def test_stdio_stdlib_include(self, tmp_path):
        """Compile a minimal program that includes <stdio.h> and <stdlib.h>."""
        src = tmp_path / "test.c"
        src.write_text(
            '#include <stdio.h>\n'
            '#include <stdlib.h>\n'
            'int main(void) { return 0; }\n'
        )
        compiler = Compiler(use_system_cpp=True)
        result = compiler.compile_file(str(src))
        assert result is not None
        assert result.success, f"Compilation failed: {result.errors}"

    def test_stdio_printf_declaration(self, tmp_path):
        """Ensure printf is visible after including <stdio.h>."""
        src = tmp_path / "test_printf.c"
        src.write_text(
            '#include <stdio.h>\n'
            'int main(void) {\n'
            '    printf("hello\\n");\n'
            '    return 0;\n'
            '}\n'
        )
        compiler = Compiler(use_system_cpp=True)
        result = compiler.compile_file(str(src))
        assert result is not None
        assert result.success, f"Compilation failed: {result.errors}"

    def test_stdlib_malloc_declaration(self, tmp_path):
        """Ensure malloc/free are visible after including <stdlib.h>."""
        src = tmp_path / "test_malloc.c"
        src.write_text(
            '#include <stdlib.h>\n'
            'int main(void) {\n'
            '    void *p = malloc(16);\n'
            '    free(p);\n'
            '    return 0;\n'
            '}\n'
        )
        compiler = Compiler(use_system_cpp=True)
        result = compiler.compile_file(str(src))
        assert result is not None
        assert result.success, f"Compilation failed: {result.errors}"
