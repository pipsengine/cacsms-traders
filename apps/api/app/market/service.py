from datetime import datetime, timezone

from .constants import CSM_CURRENCIES, FX_PAIRS
from .csm_service import CurrencyStrengthMatrixService
from .models import StrengthPoint
from .relationship_engine import RelationshipEngine


class MarketIntelligenceService:
    def __init__(self, repo):
        self.repo = repo
        self.csm = CurrencyStrengthMatrixService(repo)
        self.relationship = RelationshipEngine()

    def calculate_matrix(self, as_of=None):
        result = self.csm.calculate(as_of=as_of)
        self.csm.persist(result)
        return result

    def calculate_timeframe(self, timeframe, pair_closes=None, as_of=None):
        """Run CSM matrix and derive relationship snapshots for one timeframe."""
        as_of = as_of or datetime.now(timezone.utc)
        result = self.csm.calculate(as_of=as_of)
        self.csm.persist(result)
        strengths: dict[str, StrengthPoint] = {}
        for c in CSM_CURRENCIES:
            val = result.values[c].get(timeframe, 0.0)
            strengths[c] = StrengthPoint(
                c,
                timeframe,
                as_of,
                val,
                sample_count=result.sample_counts[c].get(timeframe, 0),
                quality=result.quality[c].get(timeframe, "MISSING"),
                confidence=min(1.0, result.sample_counts[c].get(timeframe, 0) / 7.0),
            )
        relationships = []
        for pair in FX_PAIRS:
            b, q = pair[:3], pair[3:]
            if b not in strengths or q not in strengths:
                continue
            rp = self.relationship.classify(pair, timeframe, strengths[b], strengths[q], [], as_of)
            self.repo.save_relationship(rp)
            relationships.append(rp)
        self.repo.conn.commit()
        return strengths, relationships
