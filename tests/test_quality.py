from datetime import datetime,timezone
from apps.api.app.market.quality import assess
def test_missing_is_explicit():assert assess("EURUSD","H1",None).state=="MISSING"
