"""Lude Economy: extensión modular para discord.py.

Avoid importing Discord when consumers only need the pure market engine.
Public imports ``from lude import LudeEconomy, setup`` remain supported.
"""

__all__ = ("LudeEconomy", "setup")


def __getattr__(name):
    if name in __all__:
        from .core import LudeEconomy, setup
        return {"LudeEconomy": LudeEconomy, "setup": setup}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
