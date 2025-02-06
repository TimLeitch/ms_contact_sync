from dotenv import load_dotenv
import os

load_dotenv()

client_id = os.getenv("MS_CLIENT_ID")
client_secret = os.getenv("MS_CLIENT_SECRET")
tenant_id = os.getenv("MS_TENANT_ID")
