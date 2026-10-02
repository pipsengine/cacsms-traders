from .constants import CURRENCIES
def split_pair(symbol:str):
 s=symbol.upper().replace("/","")
 if len(s)>=6 and s[:3] in CURRENCIES and s[3:6] in CURRENCIES:return s[:3],s[3:6]
 raise ValueError(f"Not a supported FX pair: {symbol}")
def canonical_pair(a,b): return a+b
