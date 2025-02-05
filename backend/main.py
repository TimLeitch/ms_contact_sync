import uvicorn
from fastapi import FastAPI, Depends, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from fastapi_msal import MSALAuthorization, UserInfo, MSALClientConfig
from dotenv import load_dotenv
import os

load_dotenv()

# Set scopes at class level
MSALClientConfig.scopes = ["User.Read", "User.Read.All"]

# Configure MSAL
client_config = MSALClientConfig()
client_config.client_id = os.getenv("MS_CLIENT_ID")
client_config.client_credential = os.getenv("MS_CLIENT_SECRET")
client_config.tenant = os.getenv("MS_TENANT_ID")
client_config.redirect_uri = "http://localhost:5000/auth/callback"

app = FastAPI()
app.add_middleware(SessionMiddleware,
                   secret_key=os.getenv("SESSION_SECRET_KEY"))

# Static and template setup
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
templates = Jinja2Templates(directory="frontend/templates")

# Auth setup
msal_auth = MSALAuthorization(client_config=client_config)
app.include_router(msal_auth.router)


@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/dashboard")
async def dashboard(request: Request, user: UserInfo = Depends(msal_auth.scheme)):
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user})


@app.get("/api/users/list")
async def list_users(user: UserInfo = Depends(msal_auth.scheme)):
    return {"users": [
        {"displayName": user.name, "userPrincipalName": user.preferred_username}
    ]}

if __name__ == "__main__":
    uvicorn.run("main:app", host="localhost", port=5000, reload=True)
