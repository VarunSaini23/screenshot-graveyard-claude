import os
import sys
import tempfile
from pathlib import Path

# Isolate app data before any app module is imported.
_tmp = tempfile.mkdtemp(prefix="sg-test-home-")
os.environ["SG_HOME"] = _tmp
os.environ.setdefault("SG_DISABLE_CLIP", "1")
os.environ.setdefault("SG_CLAUDE", "0")
os.environ.setdefault("SG_WORKERS", "2")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
