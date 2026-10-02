from datetime import datetime,timezone
from .models import RelationshipPoint
from .math_utils import clamp
from .symbols import split_pair
class RelationshipEngine:
 def __init__(self,equilibrium=1.0,divergence=3.0): self.equilibrium=equilibrium; self.divergence=divergence
 def classify(self,pair,timeframe,base,quote,history=None,as_of=None):
  as_of=as_of or datetime.now(timezone.utc); gap=base.value-quote.value; hist=list(history or []); prev=hist[-1] if hist else gap; prev2=hist[-2] if len(hist)>1 else prev; velocity=gap-prev; acceleration=velocity-(prev-prev2)
  crossed=(prev==0 or (prev<0<gap) or (prev>0>gap)); shrinking=abs(gap)<abs(prev); expanding=abs(gap)>abs(prev)
  if crossed and abs(velocity)>.25: state="ROTATION"
  elif abs(gap)<=self.equilibrium and abs(velocity)>.35: state="TRANSITIONING"
  elif abs(gap)<=self.equilibrium: state="EQUILIBRIUM"
  elif abs(gap)>=self.divergence and expanding: state="DIVERGENCE"
  elif shrinking: state="CONVERGENCE"
  else: state="UNCERTAIN"
  reasons=[]
  if abs(gap)<=self.equilibrium: reasons.append("RELATIVE_STRENGTH_CLOSE")
  if expanding: reasons.append("GAP_EXPANDING")
  if shrinking: reasons.append("GAP_COMPRESSING")
  if crossed: reasons.append("RELATIONSHIP_CROSSOVER")
  if abs(velocity)>.5: reasons.append("HIGH_GAP_VELOCITY")
  priority="HIGH" if state in ("ROTATION","TRANSITIONING") else "HIGH" if state=="EQUILIBRIUM" and abs(velocity)>.2 else "NORMAL" if state in ("DIVERGENCE","EQUILIBRIUM") else "LOW"
  confidence=clamp((base.confidence+quote.confidence)/2,0,1)
  return RelationshipPoint(pair,timeframe,as_of,base.value,quote.value,gap,abs(gap),velocity,acceleration,max(base.persistence,quote.persistence),state,confidence,priority,tuple(reasons))
