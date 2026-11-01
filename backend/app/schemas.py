from pydantic import BaseModel, EmailStr, Field
class Login(BaseModel): email: EmailStr; password: str
class Register(BaseModel): organization: str=Field(min_length=1,max_length=180); email: EmailStr; password: str=Field(min_length=12,max_length=128)
class ProfileCreate(BaseModel): name: str=Field(min_length=1,max_length=180); product: str; variant: str=""; defects: list[str]=[]; capture: dict={}; thresholds: dict={}
class ProfileUpdate(BaseModel): name: str|None=None; product: str|None=None; variant: str|None=None; defects: list[str]|None=None; capture: dict|None=None; thresholds: dict|None=None
class LabelUpdate(BaseModel): label: str=Field(pattern="^(good|defect|unknown)$"); split: str|None=Field(default=None,pattern="^(train|validation|test)$")
class ReviewUpdate(BaseModel): corrected_result: str=Field(pattern="^(pass|fail|needs_review|unknown)$"); note: str=""
