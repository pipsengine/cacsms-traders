from __future__ import annotations
import os


def mt5_python_package_status() -> dict:
    try:
        import MetaTrader5 as mt5  # type: ignore
        return {'python_package':'installed','version':getattr(mt5,'__version__',None),'hint':None}
    except (ImportError,OSError):
        local = os.name == 'nt' and not os.getenv('VERCEL')
        return {'python_package':'missing','version':None,
                'hint':'Run: py -m pip install MetaTrader5, then restart the Windows gateway API.' if local else 'No Windows MT5 gateway is connected. The hosted API cannot open a terminal on another machine.'}
