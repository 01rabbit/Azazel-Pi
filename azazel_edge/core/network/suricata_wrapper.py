"""Helper wrapper to launch Suricata with the currently selected WAN interface."""
from __future__ import annotations

import os
import sys
from typing import List

from azazel_edge.utils.wan_state import get_active_wan_interface
import os


def build_command(iface: str) -> List[str]:
    suricata_bin = os.environ.get("SURICATA_BIN", "/usr/bin/suricata")
    config_path = os.environ.get("SURICATA_CONFIG", "/etc/suricata/suricata.yaml")
    return [suricata_bin, "-c", config_path, "-i", iface]


def main() -> int:
    # Preference: SURICATA_IFACE env -> AZAZEL_WAN_IF env -> WANManager helper
    iface = os.environ.get("SURICATA_IFACE") or os.environ.get("AZAZEL_WAN_IF") or get_active_wan_interface()
    if not iface:
        print("suricata-wrapper: active WAN interface unknown", file=sys.stderr)
        return 1
    cmd = build_command(iface)
    os.execvp(cmd[0], cmd)  # Replace the process; no return


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
