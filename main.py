"""
survey_app — FastAPI untuk Checklist Kantor.
Login via Oracle (fallback PostgreSQL), form 100% server-side render.
Gak pake session cookie — pake JWT token simpel.
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

_APP_DIR = Path(__file__).resolve().parent
load_dotenv(_APP_DIR / ".env", override=False)

# ── Templates ──


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="Survey App", lifespan=lifespan)


# ── Import routes ──
from auth import router as auth_router
from checklist import router as checklist_router

app.include_router(auth_router)
app.include_router(checklist_router)


@app.get("/")
async def root():
    return RedirectResponse(url="/login")


if __name__ == "__main__":
    import uvicorn
    _host = os.getenv("API_ORIGO_BIND_HOST", "0.0.0.0")
    _port = int(os.getenv("API_ORIGO_HTTP_PORT", "5000"))
    uvicorn.run("main:app", host=_host, port=_port, reload=False)
