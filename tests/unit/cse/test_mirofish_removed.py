"""
S-CSE-14 — mirofish removal.

AC-CSE-20: No imports of complira_graph.mirofish remain in the codebase after removal.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
SRC_ROOT = PROJECT_ROOT / "src"


class TestMirofishRemoved:
    def test_mirofish_module_files_do_not_exist(self) -> None:
        """AC-CSE-20: mirofish Python files must be deleted."""
        deleted = [
            SRC_ROOT / "complira_graph" / "mirofish" / "trigger_client.py",
            SRC_ROOT / "complira_graph" / "mirofish" / "seed_extractor.py",
            SRC_ROOT / "complira_graph" / "mirofish" / "__init__.py",
            SRC_ROOT / "api" / "v1" / "endpoints" / "mirofish.py",
        ]
        existing = [str(p) for p in deleted if p.exists()]
        assert not existing, f"mirofish files still exist: {existing}"

    def test_no_mirofish_import_in_src(self) -> None:
        """AC-CSE-20: No Python source file has an import statement for complira_graph.mirofish."""
        # Match only actual import lines, not comments/docstrings
        result = subprocess.run(
            ["grep", "-rn", "--include=*.py",
             "-E", r"^(from|import)\s+complira_graph\.mirofish",
             str(SRC_ROOT)],
            capture_output=True,
            text=True,
        )
        matches = result.stdout.strip()
        assert not matches, (
            f"Found complira_graph.mirofish import statements in src/:\n{matches}"
        )

    def test_no_mirofish_import_in_router(self) -> None:
        """Router must not import mirofish endpoint."""
        router_path = SRC_ROOT / "api" / "v1" / "router.py"
        content = router_path.read_text()
        assert "mirofish" not in content, (
            "router.py still references mirofish"
        )

    def test_cse_router_registered(self) -> None:
        """router.py must register the CSE router."""
        router_path = SRC_ROOT / "api" / "v1" / "router.py"
        content = router_path.read_text()
        assert "from api.v1.endpoints import cse" in content
        assert 'cse.router' in content

    def test_no_mirofish_import_in_tests(self) -> None:
        """Test files must not have import statements for complira_graph.mirofish."""
        tests_root = PROJECT_ROOT / "tests"
        result = subprocess.run(
            ["grep", "-rn", "--include=*.py",
             "-E", r"^(from|import)\s+complira_graph\.mirofish",
             str(tests_root)],
            capture_output=True,
            text=True,
        )
        matches = result.stdout.strip()
        assert not matches, (
            f"Found mirofish import statements in test files:\n{matches}"
        )
