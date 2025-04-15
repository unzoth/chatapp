"""
认证路由模块

处理用户注册和登录相关的路由
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from db import get_db
from models import User
from schemas import (
    RegisterRequest, RegisterResponse,
    LoginRequest, LoginResponse,
    TokenVerifyRequest, TokenVerifyResponse,
    ChangePasswordRequest, ChangePasswordResponse
)
from utils import (
    hash_password, get_user_by_username,
    set_user_token, verify_token, invalidate_token
)

router = APIRouter(tags=["认证"])


@router.post("/register", response_model=RegisterResponse)
async def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """
    用户注册

    Args:
        request: 注册请求
        db: 数据库会话

    Returns:
        注册响应

    Raises:
        HTTPException: 当用户名已存在时
    """
    existing_user = get_user_by_username(db, request.username)
    if existing_user:
        raise HTTPException(status_code=400, detail="用户名已存在")

    hashed_password = hash_password(request.password)
    user = User(username=request.username, password_hash=hashed_password)
    db.add(user)
    db.commit()
    db.refresh(user)

    # 为新注册用户创建令牌
    token = set_user_token(db, user)

    return RegisterResponse(message="注册成功", user_id=user.user_id, token=token)


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    """
    用户登录

    Args:
        request: 登录请求
        db: 数据库会话

    Returns:
        登录响应

    Raises:
        HTTPException: 当账号或密码错误时
    """
    user = get_user_by_username(db, request.username)
    if not user:
        raise HTTPException(status_code=400, detail="账号或密码错误")

    hashed_password = hash_password(request.password)
    if user.password_hash != hashed_password:
        raise HTTPException(status_code=400, detail="账号或密码错误")

    # 生成并保存用户令牌
    token = set_user_token(db, user)

    return LoginResponse(message="登录成功", user_id=user.user_id, token=token)


@router.post("/verify_token", response_model=TokenVerifyResponse)
async def verify_user_token(request: TokenVerifyRequest, db: Session = Depends(get_db)):
    """
    验证用户令牌

    Args:
        request: 令牌验证请求
        db: 数据库会话

    Returns:
        令牌验证响应
    """
    is_valid = verify_token(db, request.username, request.token)

    if is_valid:
        return TokenVerifyResponse(valid=True, message="令牌有效")
    else:
        return TokenVerifyResponse(valid=False, message="令牌无效或已过期")


@router.post("/logout")
async def logout(request: TokenVerifyRequest, db: Session = Depends(get_db)):
    """
    用户登出

    Args:
        request: 包含用户名和令牌的请求
        db: 数据库会话

    Returns:
        登出结果消息
    """
    success = invalidate_token(db, request.username)

    if success:
        return {"message": "登出成功"}
    else:
        raise HTTPException(status_code=400, detail="登出失败，用户不存在")

@router.post("/change_password", response_model=ChangePasswordResponse)
async def change_password(request: ChangePasswordRequest, db: Session = Depends(get_db)):
    """
    修改用户密码

    Args:
        request: 修改密码请求
        db: 数据库会话

    Returns:
        修改密码响应

    Raises:
        HTTPException: 当用户不存在或密码验证失败时
    """
    # 获取用户
    user = get_user_by_username(db, request.username)
    if not user:
        raise HTTPException(status_code=400, detail="用户不存在")

    # 验证旧密码
    old_password_hash = hash_password(request.old_password)
    if user.password_hash != old_password_hash:
        raise HTTPException(status_code=400, detail="原密码错误")

    # 修改密码
    user.password_hash = hash_password(request.new_password)
    db.commit()
    db.refresh(user)

    # 使当前令牌失效，强制用户重新登录
    invalidate_token(db, request.username)

    return ChangePasswordResponse(
        message="密码修改成功，请重新登录",
        success=True
    )
