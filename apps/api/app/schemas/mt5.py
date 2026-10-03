from pydantic import BaseModel, Field
from typing import Optional


class Mt5SettingsPatch(BaseModel):
    terminal_path: Optional[str] = None
    login_type: Optional[str] = None
    auto_reconnect: Optional[bool] = None
    heartbeat_interval_seconds: Optional[int] = Field(None, ge=5, le=300)


class Mt5ConnectRequest(BaseModel):
    terminal_path: Optional[str] = None
