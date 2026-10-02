from apps.api.app.market.strength_engine import StrengthEngine
def test_strength_is_zero_centered():
 data={'AUDCAD':[1+i*.001 for i in range(30)],'EURUSD':[1.1-i*.001 for i in range(30)],'GBPJPY':[180+i*.1 for i in range(30)]}; out=StrengthEngine().calculate('H1',data); assert abs(sum(x.value for x in out.values()))<1e-6
