from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .core.config import APP_NAME,cors_origins
from .services.bootstrap import bootstrap
from .routers import auth,platform,tenant_admin,market_intelligence
app=FastAPI(title=f'{APP_NAME} API',version='1.0.0',docs_url='/docs',redoc_url='/redoc')
app.add_middleware(CORSMiddleware,allow_origins=cors_origins(),allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
@app.on_event('startup')
def startup(): bootstrap()
app.include_router(auth.router); app.include_router(platform.router); app.include_router(tenant_admin.router); app.include_router(market_intelligence.router)
