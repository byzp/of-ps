from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.responses import JSONResponse, PlainTextResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.requests import ClientDisconnect
from pathlib import Path
import asyncio
import logging
import threading
import time
import uvicorn
import os
from urllib.parse import urlencode

from http_server.handlers.dispatch_handler import DispatchHandler
from http_server.handlers.oauth_handler import OAuthHandler
import utils.db as db
from config import Config

logger = logging.getLogger(__name__)
_server = None
_state_lock = threading.Lock()
_stop_requested = threading.Event()
_stopped = threading.Event()
_ever_started = threading.Event()
_startup_error = None

MAX_HTTP_BODY_BYTES = 64 * 1024
HTTP_BODY_TIMEOUT = 5.0
HTTP_GRACEFUL_SHUTDOWN = 5.0
HTTP_MAX_CONCURRENCY = 256

APP_DIR = Path("resources").resolve()
WEBSTATIC_DIR = APP_DIR / "webstatic"
ASSETS_DIR = APP_DIR / "assets"

app = FastAPI(title="gadget")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(Config.HTTP_ALLOWED_ORIGINS),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class LoginRequest(BaseModel):
    username: str
    password: str


class RegistrationRequest(BaseModel):
    username: str
    password: str


def millis() -> int:
    return round(time.time() * 1000)


async def _read_limited_body(request: Request):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_HTTP_BODY_BYTES:
            raise ValueError("request body too large")
    return bytes(body)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    if request.method in {"POST", "PUT", "PATCH"}:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
            if declared < 0:
                return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
            if declared > MAX_HTTP_BODY_BYTES:
                return JSONResponse({"detail": "Request body too large"}, status_code=413)
        try:
            body = await asyncio.wait_for(
                _read_limited_body(request), timeout=HTTP_BODY_TIMEOUT
            )
        except asyncio.TimeoutError:
            return JSONResponse({"detail": "Request body timeout"}, status_code=408)
        except ClientDisconnect:
            return JSONResponse({"detail": "Client disconnected"}, status_code=400)
        except ValueError:
            return JSONResponse({"detail": "Request body too large"}, status_code=413)
        # Starlette/Pydantic can reuse the validated cached body in call_next.
        request._body = body

    response = await call_next(request)
    duration = (time.time() - start) * 1000.0
    logger.debug(
        "<< %s %s - %s (%.2f ms)",
        request.method,
        request.url.path,
        response.status_code,
        duration,
    )
    return response


@app.get("/", response_class=PlainTextResponse)
async def hello_world():
    return "hello, World"


@app.post("/dispatch/client_hot_update")
async def route_client_hot_update(request: Request):
    return JSONResponse(DispatchHandler.hot_update())


@app.get("/Resources/{version:path}/{filename:path}")
async def get_image(version: str, filename: str, request: Request):
    target = os.path.abspath(os.path.join(ASSETS_DIR, version, filename))
    if (
        not target.startswith(os.path.abspath(ASSETS_DIR) + os.sep)
        and os.path.abspath(ASSETS_DIR) != target
    ):
        # 不是子路径，拒绝
        raise HTTPException(status_code=400, detail="Illegal path")
    # 检查文件是否存在
    if not os.path.exists(target) or not os.path.isfile(target):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=target, filename=os.path.basename(target))


@app.post("/dispatch/region_info")
async def route_region_info(request: Request):
    return JSONResponse(DispatchHandler.region_info())


@app.post("/dispatch/get_notice_url_list")
async def get_notice_url_list():
    return JSONResponse({"data": []})


@app.post("/dispatch/get_notice_list")
async def get_notice_list():
    t = millis()
    return JSONResponse({"data": [], "serverTime": t})


@app.get("/config")
async def get_config():
    t = millis()
    return JSONResponse(
        {
            "code": 0,
            "data": {
                "server_timestamp": t,
                "sync_batch_size": 100,
                "sync_interval": 90,
            },
            "msg": "",
        }
    )


