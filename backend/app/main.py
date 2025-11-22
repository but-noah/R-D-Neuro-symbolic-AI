from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.endpoints import router as api_router
from app.api.v1.test_endpoints import router as test_router
from app.core.config import settings

app = FastAPI(title="Anti-Hallucination Empathy Engine API")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, set this to the specific frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")
app.include_router(test_router, prefix="/api/v1", tags=["testing"])

@app.get("/")
def root():
    return {"message": "Anti-Hallucination Engine Online"}
