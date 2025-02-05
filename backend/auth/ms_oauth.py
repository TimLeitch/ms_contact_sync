from typing import Optional, Dict
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
import logging
from urllib.parse import urlencode
import aiohttp
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Set to DEBUG level

router = APIRouter(prefix="/auth", tags=["auth"])

# OAuth configuration for organizational accounts
OAUTH_SETTINGS = {
    "client_id": os.getenv("MS_CLIENT_ID"),
    "client_secret": os.getenv("MS_CLIENT_SECRET"),
    "authority": f"https://login.microsoftonline.com/{os.getenv('MS_TENANT_ID')}",
    "scope": [
        # Use either specific scopes
        "User.Read",
        "User.Read.All",  # For reading all users
        "Contacts.Read",
        "offline_access"
        # Or use .default, but not both
        # "https://graph.microsoft.com/.default"
    ],
    "response_type": "code",
    "redirect_uri": "/auth/callback",
    "prompt": "consent",
    "token_endpoint": "/oauth2/v2.0/token"
}

# Validate required environment variables
if not OAUTH_SETTINGS["client_id"] or not OAUTH_SETTINGS["client_secret"]:
    raise ValueError(
        "Missing required environment variables: MS_CLIENT_ID and MS_CLIENT_SECRET")


async def exchange_code_for_token(code: str, request: Request) -> Dict:
    """Exchange authorization code for tokens"""
    token_url = f"{OAUTH_SETTINGS['authority']}{
        OAUTH_SETTINGS['token_endpoint']}"

    data = {
        "client_id": OAUTH_SETTINGS["client_id"],
        "client_secret": OAUTH_SETTINGS["client_secret"],
        "scope": " ".join(OAUTH_SETTINGS["scope"]),
        "code": code,
        "redirect_uri": str(request.base_url)[:-1] + OAUTH_SETTINGS["redirect_uri"],
        "grant_type": "authorization_code"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(token_url, data=data) as response:
            if response.status != 200:
                error_details = await response.json()
                logger.error(f"Token exchange failed: {error_details}")
                raise HTTPException(
                    status_code=response.status,
                    detail="Failed to exchange code for token"
                )

            return await response.json()


async def refresh_access_token(refresh_token: str) -> Dict:
    """Refresh the access token using the refresh token"""
    token_url = f"{OAUTH_SETTINGS['authority']}{
        OAUTH_SETTINGS['token_endpoint']}"

    data = {
        "client_id": OAUTH_SETTINGS["client_id"],
        "client_secret": OAUTH_SETTINGS["client_secret"],
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(token_url, data=data) as response:
            if response.status != 200:
                error_details = await response.json()
                logger.error(f"Token refresh failed: {error_details}")
                raise HTTPException(
                    status_code=response.status,
                    detail="Failed to refresh token"
                )

            return await response.json()


@router.get("/login")
async def login(request: Request):
    """Initiates the OAuth login flow with explicit consent"""
    try:
        logger.debug("Login endpoint hit")
        logger.debug(f"OAUTH_SETTINGS: {OAUTH_SETTINGS}")

        base_url = str(request.base_url)[:-1]
        logger.debug(f"Base URL: {base_url}")

        params = {
            "client_id": OAUTH_SETTINGS["client_id"],
            "response_type": OAUTH_SETTINGS["response_type"],
            "redirect_uri": base_url + OAUTH_SETTINGS["redirect_uri"],
            "scope": " ".join(OAUTH_SETTINGS["scope"]),
            "prompt": OAUTH_SETTINGS["prompt"],
            "response_mode": "query",
            "admin_consent": "true"
        }

        auth_url = f"{OAUTH_SETTINGS['authority']
                      }/oauth2/v2.0/authorize?{urlencode(params)}"
        logger.debug(f"Full auth URL: {auth_url}")

        return RedirectResponse(auth_url, status_code=303)  # Added status code
    except Exception as e:
        logger.error(f"Login error: {str(e)}", exc_info=True)  # Added exc_info
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/callback")
async def callback(request: Request):
    """Handles the OAuth callback with consent handling"""
    try:
        # Check for consent errors
        error = request.query_params.get("error")
        error_description = request.query_params.get("error_description")

        if error:
            if error == "access_denied":
                logger.warning("User denied consent")
                return RedirectResponse("/?error=consent_denied")
            elif error == "admin_consent_required":
                logger.warning("Admin consent required")
                return RedirectResponse("/?error=admin_consent_required")
            else:
                logger.error(f"OAuth error: {error} - {error_description}")
                raise HTTPException(status_code=400, detail=error_description)

        code = request.query_params.get("code")
        if not code:
            raise HTTPException(
                status_code=400, detail="No authorization code received")

        # Exchange the code for tokens
        token_response = await exchange_code_for_token(code, request)

        logger.debug("Token response received")
        logger.debug("Token response keys: " + str(token_response.keys()))

        if 'access_token' not in token_response:
            logger.error("No access token in response")
            logger.debug(f"Full token response: {token_response}")
            raise HTTPException(
                status_code=500, detail="Invalid token response")

        # Store tokens and expiration in session
        request.session.update({
            "access_token": token_response["access_token"],
            "refresh_token": token_response["refresh_token"],
            "token_expires": datetime.now().timestamp() + token_response["expires_in"]
        })

        # Force session to save
        request.session.setdefault("_session", True)

        # Use absolute URL for redirect
        base_url = str(request.base_url)[:-1]
        dashboard_url = f"{base_url}/dashboard"

        response = RedirectResponse(
            url=dashboard_url,
            status_code=303
        )

        return response
    except Exception as e:
        logger.error(f"Callback error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Authentication callback failed")


