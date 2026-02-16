import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from config import TRANSMISSION_URL, TRANSMISSION_USER, TRANSMISSION_PASS
from auth import require_admin

router = APIRouter()


@router.api_route("/transmission/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_transmission(path: str, request: Request):
    require_admin(request)
    url = f"{TRANSMISSION_URL}/transmission/{path}"
    headers = {}
    for key, val in request.headers.items():
        if key.lower() not in ("host", "cookie", "connection", "accept-encoding"):
            headers[key] = val
    body = await request.body()
    try:
        auth = httpx.BasicAuth(TRANSMISSION_USER, TRANSMISSION_PASS)
        async with httpx.AsyncClient() as client:
            resp = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=body,
                params=dict(request.query_params),
                auth=auth,
                follow_redirects=True,
            )
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Transmission is not available")
    skip = {"transfer-encoding", "content-encoding", "connection", "content-length"}
    resp_headers = {}
    for key, val in resp.headers.items():
        if key.lower() not in skip:
            resp_headers[key] = val
    return Response(content=resp.content, status_code=resp.status_code, headers=resp_headers)
