from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# 手元の MWL・Storage の SCP（モダリティのダミーの試験。spec/12 の 14 章）
from modality_peers import storage_scp, worklist_items, worklist_scp  # noqa: E402, F401
