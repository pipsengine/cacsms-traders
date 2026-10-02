from __future__ import annotations
from datetime import datetime, timezone
from .constants import CURRENCIES
from .symbols import split_pair
from .returns import normalized_return
from .math_utils import clamp,linear_slope
from .models import StrengthPoint
class StrengthEngine:
 """Cross-sectional currency strength. Each pair contributes equal/opposite normalized return evidence."""
 def calculate(self,timeframe,pair_closes:dict[str,list[float]],previous:dict[str,list[float]]|None=None,as_of=None):
  as_of=as_of or datetime.now(timezone.utc); totals={c:[] for c in CURRENCIES}
  for pair,closes in pair_closes.items():
   try: base,quote=split_pair(pair)
   except ValueError: continue
   if len(closes)<10: continue
   score=clamp(normalized_return(closes)*10,-100,100); totals[base].append(score); totals[quote].append(-score)
  raw={c:(sum(v)/len(v) if v else 0.0) for c,v in totals.items()}; center=sum(raw.values())/len(raw); raw={c:clamp(v-center,-100,100) for c,v in raw.items()}
  out={}
  for c,v in raw.items():
   hist=(previous or {}).get(c,[]); velocity=v-hist[-1] if hist else 0.0; prev_velocity=(hist[-1]-hist[-2]) if len(hist)>1 else 0.0
   out[c]=StrengthPoint(c,timeframe,as_of,v,linear_slope((hist+[v])[-8:]),velocity,velocity-prev_velocity,self._persistence((hist+[v])[-8:]),min(1,len(totals[c])/7),len(totals[c]),"FRESH" if totals[c] else "MISSING")
  return out
 def _persistence(self,xs):
  if len(xs)<2:return 0.0
  ds=[b-a for a,b in zip(xs,xs[1:])]; pos=sum(d>0 for d in ds); neg=sum(d<0 for d in ds); return max(pos,neg)/len(ds)
