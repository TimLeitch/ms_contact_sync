from typing import Optional
import logging
from fastapi import Request
from fastapi.responses import HTMLResponse
import httpx
from fastapi_msal.models import AuthToken

logger = logging.getLogger(__name__)


async def get_user_contact_folders(request: Request, user_id: str, auth) -> HTMLResponse:
    try:
        token: Optional[AuthToken] = await auth.get_session_token(request=request)
        if not token or not token.access_token:
            return HTMLResponse(content="Unauthorized", status_code=401)

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://graph.microsoft.com/beta/users/{user_id}/contactFolders",
                headers={"Authorization": f"Bearer {token.access_token}"}
            )

            if resp.status_code != 200:
                logger.error(
                    f"Graph API error: {resp.status_code} - {resp.text}")
                return HTMLResponse(
                    content=f"Error fetching folders: {resp.text}",
                    status_code=resp.status_code
                )

            folders = resp.json().get("value", [])
            return HTMLResponse(content=folders)

    except Exception as e:
        logger.exception("Error fetching contact folders")
        return HTMLResponse(content=f"Server error: {str(e)}", status_code=500)
