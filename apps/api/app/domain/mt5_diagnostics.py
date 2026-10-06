from __future__ import annotations
import os


def mt5_python_package_status() -> dict:
    try:
        import MetaTrader5 as mt5  # type: ignore
        return {'python_package':'installed','version':getattr(mt5,'__version__',None),'hint':None}
    except (ImportError,OSError):
        local = os.name == 'nt' and not os.getenv('VERCEL')
        return {'python_package':'missing','version':None,
                'hint':'Run: py -m pip install MetaTrader5, then restart the Windows gateway API.' if local else 'This hosted API cannot run a local MT5 desktop terminal. Use a Windows launcher to open it and a Windows gateway to supply market data.'}
