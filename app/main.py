from typing import Optional
import os
import logging
import uvicorn
import msal
from fastapi import FastAPI, Request
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from fastapi.responses import RedirectResponse, HTMLResponse
from app.dependencies import auth, config, templates, AuthToken
from app.routers import users, groups

# Load .env file if it exists
load_dotenv()

logger = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(SessionMiddleware,
                   secret_key=os.getenv("SESSION_SECRET_KEY"))
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(groups.router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    token: Optional[AuthToken] = await auth.get_session_token(request=request)
    if not token or not token.id_token_claims:
        return RedirectResponse(url=config.login_path)
    context = {
        "request": request,
        "user": token.id_token_claims,
        "version": msal.__version__,
    }
    return templates.TemplateResponse(name="index.html", context=context)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="localhost", port=5000, reload=True)
