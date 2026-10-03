from __future__ import annotations

CSM_CURRENCIES = ("EUR", "GBP", "USD", "JPY", "AUD", "NZD", "CAD", "CHF")

CURRENCIES = ("AUD", "CAD", "CHF", "EUR", "GBP", "JPY", "NZD", "USD")

XAU = "XAU"

FX_PAIRS_28 = (
    "AUDCAD",
    "AUDCHF",
    "AUDJPY",
    "AUDNZD",
    "AUDUSD",
    "CADCHF",
    "CADJPY",
    "CHFJPY",
    "EURAUD",
    "EURCAD",
    "EURCHF",
    "EURGBP",
    "EURJPY",
    "EURNZD",
    "EURUSD",
    "GBPAUD",
    "GBPCAD",
    "GBPCHF",
    "GBPJPY",
    "GBPNZD",
    "GBPUSD",
    "NZDCAD",
    "NZDCHF",
    "NZDJPY",
    "NZDUSD",
    "USDCAD",
    "USDCHF",
    "USDJPY",
)

FX_PAIRS = FX_PAIRS_28

# Platform strength matrix (Figma dashboard columns)
MATRIX_TIMEFRAMES = ("YTD", "Q", "MN", "W", "D1", "H8", "H1", "M15", "M5", "M1")

COMPUTE_TIMEFRAMES = MATRIX_TIMEFRAMES + ("AVG",)

SYNTHETIC_MATRIX_TIMEFRAMES = frozenset({"YTD", "Q"})

CANDLE_TIMEFRAMES = ("M1", "M5", "M15", "H1", "H8", "D1", "W1", "MN")
NATIVE_CANDLE_TIMEFRAMES = CANDLE_TIMEFRAMES

MATRIX_TO_CANDLE: dict[str, str] = {
    "M1": "M1",
    "M5": "M5",
    "M15": "M15",
    "H1": "H1",
    "H8": "H8",
    "D1": "D1",
    "W": "W1",
    "MN": "MN",
}

TIMEFRAME_ALIASES: dict[str, str] = {
    "MIN1": "M1",
    "MIN5": "M5",
    "MIN15": "M15",
    "W1": "W",
    "MN1": "MN",
    "D": "D1",
    "AVG": "AVG",
    "M30": "M15",
    "H4": "H1",
}

STRENGTH_TIMEFRAMES = COMPUTE_TIMEFRAMES
TIMEFRAMES = COMPUTE_TIMEFRAMES
CLOSED_BAR_ONLY = True
RELATIONSHIP_STATES = ("DIVERGENCE", "EQUILIBRIUM", "CONVERGENCE", "ROTATION", "TRANSITIONING", "UNCERTAIN")
QUALITY_STATES = ("FRESH", "AGING", "STALE", "MISSING", "INVALID", "PARTIAL")
INSPECTION_PRIORITIES = ("CRITICAL", "HIGH", "NORMAL", "LOW")

TIMEFRAME_SECONDS = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "H1": 3600,
    "H8": 28800,
    "D1": 86400,
    "W": 604800,
    "MN": 2592000,
    "Q": 7776000,
    "YTD": 31536000,
    "AVG": 3600,
}


def normalize_matrix_timeframe(tf: str) -> str:
    u = tf.upper()
    return TIMEFRAME_ALIASES.get(u, u)
