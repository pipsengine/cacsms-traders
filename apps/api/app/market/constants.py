from __future__ import annotations

# Display / matrix order (EarnForex CSM)
CSM_CURRENCIES = ("EUR", "GBP", "USD", "JPY", "AUD", "NZD", "CAD", "CHF")

# Legacy tuple used by relationship engine (sorted ISO)
CURRENCIES = ("AUD", "CAD", "CHF", "EUR", "GBP", "JPY", "NZD", "USD")

XAU = "XAU"

# Fixed 28-pair major basket (EarnForex CSM)
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

NATIVE_CANDLE_TIMEFRAMES = ("M1", "M5", "M15", "H1", "H8", "D1", "W1", "MN")
MATRIX_TIMEFRAMES = ("YTD", "Q", "MN", "W1", "D1", "H8", "H1", "M15", "M5", "M1", "AVG")
STRENGTH_TIMEFRAMES = MATRIX_TIMEFRAMES

TIMEFRAMES = MATRIX_TIMEFRAMES
CLOSED_BAR_ONLY = True
RELATIONSHIP_STATES = ("DIVERGENCE", "EQUILIBRIUM", "CONVERGENCE", "ROTATION", "TRANSITIONING", "UNCERTAIN")
QUALITY_STATES = ("FRESH", "AGING", "STALE", "MISSING", "INVALID")
INSPECTION_PRIORITIES = ("CRITICAL", "HIGH", "NORMAL", "LOW")

TIMEFRAME_SECONDS = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "H1": 3600,
    "H8": 28800,
    "D1": 86400,
    "W1": 604800,
    "MN": 2592000,
    "Q": 7776000,
    "YTD": 31536000,
    "AVG": 3600,
}
