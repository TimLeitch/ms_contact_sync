from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
import logging
from typing import Dict, List
import aiohttp
from ..auth.ms_oauth import get_valid_token

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["users"])


async def fetch_users(token: str) -> Dict:
    """Fetch users from Microsoft Graph API"""
    async with aiohttp.ClientSession() as session:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        async with session.get(
            "https://graph.microsoft.com/v1.0/users",
            headers=headers
        ) as response:
            if response.status != 200:
                error_details = await response.json()
                logger.error(f"Failed to fetch users: {error_details}")
                raise HTTPException(
                    status_code=response.status,
                    detail="Failed to fetch users"
                )
            return await response.json()


def format_users_html(users_data: dict) -> str:
    """Format users data as HTML"""
    users = users_data.get('value', [])
    html = "<div class='users-list'>"
    html += "<h2>Users in Organization</h2>"
    for user in users:
        html += f"""
        <div class='user-card'>
            <p><strong>Name:</strong> {user.get('displayName', 'N/A')}</p>
            <p><strong>Email:</strong> {user.get('userPrincipalName', 'N/A')}</p>
        </div>
        """
    html += "</div>"
    return html


@router.get("/list")
async def list_users(request: Request):
    """Get all users in HTML format for HTMX"""
    try:
        token = await get_valid_token(request)
        if not token:
            logger.error("No valid token found in session")
            return HTMLResponse(
                "<div class='error'>Please log in again</div>",
                status_code=401
            )

        users = await fetch_users(token)
        return HTMLResponse(format_users_html(users))
    except Exception as e:
        logger.error(f"Error fetching users: {str(e)}", exc_info=True)
        return HTMLResponse(
            "<div class='error'>Failed to fetch users. Please try logging in again.</div>"
        )