@router.get("/logout")
async def logout(request: Request):
    """Logs out the user and clears the session"""
    try:
        request.session.clear()
        params = {
            "post_logout_redirect_uri": str(request.base_url)[:-1] + "/"
        }
        logout_url = f"{OAUTH_SETTINGS['authority']
                        }/oauth2/v2.0/logout?{urlencode(params)}"
        return RedirectResponse(logout_url)
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        raise HTTPException(status_code=500, detail="Logout failed")


async def get_valid_token(request: Request) -> Optional[str]:
    """Get a valid access token, refreshing if necessary"""
    access_token = request.session.get("access_token")
    expires = request.session.get("token_expires")
    refresh_token = request.session.get("refresh_token")

    logger.debug(f"Session contains token: {bool(access_token)}")
    logger.debug(f"Token expires: {
                 datetime.fromtimestamp(expires) if expires else None}")

    if not access_token or not expires or not refresh_token:
        logger.debug("Missing token data in session")
        return None

    # Check if token is expired or about to expire (within 5 minutes)
    if datetime.now().timestamp() > (expires - 300):
        try:
            logger.debug("Token expired, attempting refresh")
            # Refresh the token
            token_response = await refresh_access_token(refresh_token)

            # Update session with new tokens
            request.session["access_token"] = token_response["access_token"]
            request.session["refresh_token"] = token_response["refresh_token"]
            request.session["token_expires"] = datetime.now(
            ).timestamp() + token_response["expires_in"]

            logger.debug("Token refreshed successfully")
            return token_response["access_token"]
        except Exception as e:
            logger.error(f"Token refresh failed: {str(e)}")
            return None

    return access_token


async def require_token(request: Request) -> str:
    """Dependency that requires a valid token"""
    token = await get_valid_token(request)
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required"
        )
    return token


async def get_users(token: str) -> dict:
    """Fetch users from Microsoft Graph API"""
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {token}"}
        async with session.get("https://graph.microsoft.com/v1.0/users", headers=headers) as response:
            if response.status != 200:
                error_details = await response.json()
                logger.error(f"Failed to fetch users: {error_details}")
                raise HTTPException(
                    status_code=response.status,
                    detail="Failed to fetch users"
                )
            return await response.json()


# Add this helper function to format user data for display
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


@router.get("/test/users")
async def test_users(request: Request):
    """Test endpoint to fetch all users"""
    try:
        token = await get_valid_token(request)
        if not token:
            raise HTTPException(status_code=401, detail="Not authenticated")

        users = await get_users(token)
        return HTMLResponse(format_users_html(users))
    except Exception as e:
        logger.error(f"Error fetching users: {str(e)}", exc_info=True)
        return HTMLResponse(
            "<div class='error'>Failed to fetch users. Please try logging in again.</div>"
        )
