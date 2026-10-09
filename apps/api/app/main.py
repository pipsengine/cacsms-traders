import asyncio
import hmac
import logging
import os
import sqlite3
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .core.config import APP_NAME, SESSION_COOKIE, app_env, cors_origins
from .core.database import DatabaseUnavailable, database_url, hold_sqlite_process_lock, release_sqlite_process_lock
from .core.env_loader import load_env_file
from .routers import auth, ctrader, market_intelligence, platform, tenant_admin
from .routers import mt5_bridge
from .services.bootstrap import bootstrap

log = logging.getLogger(__name__)
_mi_worker = None


def _is_vercel() -> bool:
    return os.getenv("VERCEL", "").strip() == "1"


def _safe_error_message(exc: Exception) -> str:
    message = str(exc)
    for name in ("DATABASE_URL", "BOOTSTRAP_PASSWORD", "SUPER_ADMIN_PASSWORD", "CTRADER_CLIENT_SECRET", "API_PROXY_SECRET",
                 "SMTP_PASSWORD", "SMTP_ENCRYPTION_KEY", "CRON_SECRET"):
        secret = os.getenv(name, "")
        if secret:
            message = message.replace(secret, "[REDACTED]")
    return message[:2000]


def _log_startup_failure(component: str, exc: Exception) -> None:
    frames = "".join(traceback.format_tb(exc.__traceback__))
    log.error(
        "%s failed; error_type=%s; detail=%s\n%s",
        component,
        type(exc).__name__,
        _safe_error_message(exc),
        frames,
    )


def _initialize_database(app: FastAPI) -> None:
    app.state.database_bootstrap_status = "initializing"
    try:
        hold_sqlite_process_lock()
        load_env_file()
        bootstrap()
    except Exception as exc:
        app.state.database_bootstrap_status = "failed"
        app.state.database_bootstrap_error = type(exc).__name__
        _log_startup_failure("Database initialization", exc)
    else:
        app.state.database_bootstrap_status = "ready"
        app.state.database_bootstrap_error = None
        log.info("Database bootstrap completed; provider=%s", "PostgreSQL/Neon" if app_env() == "production" else "SQLite")


async def _ensure_database_bootstrap(app: FastAPI) -> None:
    status = getattr(app.state, "database_bootstrap_status", "not_started")
    if status in ("ready", "failed"):
        return
    task = getattr(app.state, "database_bootstrap_task", None)
    if task is None:
        task = asyncio.create_task(asyncio.to_thread(_initialize_database, app))
        app.state.database_bootstrap_task = task
    await asyncio.shield(task)


async def _mi_cycle_async():
    from .market.intelligence_cycle import run_intelligence_cycle

    await asyncio.to_thread(run_intelligence_cycle, ingest=True)


def _start_optional_services(app: FastAPI) -> None:
    global _mi_worker
    if _is_vercel():
        log.info("Persistent autonomous workers are disabled in the Vercel HTTP service")
        return

    try:
        from .market.scanner_engine import get_scanner_engine, scanner_enabled
        from .market.strength_engine import get_strength_engine

        if os.getenv("STRENGTH_ENGINE_ENABLED", "1").strip() not in ("0", "false", "no"):
            get_strength_engine().start()
        if not _is_vercel():
            try:
                from .core.database import db
                from .domain.mt5_connection import ensure_gateway_session
                from .market.market_data import configuration

                with db() as conn:
                    from .market.market_data import bind_market_data_tenant

                    cfg = configuration(conn)
                    tenant_id = (cfg.get("tenant_id") or cfg.get("mt5_tenant_id") or "").strip()
                    if tenant_id:
                        bind_market_data_tenant(conn, tenant_id, account_id=cfg.get("account_id") or None)
                        from .market.market_data import ensure_active_provider_snapshot

                        ensure_active_provider_snapshot(conn)
                        restored = ensure_gateway_session(conn, tenant_id)
                        if restored.get("restored"):
                            log.info("Restored local MT5 session for tenant %s", tenant_id)
            except Exception as exc:
                log.warning("MT5 auto-reconnect on startup skipped: %s", _safe_error_message(exc))
        try:
            from .domain.mt5_session_keeper import get_mt5_session_keeper

            get_mt5_session_keeper().start()
        except Exception as exc:
            log.warning("Local MT5 session keeper failed to start: %s", _safe_error_message(exc))
        if scanner_enabled():
            get_scanner_engine().start()
        if os.getenv("AI_OUTLOOK_SCHEDULER_ENABLED", "1").strip().lower() not in ("0", "false", "no"):
            from .market.outlook.service import get_outlook_service

            get_outlook_service().start()
        from .notifications.worker import enabled as notifications_enabled, get_notification_worker

        if notifications_enabled():
            get_notification_worker().start()
        from .autonomous.engine import enabled as autonomous_enabled, get_autonomous_engine

        if autonomous_enabled() and scanner_enabled():
            get_autonomous_engine().start()
        if os.getenv("MI_WORKER_ENABLED", "0").strip() in ("1", "true", "yes"):
            from .workers.market_intelligence_worker import MarketIntelligenceWorker

            interval = int(os.getenv("MI_WORKER_INTERVAL", "300"))
            _mi_worker = MarketIntelligenceWorker(_mi_cycle_async, interval=interval)
            app.state.mi_worker = _mi_worker
            asyncio.create_task(_mi_worker.start())
            log.info("MI worker scheduled every %s seconds", interval)
    except Exception as exc:
        _log_startup_failure("Optional autonomous service initialization", exc)


