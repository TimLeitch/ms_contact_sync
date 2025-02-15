from typing import Optional
import os
import logging
import uvicorn
from fastapi import FastAPI, Request
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from fastapi.responses import RedirectResponse, HTMLResponse
from app.dependencies import templates
from app.routers import users, groups
from app.auth.certificate_auth import get_access_token

# Load .env file BEFORE any other imports
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(SessionMiddleware,
                   secret_key=os.getenv("SESSION_SECRET_KEY"))
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(users.router)
app.include_router(groups.router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    # Instead of delegated auth, we'll use application auth
    access_token = await get_access_token()
    if not access_token:
        logger.error("Failed to get access token")
        return HTMLResponse("Authentication failed", status_code=401)

    context = {
        "request": request,
        "version": "1.0"
    }
    return templates.TemplateResponse(name="index.html", context=context)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="localhost", port=5000, reload=True)
