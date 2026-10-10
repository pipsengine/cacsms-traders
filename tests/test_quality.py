from datetime import datetime, timezone
from apps.api.app.market.quality import assess
def test_missing_is_explicit():assert assess("EURUSD","H1",None).state=="MISSING"

def test_weekend_does_not_make_fridays_h1_stale():
    from apps.api.app.market.outlook.calendar import freshness_now

    saturday = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
    friday_close = datetime(2026, 10, 9, 21, tzinfo=timezone.utc)
    clock = freshness_now(saturday)
    assert assess("EURUSD", "H1", friday_close, now=clock).state != "STALE"
    assert assess("EURUSD", "H1", datetime(2026, 10, 7, 12, tzinfo=timezone.utc), now=clock).state == "STALE"
    wednesday = datetime(2026, 10, 7, 15, tzinfo=timezone.utc)
    assert freshness_now(wednesday) == wednesday
    assert assess("EURUSD", "H1", datetime(2026, 10, 7, 10, tzinfo=timezone.utc), now=freshness_now(wednesday)).state == "STALE"
