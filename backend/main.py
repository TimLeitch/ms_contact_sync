from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from auth.ms_oauth import router as auth_router
import logging
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI(title="Contact Sync App")

# Add session middleware with a secure key from environment
session_secret = os.getenv("SESSION_SECRET_KEY")
if not session_secret:
    raise ValueError(
        "Missing required environment variable: SESSION_SECRET_KEY")

app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret,
    max_age=3600
)

# Add CORS middleware if needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000"],  # Add your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the auth router
app.include_router(auth_router)


@app.get("/")
async def root():
    return {"message": "Welcome to Contact Sync App"}
