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

router = APIRouter(prefix="/auth", tags=["auth"])

# OAuth configuration for organizational accounts
OAUTH_SETTINGS = {
    "client_id": os.getenv("MS_CLIENT_ID"),
    "client_secret": os.getenv("MS_CLIENT_SECRET"),
    "authority": "https://login.microsoftonline.com/common",
    "scope": [
        "User.Read",
        "Contacts.Read",
        "offline_access"
    ],
    "response_type": "code",
    "redirect_uri": "/auth/callback",
    "prompt": "select_account",
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
    """Initiates the OAuth login flow"""
    try:
        params = {
            "client_id": OAUTH_SETTINGS["client_id"],
            "response_type": OAUTH_SETTINGS["response_type"],
            "redirect_uri": str(request.base_url)[:-1] + OAUTH_SETTINGS["redirect_uri"],
            "scope": " ".join(OAUTH_SETTINGS["scope"]),
            "prompt": OAUTH_SETTINGS["prompt"],
            "response_mode": "query"  # Changed to query for code flow
        }

        auth_url = f"{OAUTH_SETTINGS['authority']
                      }/oauth2/v2.0/authorize?{urlencode(params)}"
        return RedirectResponse(auth_url)
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        raise HTTPException(status_code=500, detail="Authentication failed")


@router.get("/callback")
async def callback(request: Request):
    """Handles the OAuth callback and token exchange"""
    try:
        code = request.query_params.get("code")
        if not code:
            raise HTTPException(
                status_code=400, detail="No authorization code received")

        # Exchange the code for tokens
        token_response = await exchange_code_for_token(code, request)

        # Store tokens and expiration in session
        request.session["access_token"] = token_response["access_token"]
        request.session["refresh_token"] = token_response["refresh_token"]
        request.session["token_expires"] = datetime.now(
        ).timestamp() + token_response["expires_in"]

        return RedirectResponse("/dashboard")
    except Exception as e:
        logger.error(f"Callback error: {str(e)}")
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

    if not access_token or not expires or not refresh_token:
        return None

    # Check if token is expired or about to expire (within 5 minutes)
    if datetime.now().timestamp() > (expires - 300):
        try:
            # Refresh the token
            token_response = await refresh_access_token(refresh_token)

            # Update session with new tokens
            request.session["access_token"] = token_response["access_token"]
            request.session["refresh_token"] = token_response["refresh_token"]
            request.session["token_expires"] = datetime.now(
            ).timestamp() + token_response["expires_in"]

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
