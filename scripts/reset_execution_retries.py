"""One-off: clear retriable handoff errors and run outlook advance (same as POST /api/cacsms-engine/retry-execution)."""
from apps.api.app.autonomous.engine import _mode
from apps.api.app.cacsms_engine.advance import advance_authorised_outlooks
from apps.api.app.cacsms_engine.retry import reset_execution_retries
from apps.api.app.core.database import db
from apps.api.app.market.strength_intel_store import active_scope
from datetime import datetime, timezone

with db() as conn:
    tenant, account = active_scope(conn)
    cleared = reset_execution_retries(conn, tenant, account)
    advanced = advance_authorised_outlooks(conn, tenant, account, _mode(conn), datetime.now(timezone.utc))
    conn.commit()
    print("cleared", cleared)
    print("advance", advanced)
