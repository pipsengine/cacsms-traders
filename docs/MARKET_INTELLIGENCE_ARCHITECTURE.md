# Market Intelligence Architecture
This package is additive to Cacsms-Traders Foundation. It owns market-data normalization, closed-candle persistence, quality/freshness, currency strength, historical dynamics, pair relationships and inspection prioritization. It deliberately does not own channels, ranges, opportunities, risk, or execution.

Data flow: MT5 MarketDataGateway → CandleIngestionService → mi_candle → StrengthEngine → mi_strength_snapshot → RelationshipEngine → mi_relationship_snapshot → API/UI → later Structure Intelligence.

Rules: closed bars only for structural strength snapshots; missing/stale data remains explicit; no forward filling; no BUY/SELL outputs; close-strength pairs are retained; every calculation is reproducible from persisted inputs.
