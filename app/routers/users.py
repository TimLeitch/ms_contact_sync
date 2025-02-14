import logging
import httpx
from typing import Optional
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from app.dependencies import auth, config, templates, AuthToken

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["users"])


def chunk_list(lst, chunk_size):
    """Yield successive chunks from lst."""
    lst = list(lst)
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]


@router.get("/users", response_class=HTMLResponse)
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


@router.get("/users/{user_id}/folders", response_class=HTMLResponse)
async def get_user_folders(request: Request, user_id: str):
    logger.info(f"Starting get_user_folders request for user_id: {user_id}")
    try:
        token: Optional[AuthToken] = await auth.get_session_token(request=request)
        if not token:
            logger.warning("No token found in session")
            return RedirectResponse(url=config.login_path)
        logger.info(f"Fetching folders for user: {user_id}")

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://graph.microsoft.com/v1.0/users/{user_id}/contactFolders",
                headers={
                    "Authorization": f"Bearer {token.access_token}",
                    "ConsistencyLevel": "eventual"
                }
            )

        if resp.status_code != 200:
            logger.error(f"Graph API error: {resp.status_code} - {resp.text}")
            return HTMLResponse(content=f"Error: {resp.status_code} {resp.text}")

        folders = resp.json().get("value", [])
        return templates.TemplateResponse("folders.html", {"request": request, "folders": folders})

    except Exception as e:
        logger.exception(
            f"Unexpected error in get_user_folders for user {user_id}")
        return HTMLResponse(content=f"Server error: {str(e)}", status_code=500)


@router.get("/user/{user_id}/contacts", response_class=HTMLResponse)
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
        return templates.TemplateResponse("contacts.html", {"request": request, "contacts": contacts})
    except Exception as e:
        logger.exception("Error fetching contacts")
        return HTMLResponse(content=f"Server error: {str(e)}", status_code=500)
