from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from .auth.ms_oauth import router as auth_router
from .api.users import router as users_router
import logging
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

app = FastAPI(title="Contact Sync App")

# Add templates and static files first
templates = Jinja2Templates(directory="frontend/templates")
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# 1. Add session middleware FIRST
session_secret = os.getenv("SESSION_SECRET_KEY")
if not session_secret:
    raise ValueError(
        "Missing required environment variable: SESSION_SECRET_KEY")

app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret,
    max_age=3600,
    same_site="lax",
    https_only=False,
    session_cookie="session"
)

# 2. Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Add your allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Add security headers middleware last


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response

# 4. Add debug middleware last


@app.middleware("http")
async def log_session(request: Request, call_next):
    if request.scope.get("session"):  # Changed to use scope.get()
        logger.debug(f"Session data before request: {request.session}")
    response = await call_next(request)
    if request.scope.get("session"):
        logger.debug(f"Session data after request: {request.session}")
    return response

# Include the auth router
app.include_router(auth_router)

# Include the users router
app.include_router(users_router)


@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/dashboard")
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})
