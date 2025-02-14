import logging
import httpx
from typing import Optional
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from app.dependencies import auth, config, templates, AuthToken

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["groups"])


def chunk_list(lst, chunk_size):
    """Yield successive chunks from lst."""
    lst = list(lst)
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]


@router.get("/groups", response_class=HTMLResponse)
async def get_groups(request: Request):
    try:
        token: Optional[AuthToken] = await auth.get_session_token(request=request)
        if not token or not token.access_token:
            return RedirectResponse(url=config.login_path)

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                "https://graph.microsoft.com/v1.0/groups",
                headers={"Authorization": "Bearer " + token.access_token},
                params={
                    "$select": "displayName,id",
                }
            )

            if resp.status_code != 200:
                logger.error(
                    f"Failed to fetch groups: {resp.status_code} - {resp.text}")
                return HTMLResponse(content="Failed to fetch groups", status_code=resp.status_code)

            groups = resp.json().get("value", [])

            # Prepare batch request for member counts
            batch_size = 20  # MS Graph batch limit
            batch_requests = []
            request_id_to_group = {}  # Map request IDs to group IDs

            for i, group in enumerate(groups):
                request_id = f"request-{i}"  # Create unique request ID
                request_id_to_group[request_id] = group["id"]
                batch_requests.append({
                    "id": request_id,
                    "method": "GET",
                    "url": f"/groups/{group['id']}/members/$count",
                    "headers": {
                        "ConsistencyLevel": "eventual"
                    }
                })

            # Send batch requests in chunks with retry logic
            for batch_chunk in chunk_list(batch_requests, batch_size):
                try:
                    batch_resp = await client.post(
                        "https://graph.microsoft.com/v1.0/$batch",
                        headers={
                            "Authorization": "Bearer " + token.access_token,
                        },
                        json={"requests": batch_chunk},
                        timeout=30.0  # Explicit timeout for batch request
                    )

                    if batch_resp.status_code != 200:
                        logger.error(
                            f"Batch request failed: {batch_resp.status_code} - {batch_resp.text}")
                        # Set default member count for failed batch
                        for req in batch_chunk:
                            group_id = request_id_to_group.get(req["id"])
                            if group_id:
                                group = next(
                                    (g for g in groups if g["id"] == group_id), None)
                                if group:
                                    group["memberCount"] = "Error"
                        continue

                    batch_results = batch_resp.json().get("responses", [])

                    # Update groups with member counts using request ID mapping
                    for response in batch_results:
                        request_id = response["id"]
                        group_id = request_id_to_group.get(request_id)

                        if not group_id:
                            logger.error(
                                f"Unknown request ID received: {request_id}")
                            continue

                        if response["status"] == 200:
                            group = next(
                                (g for g in groups if g["id"] == group_id), None)
                            if group:
                                group["memberCount"] = int(response["body"])
                            else:
                                logger.error(
                                    f"Could not find group for ID: {group_id}")

                except httpx.ReadTimeout:
                    logger.error("Timeout during batch request")
                    # Set default member count for timed out batch
                    for req in batch_chunk:
                        group_id = request_id_to_group.get(req["id"])
                        if group_id:
                            group = next(
                                (g for g in groups if g["id"] == group_id), None)
                            if group:
                                group["memberCount"] = "Timeout"
                    continue

            return templates.TemplateResponse("groups.html", {
                "request": request,
                "groups": groups
            })

    except Exception as e:
        logger.exception("Error in get_groups endpoint")
        return HTMLResponse(content=f"Server error: {str(e)}", status_code=500)


@router.get("/groups/{group_id}/members", response_class=HTMLResponse)
async def get_group_members(request: Request, group_id: str):
    try:
        token: Optional[AuthToken] = await auth.get_session_token(request=request)
        if not token or not token.access_token:
            return RedirectResponse(url=config.login_path)

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://graph.microsoft.com/v1.0/groups/{group_id}/members",
                headers={
                    "Authorization": "Bearer " + token.access_token,
                    "ConsistencyLevel": "eventual"
                },
                params={
                    "$select": "id,displayName,userPrincipalName,mobilePhone,businessPhones"
                }
            )

            if resp.status_code != 200:
                error_msg = f"Failed to fetch members: {resp.status_code} - {resp.text}"
                logger.error(error_msg)
                return templates.TemplateResponse("group_members.html", {
                    "request": request,
                    "members": [],
                    "error": error_msg
                })

            members = resp.json().get("value", [])
            logger.info(f"Successfully fetched {len(members)} members")
            return templates.TemplateResponse("group_members.html", {
                "request": request,
                "members": members
            })

    except Exception as e:
        error_msg = f"Error fetching group members: {str(e)}"
        logger.exception(error_msg)
        return templates.TemplateResponse("group_members.html", {
            "request": request,
            "members": [],
            "error": error_msg
        })
