from datetime import datetime,timezone
from apps.api.app.market.models import StrengthPoint
from apps.api.app.market.relationship_engine import RelationshipEngine
def p(c,v):return StrengthPoint(c,'H1',datetime.now(timezone.utc),v,confidence=1)
def test_close_is_equilibrium(): assert RelationshipEngine().classify('AUDCAD','H1',p('AUD',-.2),p('CAD',-.1),[-.1]).state=='EQUILIBRIUM'
def test_cross_is_rotation(): assert RelationshipEngine().classify('AUDCAD','H1',p('AUD',1),p('CAD',0),[-1]).state=='ROTATION'
