"""Expose Personal OS offline gate tests to the repository-wide app/deploy CI suite."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "personal-os"))
from test_preview_gate import PreviewGateTests  # noqa: E402,F401
