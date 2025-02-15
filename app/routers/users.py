import logging
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from app.dependencies import templates
from app.auth.certificate_auth import get_access_token
import asyncio

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["users"])


@router.get("/users", response_class=HTMLResponse)
async def get_users(request: Request):
    try:
        access_token = await get_access_token()
        if not access_token:
            return HTMLResponse("Authentication failed", status_code=401)

        async with httpx.AsyncClient() as client:
            users = []
            next_link = "https://graph.microsoft.com/v1.0/users"

            while next_link:
                resp = await client.get(
                    next_link,
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={
                        "$select": "displayName,userPrincipalName,mobilePhone,businessPhones,id",
                        "$top": 999  # Maximum allowed per request
                    }
                )

                if resp.status_code == 403:
                    return HTMLResponse(
                        content="Permission denied. Please ensure proper Microsoft Graph API permissions.",
                        status_code=403
                    )

                data = resp.json()
                users.extend(data.get("value", []))
                next_link = data.get("@odata.nextLink")

        return templates.TemplateResponse("users.html", {"request": request, "users": users})

    except Exception as e:
        logger.error(f"Error fetching users: {str(e)}")
        return HTMLResponse(content="Server error", status_code=500)


@router.get("/users/{user_id}/details", response_class=HTMLResponse)
async def get_user_details(request: Request, user_id: str):
    try:
        access_token = await get_access_token()
        if not access_token:
            return HTMLResponse("Authentication failed", status_code=401)

        async with httpx.AsyncClient() as client:
            # First get folders to find Work Contacts folder
            folders_resp = await client.get(
                f"https://graph.microsoft.com/v1.0/users/{user_id}/contactFolders",
                headers={"Authorization": f"Bearer {access_token}"}
            )

            if folders_resp.status_code == 403:
                return HTMLResponse(
                    content="Permission denied. Please ensure proper Microsoft Graph API permissions.",
                    status_code=403
                )

            folders = folders_resp.json().get("value", [])
            work_folder = next(
                (f for f in folders if f["displayName"] == "Work Contacts"), None)

            # Batch requests for efficiency
            batch_requests = [
                # Get recent contacts with parent folder info
                client.get(
                    f"https://graph.microsoft.com/v1.0/users/{user_id}/contacts",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={
                        "$select": "displayName,emailAddresses,parentFolderId",
                        "$orderby": "lastModifiedDateTime desc",
                        "$top": 5
                    }
                )
            ]

            # Add work folder contacts query if found
            if work_folder:
                batch_requests.append(
                    client.get(
                        f"https://graph.microsoft.com/v1.0/users/{user_id}/contactFolders/{work_folder['id']}/contacts/$count",
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "ConsistencyLevel": "eventual"
                        }
                    )
                )

            responses = await asyncio.gather(*batch_requests)

            recent_contacts = responses[0].json().get("value", [])

            # Add folder info to contacts for debugging
            for contact in recent_contacts:
                folder_id = contact.get("parentFolderId")
                folder = next(
                    (f for f in folders if f["id"] == folder_id), None)
                contact["folderName"] = folder["displayName"] if folder else "Unknown Folder"

            # Update work folder count if we got it
            if work_folder and len(responses) > 1:
                work_folder["totalContactCount"] = int(responses[1].text)

            logger.debug(f"Folders: {folders}")
            logger.debug(f"Recent contacts with folders: {recent_contacts}")

        return templates.TemplateResponse(
            "user_details.html",
            {
                "request": request,
                "contacts": recent_contacts,
                "folders": folders,
                "debug_info": {
                    "recent_contacts_with_folders": recent_contacts,
                    "all_folders": folders
                }
            }
        )

    except Exception as e:
        logger.error(f"Error fetching user details for {user_id}: {str(e)}")
        return HTMLResponse(content="Error fetching user details", status_code=500)
