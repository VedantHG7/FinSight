"""
Main FastAPI application for FinSight.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes.health import router as health_router
from app.api.routes.analysis import router as analysis_router
from app.core.config import settings
from app.api.routes.auth import router as auth_router
from app.db.database import create_tables

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG
)

# Configure CORS for all local development origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def response_security_headers(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith('/api'):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
    return response


# Include routers
app.include_router(health_router, prefix="/api", tags=["health"])
app.include_router(analysis_router, prefix="/api")
app.include_router(auth_router, prefix="/api")


@app.on_event("startup")
def startup():
    create_tables()

@app.get("/")
async def root():
    return {"message": f"Welcome to {settings.APP_NAME}"}
