from __future__ import annotations

import os
import tempfile
from pathlib import Path


PROJECT_TMP = Path(__file__).resolve().parents[1] / ".tmp"
PROJECT_TMP.mkdir(exist_ok=True)

os.environ["TMP"] = str(PROJECT_TMP)
os.environ["TEMP"] = str(PROJECT_TMP)
os.environ["TMPDIR"] = str(PROJECT_TMP)
tempfile.tempdir = str(PROJECT_TMP)