def _stop_optional_services() -> None:
    if _is_vercel():
        return
    try:
        if _mi_worker:
            _mi_worker.stop()
        from .market.scanner_engine import get_scanner_engine
        from .market.strength_engine import get_strength_engine

        from .domain.mt5_session_keeper import get_mt5_session_keeper

        get_mt5_session_keeper().stop()
        get_strength_engine().stop()
        get_scanner_engine().stop()
        from .market.outlook.service import get_outlook_service

        get_outlook_service().stop()
        from .notifications.worker import get_notification_worker

        get_notification_worker().stop()
        from .autonomous.engine import get_autonomous_engine

        get_autonomous_engine().stop()
    except Exception as exc:
        _log_startup_failure("Optional autonomous service shutdown", exc)
    release_sqlite_process_lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.database_bootstrap_status = "initializing"
    app.state.database_bootstrap_error = None
    app.state.mi_worker = None
    if _is_vercel():
        app.state.database_bootstrap_task = None
        log.info("Vercel runtime initialized; DATABASE_URL configured=%s", bool(database_url()))
    else:
        _initialize_database(app)
        _start_optional_services(app)
    try:
        yield
    finally:
        _stop_optional_services()


app = FastAPI(title=f"{APP_NAME} API", version="1.1.0", docs_url="/docs", redoc_url="/redoc", lifespan=lifespan)


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
        log.warning('PostgreSQL error for %s %s; error_type=%s; detail=%s', request.method, request.url.path, type(exc).__name__, _safe_error_message(exc))
        return JSONResponse({"detail": "Database unavailable"}, status_code=503)
    raise exc
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LOOPBACK = ("127.0.0.1", "::1", "localhost", "testclient")
FORWARDED_HEADERS = ("x-forwarded-for", "cf-connecting-ip", "x-real-ip")


@app.middleware("http")
async def require_proxy_secret(request: Request, call_next):
    """When API_PROXY_SECRET is set, public traffic must arrive through the Vercel proxy that carries it.

    Direct local calls (Vite dev proxy, scripts) stay allowed: loopback peer with no forwarding headers.
    """
    secret = os.getenv("API_PROXY_SECRET", "").strip()
    if secret and not _is_vercel() and request.url.path.startswith("/api/"):
        direct_local = (request.client is None or request.client.host in LOOPBACK) and not any(
            h in request.headers for h in FORWARDED_HEADERS
        )
        sent = request.headers.get("x-ct-proxy-secret", "")
        if not direct_local and not hmac.compare_digest(sent, secret):
            return JSONResponse({"detail": "Forbidden"}, status_code=403)

    path = request.url.path
    liveness = path == "/api/health/live"
    unauthenticated_me = path == "/api/auth/me" and not (
        request.headers.get("authorization") or request.cookies.get(SESSION_COOKIE)
    )
    if path.startswith("/api/") and not liveness and not unauthenticated_me:
        await _ensure_database_bootstrap(request.app)
        if (
            getattr(request.app.state, "database_bootstrap_status", "not_started") != "ready"
            and path not in ("/api/health/ready", "/api/health")
        ):
            return JSONResponse({"detail": "Database unavailable"}, status_code=503)
    return await call_next(request)


# Every backend route lives under /api — one convention for local dev, the Vercel proxy and API clients.
app.include_router(auth.router, prefix="/api")
app.include_router(platform.router, prefix="/api")
app.include_router(tenant_admin.router, prefix="/api")
app.include_router(mt5_bridge.router)
app.include_router(ctrader.router, prefix="/api")
app.include_router(market_intelligence.router)

from .routers import providers
app.include_router(providers.router)

from .routers import ai_outlook
app.include_router(ai_outlook.router)

from .routers import notifications
app.include_router(notifications.router)

from .routers import autonomous
app.include_router(autonomous.router)
