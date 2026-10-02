from pydantic import BaseModel
from typing import Optional
class LoginRequest(BaseModel): username:str; password:str
class ChangePasswordRequest(BaseModel): current_password:str; new_password:str
class ProfilePatch(BaseModel):
 first_name:Optional[str]=None; middle_name:Optional[str]=None; last_name:Optional[str]=None
 phone:Optional[str]=None; timezone:Optional[str]=None; preferred_currency:Optional[str]=None
