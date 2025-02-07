from typing import Optional
import os
import logging
from itertools import islice

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
from dotenv import load_dotenv

# Load .env file if it exists (for local development)
load_dotenv()

# Add at the top of the file
logger = logging.getLogger(__name__)


class AppConfig(MSALClientConfig):
    scopes: list[str] = [
        "User.Read",
        "User.Read.All",
        "Directory.Read.All",
        "Contacts.Read",
    ]

    def __init__(self):
        super().__init__(
            login_path="/auth/login",
            logout_path="/auth/logout",
            client_id=os.getenv("MS_CLIENT_ID"),
            client_credential=os.getenv("MS_CLIENT_SECRET"),
            tenant=os.getenv("MS_TENANT_ID"),
            redirect_uri="http://localhost:5000/token"
        )


config = AppConfig()

app = FastAPI()
app.add_middleware(SessionMiddleware,
                   secret_key=os.getenv("SESSION_SECRET_KEY"))
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
    try:
        token: Optional[AuthToken] = await auth.handler.get_token_from_session(request=request)
        if not token or not token.access_token:
            return RedirectResponse(url=config.login_path)

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://graph.microsoft.com/v1.0/users",
                headers={"Authorization": f"Bearer {token.access_token}"},
                params={
                    "$select": "displayName,userPrincipalName,mobilePhone,businessPhones,id"
                }
            )

        if resp.status_code == 403:
            logger.error(f"Permission denied: {resp.text}")
            return HTMLResponse(
                content="Permission denied. Please ensure the app has proper Microsoft Graph API permissions.",
                status_code=403
            )

        users = resp.json().get("value", [])
        return templates.TemplateResponse("users.html", {"request": request, "users": users})

    except Exception as e:
        logger.exception("Error in get_users endpoint")
        return HTMLResponse(content=f"Server error: {str(e)}", status_code=500)


def chunk_list(lst, chunk_size):
    """Yield successive chunks from lst."""
    lst = list(lst)
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]


@app.get("/api/groups", response_class=HTMLResponse)
async def get_groups(request: Request):
    try:
        token: Optional[AuthToken] = await auth.handler.get_token_from_session(request=request)
        if not token or not token.access_token:
            return RedirectResponse(url=config.login_path)

        BATCH_SIZE = 20  # Microsoft Graph API batch limit
        logger.info("Fetching groups from Microsoft Graph API")

        async with httpx.AsyncClient() as client:
            # First get all groups
            resp = await client.get(
                "https://graph.microsoft.com/v1.0/groups",
                headers={"Authorization": "Bearer " + token.access_token},
                params={
                    "$select": "displayName,id",
                }
            )

            if resp.status_code != 200:
                logger.error(f"Failed to fetch groups: {
                             resp.status_code} - {resp.text}")
                return HTMLResponse(content="Failed to fetch groups", status_code=resp.status_code)

            groups = resp.json().get("value", [])
            logger.info(
                f"Found {len(groups)} groups, preparing batch requests")

            # Process groups in chunks
            for chunk_index, groups_chunk in enumerate(chunk_list(groups, BATCH_SIZE)):
                logger.info(f"Processing batch {
                            chunk_index + 1} with {len(groups_chunk)} groups")

                batch_requests = {
                    "requests": [
                        {
                            "id": str(i),
                            "method": "GET",
                            "url": f"/groups/{group['id']}/members?$count=true&$select=id,displayName,userPrincipalName",
                            "headers": {
                                "ConsistencyLevel": "eventual"
                            }
                        }
                        for i, group in enumerate(groups_chunk)
                    ]
                }

                batch_resp = await client.post(
                    "https://graph.microsoft.com/v1.0/$batch",
                    headers={
                        "Authorization": "Bearer " + token.access_token,
                        "Content-Type": "application/json"
                    },
                    json=batch_requests
                )

                if batch_resp.status_code == 200:
                    batch_results = batch_resp.json().get("responses", [])
                    logger.info(f"Received {len(batch_results)} responses for batch {
                                chunk_index + 1}")

                    # Update groups with member counts and store members
                    for i, result in enumerate(batch_results):
                        group_index = (chunk_index * BATCH_SIZE) + i
                        if result.get("status") == 200:
                            response_body = result.get("body", {})
                            groups[group_index]["memberCount"] = response_body.get(
                                "@odata.count", 0)
                            groups[group_index]["members"] = response_body.get(
                                "value", [])
                            logger.debug(f"Group {groups[group_index]['displayName']} has {
                                         groups[group_index]['memberCount']} members")
                        else:
                            logger.warning(f"Failed to get members for group {
                                           groups[group_index]['displayName']}: {result.get('status')}")
                            groups[group_index]["memberCount"] = 0
                            groups[group_index]["members"] = []
                else:
                    logger.error(
                        f"Batch {chunk_index + 1} failed: {batch_resp.status_code} - {batch_resp.text}")

        return templates.TemplateResponse("groups.html", {
            "request": request,
            "groups": groups
        })

    except Exception as e:
        logger.exception("Error in get_groups endpoint")
        return HTMLResponse(content=f"Server error: {str(e)}", status_code=500)


@app.get("/api/user/{user_id}/contacts", response_class=HTMLResponse)
async def get_user_contacts(request: Request, user_id: str):
    try:
        token: Optional[AuthToken] = await auth.handler.get_token_from_session(request=request)
        if not token or not token.access_token:
            return RedirectResponse(url=config.login_path)

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://graph.microsoft.com/v1.0/users/{user_id}/contacts",
                headers={"Authorization": "Bearer " + token.access_token}
            )

        if resp.status_code != 200:
            logger.error(f"Graph API error: {resp.status_code} - {resp.text}")
            return HTMLResponse(content=f"Error: {resp.status_code} {resp.text}")

        contacts = resp.json().get("value", [])
        return templates.TemplateResponse(
            "contacts.html",
            {"request": request, "contacts": contacts}
        )
    except Exception as e:
        logger.exception("Error fetching contacts")
        return HTMLResponse(content=f"Server error: {str(e)}", status_code=500)


if __name__ == "__main__":
    uvicorn.run("main:app", host="localhost", port=5000, reload=True)
