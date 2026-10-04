import asyncio
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import APP_NAME, cors_origins
from .core.database import db_path
from .core.env_loader import load_env_file
from .market.intelligence_cycle import run_intelligence_cycle
from .market.scanner_engine import get_scanner_engine, scanner_enabled
from .market.strength_engine import get_strength_engine
from .routers import auth, market_intelligence, platform, tenant_admin
from .services.bootstrap import bootstrap
from .workers.market_intelligence_worker import MarketIntelligenceWorker

log = logging.getLogger(__name__)

app = FastAPI(title=f"{APP_NAME} API", version="1.1.0", docs_url="/docs", redoc_url="/redoc")
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
    bootstrap()
    log.info("SQLite database: %s", db_path())
    from .domain.mt5_diagnostics import mt5_python_package_status

    mt5_pkg = mt5_python_package_status()
    log.info("MT5 Python package: %s", mt5_pkg.get("python_package"))
    if mt5_pkg.get("hint"):
        log.warning(mt5_pkg["hint"])
    global _mi_worker
    if os.getenv("MI_WORKER_ENABLED", "0").strip() in ("1", "true", "yes"):
        interval = int(os.getenv("MI_WORKER_INTERVAL", "300"))
        _mi_worker = MarketIntelligenceWorker(_mi_cycle_async, interval=interval)
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


app.include_router(auth.router)
app.include_router(platform.router)
app.include_router(tenant_admin.router)
app.include_router(market_intelligence.router)
