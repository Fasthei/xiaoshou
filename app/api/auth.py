"""Auth endpoints: /login redirect, /callback code exchange, /me introspection."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.auth.casdoor import authorize_url, exchange_code_for_token, verify_jwt, CasdoorAuthError
from app.auth.dependencies import CurrentUser, require_auth

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.get("/login", summary="跳转到 Casdoor 登录页")
def login(state: str = Query("xiaoshou")):
    return RedirectResponse(url=authorize_url(state=state))


@router.get("/callback", summary="Casdoor OAuth2 回调")
def callback(code: str = Query(...), state: str = Query("")):
    try:
        token_resp = exchange_code_for_token(code=code, state=state)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"token exchange failed: {e}")
    # Validate the returned access_token / id_token before handing it back
    tok = token_resp.get("access_token") or token_resp.get("id_token")
    if not tok:
        raise HTTPException(status_code=400, detail=f"no token in response: {token_resp}")
    try:
        verify_jwt(tok)
    except CasdoorAuthError as e:
        raise HTTPException(status_code=400, detail=f"token verify failed: {e}")
    return token_resp


@router.get("/me", summary="当前登录用户")
def me(user: CurrentUser = Depends(require_auth)):
    return {
        "sub": user.sub,
        "name": user.name,
        "email": user.email,
        "owner": user.owner,
        "roles": user.roles,
    }
