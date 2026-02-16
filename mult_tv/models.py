from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "user"


class ChangePasswordRequest(BaseModel):
    password: str


class MarkWatchedRequest(BaseModel):
    file_path: str


class PlayRequest(BaseModel):
    path: str


class ReportRequest(BaseModel):
    file_path: str
    comment: str
