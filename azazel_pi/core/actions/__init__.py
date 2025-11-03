"""Traffic shaping actions used by the state machine.

⚠️ DEPRECATION WARNING: このactionsモジュールは非推奨です。
新しい統合システムでは azazel_pi.core.enforcer.traffic_control.TrafficControlEngine を使用してください。
テスト用途以外での使用は推奨されません。
"""

import warnings
warnings.warn(
    "azazel_pi.core.actions モジュールは非推奨です。traffic_control.TrafficControlEngine を使用してください。",
    DeprecationWarning,
    stacklevel=2
)

from .base import Action, ActionResult
from .delay import DelayAction
from .shape import ShapeAction
from .block import BlockAction
from .redirect import RedirectAction

__all__ = [
    "Action",
    "ActionResult",
    "DelayAction",
    "ShapeAction",
    "BlockAction",
    "RedirectAction",
]
