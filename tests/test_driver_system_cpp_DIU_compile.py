import os
import subprocess
import textwrap


def test_system_cpp_compile_forwards_I_D_U(tmp_path):
    # End-to-end compile+link path (not -E): ensure driver forwards -I/-D/-U
    # to the system preprocessor invoked by --use-system-cpp.
    inc = tmp_path / "inc"
    inc.mkdir()

    (inc / "cfg.h").write_text(
        textwrap.dedent(
            """
            #ifndef NAME
            #error NAME not defined
            #endif
            
            #ifdef SHOULD_NOT_BE_DEFINED
            #error SHOULD_NOT_BE_DEFINED is defined
            #endif
            """
        ).lstrip()
    )

    src = tmp_path / "main.c"
    src.write_text(
        textwrap.dedent(
            """
            #include <stdio.h>
            #include "cfg.h"

            int main(void) {
                puts(NAME);
                return 0;
            }
            """
        ).lstrip()
    )

    exe = tmp_path / "a.out"

    cmd = [
        "python",
        "pycc.py",
        "--use-system-cpp",
        str(src),
        "-o",
        str(exe),
        "-I",
        str(inc),
        "-DSHOULD_NOT_BE_DEFINED",
        "-U",
        "SHOULD_NOT_BE_DEFINED",
        "-DNAME=\"ok\"",
    ]

    env = dict(os.environ)
    # Determinism for locale-sensitive output.
    env.setdefault("LC_ALL", "C")

    build = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert build.returncode == 0, (build.stdout, build.stderr)

    run = subprocess.run([str(exe)], capture_output=True, text=True, env=env)
    assert run.returncode == 0, (run.stdout, run.stderr)
    assert run.stdout == "ok\n"