@app.get("/onlineHeartbeat")
async def online_heartbeat():
    return JSONResponse(
        {"status": True, "data": {"needLogout": 0, "needLogoutTip": 0}, "message": ""}
    )


@app.post("/openCenter/setGameRoleInfo")
async def set_game_role_info():
    return JSONResponse({"code": 0})


@app.post("/sync")
async def sync_endpoint():
    return JSONResponse({"status": True, "data": None, "message": "role up success"})


@app.post("/dispatch/get_login_url_list")
async def dispatch_get_login_url_list():
    return JSONResponse({})


@app.get("/open/oauth")
async def open_oauth():
    return OAuthHandler.oauth_page(WEBSTATIC_DIR)


@app.get("/openapi/oauth")
async def open_oauth():
    return OAuthHandler.oauth_page(WEBSTATIC_DIR)


@app.post("/api/register")
async def api_register(registration: RegistrationRequest):
    try:
        user = db.create_sdk_user(registration.username, registration.password)
    except ValueError as error:
        return JSONResponse({"success": False, "msg": str(error)}, status_code=400)
    return JSONResponse({"success": True, "uid": str(user["id"]), "username": user["username"]})


@app.post("/api/login")
async def api_login(login: LoginRequest):
    user = db.get_sdk_user_info(login.username, login.password)
    if not user:
        return JSONResponse({"success": False, "msg": "密码错误"}, status_code=200)

    uid = str(user["id"])
    username = user["username"]
    user_token = user["user_token"]

    local_host = '127.0.0.1' if Config.HTTP_HOST in ('0.0.0.0', '::') else Config.HTTP_HOST
    success_url = f"http://{local_host}:{Config.HTTP_PORT}/loginSuccess.html?" + urlencode({
        "uid": uid,
        "username": username,
        "userToken": user_token,
        "authToken": user_token,
        "timeleft": -1,
    })

    return JSONResponse({"success": True, "successUrl": success_url})


@app.get("/loginSuccess.html")
async def login_success():
    return Response(content="", status_code=200)


def start():
    global _server, _startup_error
    with _state_lock:
        if _stop_requested.is_set() and not _ever_started.is_set():
            _stopped.set()
            return
        if _stop_requested.is_set() and not _stopped.is_set():
            # A stop raced with an active start; let that start exit.
            return
        _stop_requested.clear()
        if _server is not None and not _stopped.is_set():
            raise RuntimeError("HTTP server is already running")
        _ever_started.set()
        _stopped.clear()
        _startup_error = None
        logger.info(f"HTTP server started at http://{Config.HTTP_HOST}:{Config.HTTP_PORT}")
        _server = uvicorn.Server(
            uvicorn.Config(
                "http_server.server:app",
                host=Config.HTTP_HOST,
                port=Config.HTTP_PORT,
                log_level="warning",
                access_log=False,
                backlog=512,
                limit_concurrency=HTTP_MAX_CONCURRENCY,
                timeout_keep_alive=5,
                timeout_graceful_shutdown=HTTP_GRACEFUL_SHUTDOWN,
                h11_max_incomplete_event_size=16384,
            )
        )
        server = _server

    try:
        server.run()
    except BaseException as error:
        with _state_lock:
            _startup_error = str(error) or type(error).__name__
        logger.exception("HTTP server failed")
    finally:
        with _state_lock:
            if _server is server:
                _server = None
        _stopped.set()


def stop():
    global _server
    with _state_lock:
        _stop_requested.set()
        server = _server
        if server is not None:
            server.should_exit = True
        else:
            _stopped.set()


def wait_started(timeout=None):
    deadline = None if timeout is None else time.monotonic() + timeout
    while True:
        with _state_lock:
            server = _server
            error = _startup_error
        if error:
            raise RuntimeError(error) from error
        if server is not None and server.started:
            return True
        if _stopped.is_set():
            return False
        if deadline is not None and time.monotonic() >= deadline:
            return False
        time.sleep(0.02)


def wait_stopped(timeout=None):
    return _stopped.wait(timeout)


def startup_error():
    with _state_lock:
        return _startup_error
