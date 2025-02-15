# MS Contact Sync

FastAPI + HTMX application for syncing Microsoft contacts.

## Features

- OAuth2 integration with Microsoft Graph API
- Contact synchronization and management 
- Simple HTMX frontend
- Docker

## Setup

1. Clone the repository
2. Rename `.env.example` to `.env`
3. Update the `.env` file with your credentials:
   - Add your app credentials
   
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

   Alternatively, I recommended you use a virtual environment:
   ```bash
   # Create a virtual environment
   python -m venv venv

   # Activate the virtual environment (Windows)
   .\venv\Scripts\activate
   # OR activate the virtual environment (Linux/Mac)
   source venv/bin/activate

   # Install dependencies
   pip install -r requirements.txt
   ```
5. Run the application:
   ```bash
   uvicorn app:app --reload
   ```

> **Note:** While the above instructions are for local development, in production the application should be run using Docker. Docker deployment instructions will be provided soon.

# Generate private key and certificate
openssl req -x509 -newkey rsa:4096 -keyout private.key -out cert.pem -days 365 -nodes -subj "/CN=your-app-name"

# Convert certificate to base64 (needed for Azure AD)
openssl base64 -in cert.pem -out cert.base64 -A