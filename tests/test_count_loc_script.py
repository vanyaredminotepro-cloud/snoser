import subprocess
import sys
from pathlib import Path


def test_count_loc_script_runs():
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run([sys.executable, str(root / "scripts" / "count_loc.py")], capture_output=True, text=True)
    assert proc.returncode == 0
    assert "Total LOC" in proc.stdout
