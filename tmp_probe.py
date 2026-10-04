import sys
sys.path.insert(0, "apps/api")
from app.core.database import db

with db() as c:
    print([tuple(r) for r in c.execute("SELECT sql FROM sqlite_master WHERE name='reference_instruments'").fetchall()])
    print([tuple(r) for r in c.execute("SELECT * FROM reference_instruments LIMIT 3").fetchall()])
    print(c.execute("SELECT COUNT(*) FROM reference_instruments").fetchone()[0])
    print([r[0] for r in c.execute("SELECT symbol FROM reference_instruments").fetchall()])
    print([tuple(r) for r in c.execute("SELECT symbol, COUNT(*) FROM mi_candle WHERE timeframe='D1' GROUP BY symbol").fetchall()])
