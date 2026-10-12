"""用户与登录相关 DTO。"""
from typing import Optional

from pydantic import BaseModel, Field


class UserLoginDto(BaseModel):
    account: str = Field(..., description="用户账号")
    password: str = Field(..., description="用户密码")


class UserRegisterDto(BaseModel):
    account: str = Field(..., description="用户账号")
    password: str = Field(..., description="用户密码")


class ChangePasswordDto(BaseModel):
    old_password: str = Field(..., description="原密码")
    new_password: str = Field(..., description="新密码")


class LoginResponse(BaseModel):
    user_id: str = Field(..., description="用户ID（业务表使用的字符串标识）")
    user_pk: int = Field(..., description="user 表主键")
    account: str = Field(..., description="账号")
    token: str = Field(..., description="登录令牌")
    expires_in_hours: int = Field(..., description="令牌有效期（小时）")
    create_time: Optional[str] = Field(None, description="注册时间")
