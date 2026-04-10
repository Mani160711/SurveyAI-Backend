from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import Base, engine
from app.routers import auth, surveys, responses, analytics, ai, superadmin
import app.models  # Ensures all models are registered with Base metadata

app = FastAPI(
    title="SurveyAI",
    description="AI-powered multi-tenant survey platform",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Create all tables on startup (Safe for Serverless)
@app.on_event("startup")
def startup_db_check():
    try:
        Base.metadata.create_all(bind=engine)
        print("Database connected and tables verified.")
    except Exception as e:
        print(f"Database connection failed on startup: {e}")
        # We don't raise here so the app can still start and serve a health check or CORS headers


# --- Robust CORS Configuration (Optimized for Vercel/Production) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL, 
        "https://survey-ai-frontend-kappa.vercel.app",
        "https://survey-ai-superadmin.vercel.app",
        "http://localhost:3000", 
        "http://localhost:3001",
    ],
    # allow_origin_regex supports all Vercel subdomains (previews)
    allow_origin_regex=r"https://survey-ai-frontend-.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=600, # Cache preflight for 10 minutes
)

@app.get("/api/v1/health-cors")
def health_cors():
    """Diagnostics route to verify CORS headers are reachable."""
    return {
        "status": "ok",
        "allowed_frontend": settings.FRONTEND_URL,
        "is_production": "vercel.app" in settings.FRONTEND_URL
    }

API = settings.API_V1_STR  # /api/v1

app.include_router(auth.router, prefix=API)
app.include_router(surveys.router, prefix=API)
app.include_router(responses.router, prefix=API)
app.include_router(analytics.router, prefix=API)
app.include_router(ai.router, prefix=API)
app.include_router(superadmin.router, prefix=API)


@app.get("/")
def root():
    return {"message": "SurveyAI API", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok"}
