from pydantic import BaseModel, Field, field_validator

SYMBOL_PATTERN = r"^[A-Z0-9._-]{3,16}$"
DRAWING_KINDS = frozenset({"horizontal", "trendline", "rectangle", "text", "fibonacci", "channel"})
CHART_TFS = frozenset({"M1", "M5", "M15", "M30", "H1", "H4", "H8", "D1", "W", "W1", "MN", "Q", "Y", "YTD", "HY"})


class Point(BaseModel):
    time: int
    price: float


class Drawing(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    symbol: str
    timeframe: str
    kind: str
    points: list[Point] = Field(min_length=1, max_length=3)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    label: str | None = Field(default=None, max_length=200)

    @field_validator("kind")
    @classmethod
    def valid_kind(cls, v: str) -> str:
        if v not in DRAWING_KINDS:
            raise ValueError("Unknown drawing tool")
        return v

    @field_validator("points")
    @classmethod
    def valid_points(cls, v: list[Point], info) -> list[Point]:
        kind = info.data.get("kind")
        if kind in {"horizontal", "text"} and len(v) != 1:
            raise ValueError("This drawing requires exactly one point")
        if kind in {"trendline", "rectangle", "fibonacci"} and len(v) != 2:
            raise ValueError("This drawing requires exactly two points")
        if kind == "channel" and len(v) != 3:
            raise ValueError("Parallel channel requires three points")
        return v


class Workspace(BaseModel):
    symbol: str
    timeframe: str
    indicators: list[str] = Field(max_length=30)
    layers: list[str] = Field(max_length=30)
    drawings: list[Drawing] = Field(max_length=300)
    expected_updated_at: str | None = Field(default=None, max_length=40)


class AnalysisIn(BaseModel):
    symbol: str
    timeframe: str
    title: str = Field(min_length=1, max_length=160)
    notes: str = Field(max_length=20000)


class OpportunityIn(BaseModel):
    symbol: str
    timeframe: str
    direction: str
    strategy: str
    notes: str = Field(max_length=20000)
    analysis_id: str | None = None
