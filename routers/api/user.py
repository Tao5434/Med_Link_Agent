"""用户模块接口：注册 / 登录 / 退出 / 资料 / 改密。

账号体系完全基于数据库 ``user`` 表（密码 MD5），登录成功后签发 ``user_tokens`` 令牌。
默认管理员账号：``admin`` / ``123456``（由建库种子数据写入）。
"""
from fastapi import APIRouter, Depends, HTTPException

from schema.dto.user_dto import ChangePasswordDto, LoginResponse, UserLoginDto, UserRegisterDto
from service.auth_service import AuthError, AuthService
from utils.response_model import error_message, success_data, success_data_message
from utils.security import current_user

user_router = APIRouter(prefix="/api/user", tags=["用户与登录"])


@user_router.post("/register", summary="用户注册（注册成功即登录）")
async def user_register(dto: UserRegisterDto):
    try:
        return success_data_message(AuthService.register(dto), "注册成功")
    except AuthError as exc:
        return error_message(str(exc))


@user_router.post("/login", response_model=LoginResponse, summary="用户登录")
async def user_login(dto: UserLoginDto):
    try:
        return AuthService.login(dto)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@user_router.post("/logout", summary="退出登录（令牌立即失效）")
async def user_logout(user: dict = Depends(current_user)):
    AuthService.logout(user.get("token"))
    return success_data_message({"ok": True}, "已退出登录")


@user_router.get("/profile", summary="当前登录用户信息")
async def user_profile(user: dict = Depends(current_user)):
    return success_data(AuthService.profile(user))


@user_router.post("/password", summary="修改密码")
async def change_password(dto: ChangePasswordDto, user: dict = Depends(current_user)):
    try:
        AuthService.change_password(user, dto.old_password, dto.new_password)
        return success_data_message({"ok": True}, "密码已修改，请重新登录")
    except AuthError as exc:
        return error_message(str(exc))
