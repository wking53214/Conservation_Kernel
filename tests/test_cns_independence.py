"""The Conservation Kernel is independent of CNS, and these tests hold whether
or not CNS is installed. They never skip.

Most run in a fresh interpreter in which ``cns`` is blocked outright
(``sys.modules['cns'] = None`` makes any import of it fail), so the result does
not depend on what the test environment happens to contain. One runs with CNS
reachable, when it is installed, and asserts the package never loads it.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PACKAGE = SRC / "conservation_kernel"

CNS_SHA = "3b465dbcc1a6a4ab6f1040f93d44483196abd737"

BLOCK = "import sys; sys.modules['cns'] = None; sys.modules['cns.gate'] = None\n"


def _run(code: str, *, block: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", (BLOCK if block else "") + textwrap.dedent(code)],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(SRC), "PATH": ""},
        timeout=120,
    )


def _ok(done: subprocess.CompletedProcess[str]) -> None:
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "ok"


def test_the_blocking_really_blocks():
    """If this fails, every other test in this file proves nothing."""
    done = _run(
        """
        try:
            import cns
        except ImportError:
            print('ok')
        """
    )
    _ok(done)


def test_every_module_of_the_package_imports_with_cns_blocked():
    done = _run(
        """
        import importlib, pkgutil
        import conservation_kernel
        names = [m.name for m in pkgutil.walk_packages(
            conservation_kernel.__path__, 'conservation_kernel.')]
        assert 'conservation_kernel.cns_connector' in names
        for name in names:
            importlib.import_module(name)
        print('ok')
        """
    )
    _ok(done)


def test_the_kernel_still_judges_transformations_with_cns_blocked():
    done = _run(
        """
        from conservation_kernel import ConservationKernel, VerificationStatus
        from conservation_kernel.experiments import (
            build_ground_truth, hostile_cases, legitimate_transformation)
        base, registry = build_ground_truth()
        kernel = ConservationKernel(registry=registry)
        kernel.register_root(base)
        output, record = legitimate_transformation(base, 1)
        assert kernel.submit(base, output, record).accepted
        case = hostile_cases()[0]
        output, record, _ = case.build(base)
        result = kernel.submit(base, output, record)
        assert result.status is VerificationStatus.REJECT
        print('ok')
        """
    )
    _ok(done)


def test_the_connector_says_what_is_missing_when_cns_is_blocked():
    done = _run(
        """
        from conservation_kernel.cns_connector import (
            CnsNotInstalled, cns_available, cns_chain, verify_to_cns)
        from conservation_kernel.experiments import (
            build_ground_truth, legitimate_transformation)
        assert cns_available() is False
        base, registry = build_ground_truth()
        output, record = legitimate_transformation(base, 1)
        for call in (
            lambda: verify_to_cns(base, output, record, registry),
            lambda: cns_chain(registry),
        ):
            try:
                call()
            except CnsNotInstalled as exc:
                message = str(exc)
                assert isinstance(exc, ImportError)
                # The extra pins cns by git commit, which PyPI does not accept, so
                # the hint must not send anyone to an index for it.
                assert "conservation-kernel[cns] @ git+https://" in message, message
                assert "pip install -e '.[cns]'" in message, message
                assert "pip install 'conservation-kernel[cns]'" not in message, message
            else:
                raise AssertionError('no CnsNotInstalled')
        print('ok')
        """
    )
    _ok(done)


def test_constructing_a_gate_fails_at_construction_not_first_use():
    done = _run(
        """
        from conservation_kernel import ConservationKernel, EvidenceRegistry
        from conservation_kernel.cns_connector import (
            CnsGate, CnsNotInstalled, CnsRootAdmissionGate)
        for build in (
            lambda: CnsGate(EvidenceRegistry()),
            lambda: CnsRootAdmissionGate(ConservationKernel()),
        ):
            try:
                build()
            except CnsNotInstalled:
                pass
            else:
                raise AssertionError('constructed without cns')
        print('ok')
        """
    )
    _ok(done)


def test_submit_to_cns_without_cns_raises_before_the_kernel_is_touched():
    """A connector that submitted first and complained after would change the
    ledger in an environment that cannot even report the verdict."""
    done = _run(
        """
        from conservation_kernel import ConservationKernel
        from conservation_kernel.cns_connector import CnsNotInstalled, submit_to_cns
        from conservation_kernel.experiments import (
            build_ground_truth, legitimate_transformation)
        base, registry = build_ground_truth()
        kernel = ConservationKernel(registry=registry)
        kernel.register_root(base)
        before = kernel.ledger.snapshot()
        output, record = legitimate_transformation(base, 1)
        try:
            submit_to_cns(kernel, base, output, record)
        except CnsNotInstalled:
            pass
        else:
            raise AssertionError('no CnsNotInstalled')
        assert kernel.ledger.snapshot() == before
        assert kernel.ledger.reports() == ()
        print('ok')
        """
    )
    _ok(done)


def test_importing_the_package_never_even_tries_to_import_cns():
    """A load that is attempted and swallowed (``try: import_module('cns.gate')
    except ImportError: pass`` at module level) passes the blocked-import tests,
    because blocking makes it fail quietly, and the AST scan, which looks for
    import statements. A finder that records every lookup of ``cns`` sees it, in
    an environment without CNS as well as one with it."""
    done = _run(
        """
        import importlib, pkgutil, sys

        attempts = []

        class Recorder:
            def find_spec(self, name, path=None, target=None):
                if name == 'cns' or name.startswith('cns.'):
                    attempts.append(name)
                return None

        sys.modules.pop('cns', None)
        sys.modules.pop('cns.gate', None)
        sys.meta_path.insert(0, Recorder())
        import conservation_kernel
        for module in pkgutil.walk_packages(
                conservation_kernel.__path__, 'conservation_kernel.'):
            importlib.import_module(module.name)
        assert attempts == [], attempts

        # The recorder has to be able to see an attempt, or the line above is empty.
        try:
            import cns.gate
        except ImportError:
            pass
        assert attempts, 'the recorder did not see an import of cns'
        print('ok')
        """,
        block=False,
    )
    _ok(done)


def test_importing_and_using_the_package_never_loads_cns_even_when_it_is_installed():
    """Runs with CNS reachable. Where CNS is installed this is the test that
    catches an import-time load; where it is not, it still passes honestly."""
    done = _run(
        """
        import sys
        import conservation_kernel, conservation_kernel.cns_connector
        from conservation_kernel import ConservationKernel
        from conservation_kernel.experiments import (
            build_ground_truth, hostile_cases, legitimate_transformation)
        base, registry = build_ground_truth()
        kernel = ConservationKernel(registry=registry)
        kernel.register_root(base)
        output, record = legitimate_transformation(base, 1)
        assert kernel.submit(base, output, record).accepted
        output, record, _ = hostile_cases()[0].build(base)
        assert not kernel.submit(base, output, record).accepted
        loaded = sorted(m for m in sys.modules if m == 'cns' or m.startswith('cns.'))
        assert loaded == [], loaded
        print('ok')
        """,
        block=False,
    )
    _ok(done)


def _module_level_cns_imports(path: Path) -> list[int]:
    """Line numbers of ``import cns`` / ``from cns ...`` that run at import time.

    Class bodies run at import; function bodies do not, so those are skipped.
    """
    found: list[int] = []

    def visit(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(child, ast.Import):
                if any(a.name == "cns" or a.name.startswith("cns.") for a in child.names):
                    found.append(child.lineno)
            elif isinstance(child, ast.ImportFrom):
                if child.level == 0 and (
                    child.module == "cns" or (child.module or "").startswith("cns.")
                ):
                    found.append(child.lineno)
            visit(child)

    visit(ast.parse(path.read_text(encoding="utf-8")))
    return found


def test_no_module_of_the_package_imports_cns_at_module_level():
    files = sorted(PACKAGE.rglob("*.py"))
    assert any(f.name == "cns_connector.py" for f in files)
    offenders = {
        str(f.relative_to(ROOT)): lines
        for f in files
        if (lines := _module_level_cns_imports(f))
    }
    assert offenders == {}


def test_the_static_scan_does_catch_a_module_level_import(tmp_path):
    """The scan above is only worth having if it can fail."""
    bad = tmp_path / "bad.py"
    bad.write_text("import os\nimport cns.gate\n", encoding="utf-8")
    assert _module_level_cns_imports(bad) == [2]
    bad.write_text("from cns.gate import GateResult\n", encoding="utf-8")
    assert _module_level_cns_imports(bad) == [1]
    ok = tmp_path / "ok.py"
    ok.write_text("def f():\n    import cns.gate\n", encoding="utf-8")
    assert _module_level_cns_imports(ok) == []


def test_the_package_declares_no_runtime_dependency_and_pins_the_extra():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["dependencies"] == []
    extras = data["project"]["optional-dependencies"]
    assert set(extras) == {"dev", "cns"}
    (requirement,) = extras["cns"]
    assert requirement.startswith("cns @ git+https://github.com/wking53214/cns.git@")
    assert requirement.endswith(CNS_SHA)
