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
        token: Optional[AuthToken] = await auth.get_session_token(request=request)
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
        token: Optional[AuthToken] = await auth.get_session_token(request=request)
        if not token or not token.access_token:
            return RedirectResponse(url=config.login_path)

        async with httpx.AsyncClient(timeout=30.0) as client:  # Increased timeout
            # Get groups first
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

            # Prepare batch request for member counts
            batch_size = 20  # MS Graph batch limit
            batch_requests = []
            request_id_to_group = {}  # Map request IDs to group IDs

            for i, group in enumerate(groups):
                request_id = f"request-{i}"  # Create unique request ID
                request_id_to_group[request_id] = group["id"]
                batch_requests.append({
                    "id": request_id,
                    "method": "GET",
                    "url": f"/groups/{group['id']}/members/$count",
                    "headers": {
                        "ConsistencyLevel": "eventual"
                    }
                })

            # Send batch requests in chunks with retry logic
            for batch_chunk in chunk_list(batch_requests, batch_size):
                try:
                    batch_resp = await client.post(
                        "https://graph.microsoft.com/v1.0/$batch",
                        headers={
                            "Authorization": "Bearer " + token.access_token,
                        },
                        json={"requests": batch_chunk},
                        timeout=30.0  # Explicit timeout for batch request
                    )

                    if batch_resp.status_code != 200:
                        logger.error(f"Batch request failed: {
                                     batch_resp.status_code} - {batch_resp.text}")
                        # Set default member count for failed batch
                        for req in batch_chunk:
                            group_id = request_id_to_group.get(req["id"])
                            if group_id:
                                group = next(
                                    (g for g in groups if g["id"] == group_id), None)
                                if group:
                                    group["memberCount"] = "Error"
                        continue

                    batch_results = batch_resp.json().get("responses", [])

                    # Update groups with member counts using request ID mapping
                    for response in batch_results:
                        request_id = response["id"]
                        group_id = request_id_to_group.get(request_id)

                        if not group_id:
                            logger.error(
                                f"Unknown request ID received: {request_id}")
                            continue

                        if response["status"] == 200:
                            group = next(
                                (g for g in groups if g["id"] == group_id), None)
                            if group:
                                group["memberCount"] = int(response["body"])
                            else:
                                logger.error(
                                    f"Could not find group for ID: {group_id}")

                except httpx.ReadTimeout:
                    logger.error("Timeout during batch request")
                    # Set default member count for timed out batch
                    for req in batch_chunk:
                        group_id = request_id_to_group.get(req["id"])
                        if group_id:
                            group = next(
                                (g for g in groups if g["id"] == group_id), None)
                            if group:
                                group["memberCount"] = "Timeout"
                    continue

            return templates.TemplateResponse("groups.html", {
                "request": request,
                "groups": groups
            })

    except Exception as e:
        logger.exception("Error in get_groups endpoint")
        return HTMLResponse(content=f"Server error: {str(e)}", status_code=500)


@app.get("/api/groups/{group_id}/members", response_class=HTMLResponse)
async def get_group_members(request: Request, group_id: str):
    try:
        token: Optional[AuthToken] = await auth.get_session_token(request=request)
        if not token or not token.access_token:
            return RedirectResponse(url=config.login_path)

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://graph.microsoft.com/v1.0/groups/{group_id}/members",
                headers={
                    "Authorization": "Bearer " + token.access_token,
                    "ConsistencyLevel": "eventual"
                },
                params={
                    "$select": "id,displayName,userPrincipalName,mobilePhone,businessPhones"
                }
            )

            if resp.status_code != 200:
                error_msg = f"Failed to fetch members: {
                    resp.status_code} - {resp.text}"
                logger.error(error_msg)
                return templates.TemplateResponse("group_members.html", {
                    "request": request,
                    "members": [],
                    "error": error_msg
                })

            members = resp.json().get("value", [])
            logger.info(f"Successfully fetched {len(members)} members")
            return templates.TemplateResponse("group_members.html", {
                "request": request,
                "members": members
            })

    except Exception as e:
        error_msg = f"Error fetching group members: {str(e)}"
        logger.exception(error_msg)
        return templates.TemplateResponse("group_members.html", {
            "request": request,
            "members": [],
            "error": error_msg
        })


@app.get("/api/user/{user_id}/contacts", response_class=HTMLResponse)
async def get_user_contacts(request: Request, user_id: str):
    try:
        token: Optional[AuthToken] = await auth.get_session_token(request=request)
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
