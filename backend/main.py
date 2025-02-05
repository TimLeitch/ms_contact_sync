import uvicorn
from fastapi import FastAPI, Depends, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from fastapi_msal import MSALAuthorization, UserInfo, MSALClientConfig
from dotenv import load_dotenv
import os
from fastapi.responses import RedirectResponse
import httpx

load_dotenv()

# Set scopes at class level
MSALClientConfig.scopes = [
    "User.Read",
    "User.Read.All",
    "Directory.Read.All"  # Add this if you need to read all users
]

# Configure MSAL
client_config = MSALClientConfig()
client_config.client_id = os.getenv("MS_CLIENT_ID")
client_config.client_credential = os.getenv("MS_CLIENT_SECRET")
client_config.tenant = os.getenv("MS_TENANT_ID")
client_config.redirect_uri = "http://localhost:5000/token"
client_config.login_path = "/auth/login"
client_config.logout_path = "/auth/logout"


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
    try:
        # Try to get the user info - if this succeeds, they're authenticated
        user = await msal_auth.scheme(request)
        return RedirectResponse(url="/dashboard")
    except:
        # If not authenticated, show login page
        return templates.TemplateResponse("login.html", {"request": request})


@app.get("/token")
async def token_callback(request: Request):
    try:
        # Get the user info which includes the token
        user = await msal_auth.scheme(request)
        # Debug: Print what we got from MSAL
        print("User object contents:", dir(user))
        print("User claims:", user.claims if hasattr(
            user, 'claims') else "No claims")

        # Try to get token from different possible locations
        token = None
        if hasattr(user, 'token'):
            token = user.token
        elif hasattr(user, 'access_token'):
            token = user.access_token
        elif hasattr(user, '_token'):
            token = user._token
        elif hasattr(user, 'aio') and hasattr(user.aio, 'token'):
            token = user.aio.token

        if token:
            request.session['access_token'] = token
            print("Token successfully stored:",
                  token[:50] if token else "No token")
        else:
            print("No token found in user object")
            # Try to get token from query parameters
            code = request.query_params.get('code')
            if code:
                print("Found authorization code, attempting to get token")
                # You might need to implement token exchange here

        return RedirectResponse(url="/dashboard")
    except Exception as e:
        print(f"Error in token callback: {str(e)}")
        import traceback
        traceback.print_exc()
        return RedirectResponse(url="/")


@app.get("/dashboard")
async def dashboard(request: Request, user: UserInfo = Depends(msal_auth.scheme)):
    # Get user info from claims
    user_info = {
        # Fallback to "User" if name not available
        "name": user.preferred_username or "User",
    }
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user_info})


@app.get("/api/users/list")
async def list_users(request: Request, user: UserInfo = Depends(msal_auth.scheme)):
    try:
        # Try to get the token from the MSAL auth context
        auth_result = await msal_auth.get_token(request)
        if auth_result and 'access_token' in auth_result:
            access_token = auth_result['access_token']
        else:
            # Fallback to session token
            access_token = request.session.get('access_token')

        if not access_token:
            print("No access token found")
            return {"error": "No access token available", "status": 401}

        print("Using token (first 50 chars):", access_token[:50])

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://graph.microsoft.com/v1.0/users",
                headers=headers
            )

            if response.status_code != 200:
                print("Graph API Error:", response.status_code)
                print("Response:", response.text)
                print("Headers sent:", headers)

            return {"users": response.json().get("value", [])} if response.status_code == 200 \
                else {"error": "Failed to fetch users", "status": response.status_code}
    except Exception as e:
        print(f"Error in list_users: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"error": str(e), "status": 500}

if __name__ == "__main__":
    uvicorn.run("main:app", host="localhost", port=5000, reload=True)
