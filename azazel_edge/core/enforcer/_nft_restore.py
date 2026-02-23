#!/usr/bin/env python3
"""Helper utilities for restoring persisted nft handle entries into engine."""
from typing import Dict
import json
from pathlib import Path

def load_persisted(path: Path) -> Dict[str, Dict]:
    try:
        if not path.exists():
            return {}
        with path.open('r') as fh:
            return json.load(fh)
    except Exception:
        return {}
