from typing import Annotated
from fastapi import Depends, HTTPException, status, Request
import jwt
from jwt.exceptions import InvalidTokenError
from app.config import get_settings
from app.models.user import User
from app.dependencies.session import SessionDep
from app.repositories.user import UserRepository

def _extract_bearer_token(request: Request) -> str | None:
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return None


async def _resolve_user_from_token(token: str | None, request: Request, db: SessionDep) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise credentials_exception
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[get_settings().jwt_algorithm])
        user_id = payload.get("sub", None)
    except InvalidTokenError as e:
        print("Invalid token error: ", e)
        raise credentials_exception

    repo = UserRepository(db)
    user = repo.get_by_id(user_id)
    if user is None:
        raise credentials_exception
    return user


async def get_current_user(request: Request, db: SessionDep) -> User:
    token = _extract_bearer_token(request)
    if token is None:
        token = request.cookies.get("access_token")
    return await _resolve_user_from_token(token, request, db)


async def get_api_current_user(request: Request, db: SessionDep) -> User:
    return await _resolve_user_from_token(_extract_bearer_token(request), request, db)


async def is_logged_in(request: Request, db: SessionDep):
    try:
        await get_current_user(request, db)
        return True
    except Exception:
        return False


IsUserLoggedIn = Annotated[bool, Depends(is_logged_in)]
AuthDep = Annotated[User, Depends(get_current_user)]
ApiAuthDep = Annotated[User, Depends(get_api_current_user)]


async def is_admin(user: User):
    return user.role == "admin"


async def is_admin_dep(user: AuthDep):
    if not await is_admin(user):
        raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource.",
            )
    return user


async def is_api_admin_dep(user: ApiAuthDep):
    if not await is_admin(user):
        raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource.",
            )
    return user


AdminDep = Annotated[User, Depends(is_admin_dep)]
ApiAdminDep = Annotated[User, Depends(is_api_admin_dep)]
