import asyncio
import hmac
import logging
import os
import sqlite3

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .core.config import APP_NAME, app_env, cors_origins
from .core.database import DatabaseUnavailable, database_url, db_path
from .core.env_loader import load_env_file
from .market.intelligence_cycle import run_intelligence_cycle
from .market.scanner_engine import get_scanner_engine, scanner_enabled
from .market.strength_engine import get_strength_engine
from .routers import auth, ctrader, market_intelligence, platform, tenant_admin
from .services.bootstrap import bootstrap
from .workers.market_intelligence_worker import MarketIntelligenceWorker

log = logging.getLogger(__name__)

app = FastAPI(title=f"{APP_NAME} API", version="1.1.0", docs_url="/docs", redoc_url="/redoc")


@app.exception_handler(DatabaseUnavailable)
async def database_unavailable_handler(request: Request, exc: DatabaseUnavailable):
    log.warning('Database unavailable for %s %s: %s', request.method, request.url.path, exc)
    return JSONResponse({"detail": "Database unavailable"}, status_code=503)


@app.exception_handler(sqlite3.DatabaseError)
async def sqlite_error_handler(request: Request, exc: sqlite3.DatabaseError):
    log.warning('SQLite error for %s %s: %s', request.method, request.url.path, exc)
    return JSONResponse({"detail": "Database unavailable"}, status_code=503)

try:
    import psycopg
except Exception:  # pragma: no cover - optional dependency is installed in prod
    psycopg = None


@app.exception_handler(Exception)
async def fallback_exception_handler(request: Request, exc: Exception):
    if database_url() and (psycopg is not None and isinstance(exc, psycopg.Error)):
        log.warning('PostgreSQL error for %s %s: %s', request.method, request.url.path, exc)
        return JSONResponse({"detail": "Database unavailable"}, status_code=503)
    raise exc
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_mi_worker: MarketIntelligenceWorker | None = None


async def _mi_cycle_async():
    await asyncio.to_thread(run_intelligence_cycle, ingest=True)


@app.on_event("startup")
async def startup():
    load_env_file()
    try:
        bootstrap()
    except DatabaseUnavailable:
        log.exception("Startup bootstrap failed because the production database is unavailable: %s", db_path())
        raise
    provider = "PostgreSQL/Neon" if app_env() == "production" else "SQLite"
    log.info("Database provider: %s", provider)
    from .domain.mt5_diagnostics import mt5_python_package_status

    mt5_pkg = mt5_python_package_status()
    log.info("MT5 Python package: %s", mt5_pkg.get("python_package"))
    if mt5_pkg.get("hint"):
        log.warning(mt5_pkg["hint"])
    global _mi_worker
    if os.getenv("MI_WORKER_ENABLED", "0").strip() in ("1", "true", "yes"):
        interval = int(os.getenv("MI_WORKER_INTERVAL", "300"))
        _mi_worker = MarketIntelligenceWorker(_mi_cycle_async, interval=interval)
        app.state.mi_worker = _mi_worker
        asyncio.create_task(_mi_worker.start())
        log.info("MI worker scheduled every %s seconds", interval)
    if os.getenv("STRENGTH_ENGINE_ENABLED", "1").strip() not in ("0", "false", "no"):
        get_strength_engine().start()
    if scanner_enabled():
        get_scanner_engine().start()


@app.on_event("shutdown")
async def shutdown():
    if _mi_worker:
        _mi_worker.stop()
    get_strength_engine().stop()
    get_scanner_engine().stop()


LOOPBACK = ("127.0.0.1", "::1", "localhost", "testclient")
FORWARDED_HEADERS = ("x-forwarded-for", "cf-connecting-ip", "x-real-ip")


@app.middleware("http")
async def require_proxy_secret(request: Request, call_next):
    """When API_PROXY_SECRET is set, public traffic must arrive through the Vercel proxy that carries it.

    Direct local calls (Vite dev proxy, scripts) stay allowed: loopback peer with no forwarding headers.
    """
    secret = os.getenv("API_PROXY_SECRET", "").strip()
    if secret and request.url.path.startswith("/api/"):
        direct_local = (request.client is None or request.client.host in LOOPBACK) and not any(
            h in request.headers for h in FORWARDED_HEADERS
        )
        sent = request.headers.get("x-ct-proxy-secret", "")
        if not direct_local and not hmac.compare_digest(sent, secret):
            return JSONResponse({"detail": "Forbidden"}, status_code=403)
    return await call_next(request)


# Every backend route lives under /api — one convention for local dev, the Vercel proxy and API clients.
app.include_router(auth.router, prefix="/api")
app.include_router(platform.router, prefix="/api")
app.include_router(tenant_admin.router, prefix="/api")
app.include_router(ctrader.router, prefix="/api")
app.include_router(market_intelligence.router)
