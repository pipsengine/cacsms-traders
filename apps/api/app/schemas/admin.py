from pydantic import BaseModel,Field
from typing import Optional
class TenantCreate(BaseModel): name:str; slug:str; reporting_currency:str='USD'
class UserCreate(BaseModel): username:str; email:Optional[str]=None; first_name:str; middle_name:Optional[str]=None; last_name:str; password:str=Field(min_length=8); role_id:Optional[str]=None
class UserPatch(BaseModel): first_name:Optional[str]=None; middle_name:Optional[str]=None; last_name:Optional[str]=None; phone:Optional[str]=None; timezone:Optional[str]=None; preferred_currency:Optional[str]=None; status:Optional[str]=None
class AccountCreate(BaseModel): account_name:str; account_number:Optional[str]=None; broker:Optional[str]=None; server:Optional[str]=None; environment:str='DEMO'; account_currency:str='USD'; leverage:Optional[str]=None
class AccountPatch(BaseModel): account_name:Optional[str]=None; status:Optional[str]=None; trading_enabled:Optional[bool]=None; autonomous_trading_enabled:Optional[bool]=None
class SystemModeUpdate(BaseModel): mode:str; reason:str
class ConnectionCreate(BaseModel): trading_account_id:str; adapter_type:str='LOCAL_MT5'; terminal_path:Optional[str]=None; server_name:Optional[str]=None
