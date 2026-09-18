"""Punto de entrada compatible para cargar Lude Economy como extensión.

La implementación vive en el paquete :mod:`lude`; este módulo conserva las
importaciones históricas y el ``setup(bot)`` esperado por discord.py.
"""

from lude.config import *  # noqa: F401,F403 - compatibilidad con el módulo anterior
from lude.core import LudeEconomy, setup
from lude.crypto import market_engine_step
from lude.groups import TesterLudeGroup
from lude.utils import *  # noqa: F401,F403
from lude.views import (  # noqa: F401
    BlackjackView,
    CoinflipView,
    LudeAdminConfirmation,
    LudeAdminModal,
    LudeAdminPanel,
    LudeNavigator,
    ProtectionOfferView,
    WorkView,
)

__all__ = ("LudeEconomy", "setup", "market_engine_step", "TesterLudeGroup")
