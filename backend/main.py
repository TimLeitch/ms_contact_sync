from typing import Optional

import httpx
import uvicorn
import msal
from starlette.middleware.sessions import SessionMiddleware
from fastapi import FastAPI, Request, Query
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi_msal import MSALAuthorization, MSALClientConfig
from fastapi_msal.models import AuthToken
from fastapi.staticfiles import StaticFiles


class AppConfig(MSALClientConfig):
    login_path: str = "/auth/login"  # default is '/_login_route'
    logout_path: str = "/auth/logout"  # default is '/_logout_route'


config = AppConfig(_env_file="app_config.env")

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=config.client_credential)
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
auth = MSALAuthorization(client_config=config)
app.include_router(auth.router)


templates = Jinja2Templates(directory="frontend/templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    token: Optional[AuthToken] = await auth.get_session_token(request=request)
    if not token or not token.id_token_claims:
        return RedirectResponse(url=config.login_path)
    context = {
        "request": request,
        "user": token.id_token_claims,
        "version": msal.__version__,
    }
    return templates.TemplateResponse(name="index.html", context=context)


@app.get("/api/users", response_class=HTMLResponse)
async def get_users(request: Request):
    token: Optional[AuthToken] = await auth.handler.get_token_from_session(request=request)
    if not token or not token.access_token:
        return RedirectResponse(url=config.login_path)
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://graph.microsoft.com/v1.0/users", headers={
                "Authorization": "Bearer " + token.access_token},
            params={
                "$select": "displayName,userPrincipalName,mobilePhone,businessPhones,id"}
        )

    if resp.status_code != 200:
        return HTMLResponse(content=f"Error: {resp.status_code} {resp.text}")

    users = resp.json().get("value", [])

    return templates.TemplateResponse("users.html", {"request": request, "users": users})


@app.get("/api/groups", response_class=HTMLResponse)
async def get_groups(request: Request):
    token: Optional[AuthToken] = await auth.handler.get_token_from_session(request=request)
    if not token or not token.access_token:
        return RedirectResponse(url=config.login_path)

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://graph.microsoft.com/v1.0/groups", headers={
                "Authorization": "Bearer " + token.access_token},
            params={"$select": "displayName,id"}
        )

    if resp.status_code != 200:
        return HTMLResponse(content=f"Error: {resp.status_code} {resp.text}")

    groups = resp.json().get("value", [])

    return templates.TemplateResponse("groups.html", {"request": request, "groups": groups})


@app.get("/api/user/{user_id}/contacts", response_class=HTMLResponse)
async def get_user_contacts(request: Request, user_id: str):
    token: Optional[AuthToken] = await auth.handler.get_token_from_session(request=request)
    if not token or not token.access_token:
        return RedirectResponse(url=config.login_path)

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://graph.microsoft.com/v1.0/users/{user_id}/contacts",
            headers={"Authorization": "Bearer " + token.access_token}
        )

    if resp.status_code != 200:
        return HTMLResponse(content=f"Error: {resp.status_code} {resp.text}")

    contacts = resp.json().get("value", [])
    return templates.TemplateResponse(
        "contacts.html",
        {"request": request, "contacts": contacts}
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="localhost", port=5000, reload=True)
