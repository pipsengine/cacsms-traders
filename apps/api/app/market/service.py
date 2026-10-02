from datetime import datetime,timezone
from .constants import CURRENCIES,FX_PAIRS,STRENGTH_TIMEFRAMES
from .strength_engine import StrengthEngine
from .relationship_engine import RelationshipEngine
from .inspection import inspection_score
class MarketIntelligenceService:
 def __init__(self,repo): self.repo=repo; self.strength=StrengthEngine(); self.relationship=RelationshipEngine()
 def calculate_timeframe(self,timeframe,pair_closes,as_of=None):
  as_of=as_of or datetime.now(timezone.utc); previous={c:[r[1] for r in self.repo.strength_history(c,timeframe,16)] for c in CURRENCIES}
  strengths=self.strength.calculate(timeframe,pair_closes,previous,as_of)
  for p in strengths.values():self.repo.save_strength(p)
  relationships=[]
  for pair in FX_PAIRS:
   b,q=pair[:3],pair[3:]; hist=[]
   rp=self.relationship.classify(pair,timeframe,strengths[b],strengths[q],hist,as_of); self.repo.save_relationship(rp); relationships.append(rp)
  self.repo.conn.commit(); return strengths,relationships
