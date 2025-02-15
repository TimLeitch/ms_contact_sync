import os
import time
import jwt
import aiohttp
from typing import Optional
import logging
from cryptography.x509 import load_pem_x509_certificate
from cryptography.hazmat.primitives import hashes
import base64

logger = logging.getLogger(__name__)

TENANT_ID = os.getenv("AZURE_TENANT_ID")
CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
PRIVATE_KEY_PATH = os.getenv("PRIVATE_KEY_PATH", "private.key")
# Application permissions use .default scope
SCOPE = [
    "https://graph.microsoft.com/.default"
]


async def get_access_token() -> Optional[str]:
    try:
        # Read private key
        with open(PRIVATE_KEY_PATH, 'r') as key_file:
            private_key = key_file.read()
            logger.debug("Private key loaded successfully")

        # Read certificate and get thumbprint
        with open('cert.pem', 'rb') as cert_file:
            cert_data = cert_file.read()
            cert = load_pem_x509_certificate(cert_data)
            # Get raw thumbprint bytes and convert to hex, removing colons
            thumbprint = cert.fingerprint(hashes.SHA1())
            thumbprint = ''.join([f'{b:02X}' for b in thumbprint])
            logger.debug(f"Certificate thumbprint: {thumbprint}")

        now = int(time.time())
        claim = {
            'aud': f'https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token',
            'exp': now + 3600,
            'iss': CLIENT_ID,
            'jti': str(int(time.time() * 1000)),
            'nbf': now,
            'sub': CLIENT_ID
        }

        headers = {
            'typ': 'JWT',
            'alg': 'RS256',
            'x5t': base64.b64encode(bytes.fromhex(thumbprint)).decode('utf-8').rstrip('=')
        }

        # Add debug logging
        logger.debug(f"Claims: {claim}")
        logger.debug(f"Headers: {headers}")
        logger.debug(f"TENANT_ID: {TENANT_ID}")
        logger.debug(f"CLIENT_ID: {CLIENT_ID}")

        try:
            assertion = jwt.encode(
                claim, private_key, algorithm='RS256', headers=headers)
            logger.debug("JWT created successfully")
            # Log first 50 chars of JWT
            logger.debug(f"JWT: {assertion[:50]}...")
        except Exception as jwt_error:
            logger.error(f"JWT creation failed: {str(jwt_error)}")
            raise

        # Get token from Azure AD
        async with aiohttp.ClientSession() as session:
            data = {
                'client_id': CLIENT_ID,
                'client_assertion_type': 'urn:ietf:params:oauth:client-assertion-type:jwt-bearer',
                'client_assertion': assertion,
                'scope': SCOPE,
                'grant_type': 'client_credentials'
            }
            logger.debug(f"Request data: {data}")

            async with session.post(
                f'https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token',
                data=data
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get('access_token')
                else:
                    error_text = await response.text()
                    logger.error(f"Token request failed: {error_text}")
                    logger.error(f"Response status: {response.status}")
                    return None

    except Exception as e:
        logger.error(f"Error getting access token: {str(e)}")
        return None
