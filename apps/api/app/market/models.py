from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
@dataclass(frozen=True)
class Candle:
 symbol:str; timeframe:str; open_time:datetime; close_time:datetime; open:float; high:float; low:float; close:float; tick_volume:int=0; spread:float|None=0.0; source:str="UNKNOWN"; is_closed:bool=True; account_id:str=""
@dataclass(frozen=True)
class DataQuality:
 symbol:str; timeframe:str; state:str; last_closed_at:Optional[datetime]; age_seconds:Optional[float]; missing_bars:int=0; reason:str=""
@dataclass(frozen=True)
class StrengthPoint:
 currency:str; timeframe:str; as_of:datetime; value:float; slope:float=0; velocity:float=0; acceleration:float=0; persistence:float=0; confidence:float=0; sample_count:int=0; quality:str="FRESH"; score:float|None=None
@dataclass(frozen=True)
class RelationshipPoint:
 pair:str; timeframe:str; as_of:datetime; base_value:float; quote_value:float; gap:float; abs_gap:float; gap_velocity:float; gap_acceleration:float; persistence:float; state:str; confidence:float; inspection_priority:str; reason_codes:tuple[str,...]=field(default_factory=tuple)
