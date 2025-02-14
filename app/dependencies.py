from typing import Optional
import os
import logging
from fastapi import Request
from fastapi_msal import MSALAuthorization, MSALClientConfig
from fastapi_msal.models import AuthToken
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)


class AppConfig(MSALClientConfig):
    scopes: list[str] = [
        "User.Read",
        "User.Read.All",
        "Directory.Read.All",
        "Contacts.Read",
        "Contacts.ReadWrite",
        "Contacts.ReadWrite.Shared",
        "Directory.Read.All",
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
auth = MSALAuthorization(client_config=config)
templates = Jinja2Templates(directory="app/templates")


async def get_auth_token(request: Request) -> Optional[AuthToken]:
    """Common dependency for getting auth token"""
    return await auth.get_session_token(request=request)
