from __future__ import annotations


def mt5_python_package_status() -> dict:
    try:
        import MetaTrader5 as mt5  # type: ignore

        ver = getattr(mt5, "__version__", None)
        return {
            "python_package": "installed",
            "version": ver,
            "hint": None,
        }
    except ImportError:
        return {
            "python_package": "missing",
            "version": None,
            "hint": "Run: py -m pip install MetaTrader5 — then restart the API server (uvicorn).",
        }
