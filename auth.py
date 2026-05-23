"""
auth.py — Login/logout routes. FastAPI.
Login: Oracle APEX → fallback PostgreSQL lokal.
Session: JWT token sederhana (simpen di cookie httpOnly).
"""
import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Cookie, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pathlib import Path

import jwt
from templates import TemplateResponse

_APP_DIR = Path(__file__).resolve().parent
load_dotenv(_APP_DIR / ".env", override=False)

# Load Oracle creds dari origo_bots/.env (FAST_USER, FAST_PASS, FAST_SERVICE, dll)
_origo_bots_env = Path("/home/bhc0104/origo_bots/.env")
if _origo_bots_env.exists():
    load_dotenv(_origo_bots_env, override=True)

JWT_SECRET = os.getenv("ORIGO_FLASK_SECRET")
if not JWT_SECRET:
    # Generate secure random fallback (NOT hardcoded) — tapi idealnya set di .env
    import secrets
    JWT_SECRET = secrets.token_hex(32)
    print("WARNING: ORIGO_FLASK_SECRET not set in .env! Using auto-generated random secret.", flush=True)
JWT_ALGO = "HS256"
JWT_EXPIRY_HOURS = 8

router = APIRouter()


# ── Simple in-memory rate limiter (no external deps) ──
import time
_ratelimit_store: dict[str, list[float]] = {}

def _check_rate_limit(key: str, max_attempts: int = 5, window_seconds: int = 60) -> bool:
    """Return True if request is allowed, False if rate-limited."""
    now = time.time()
    if key not in _ratelimit_store:
        _ratelimit_store[key] = []
    # Purge expired entries
    _ratelimit_store[key] = [t for t in _ratelimit_store[key] if now - t < window_seconds]
    if len(_ratelimit_store[key]) >= max_attempts:
        return False
    _ratelimit_store[key].append(now)
    return True


# ── DB helper ──
def get_db():
    import psycopg2
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", 5432)),
        dbname=os.getenv("PG_DB", "db_gabungan"),
        user=os.getenv("PG_USER", "postgres"),
        password=os.getenv("PG_PASS", "iCos2023"),
    )


# ── Oracle login ──
def _oracle_login(user_id_val: str, password: str) -> Optional[dict]:
    """Login via Oracle langsung. Query - cocokin password - return."""
    try:
        import oracledb
        _olib = os.getenv("ORACLE_INSTANT_CLIENT_DIR", "/opt/oracle/instantclient_21_1")
        oracledb.init_oracle_client(lib_dir=_olib)
        _ouser = os.getenv("FAST_USER", "bhcro")
        _opass = os.getenv("FAST_PASS", "")
        _ohost = os.getenv("FAST_TUNNEL_HOST", "127.0.0.1")
        _oport = os.getenv("FAST_TUNNEL_PORT", "1522")
        _osvc  = os.getenv("FAST_SERVICE", "FSMG1")
        _odsn  = f"{_ohost}:{_oport}/{_osvc}"
        conn = oracledb.connect(user=_ouser, password=_opass, dsn=_odsn)
        cur = conn.cursor()
        cur.execute(
            "SELECT USER_ID AS username, USER_NAME AS fullname, enkripsi.decak(USER_PWD) AS password "
            "FROM fifapps.fs_sec_users WHERE USER_ID=:1",
            (user_id_val,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row and row[0] == user_id_val and row[2] == password:
            return {"user_id": row[0], "fullname": row[1], "role": ""}
    except:
        pass  # Oracle gagal? fallback ke lokal
    return None


def _local_login(user_id_val: str, password: str) -> Optional[dict]:
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id, user_name, full_name, user_pwd_hash, user_pwd_plain "
            "FROM origo.survey_users WHERE user_id=%s AND is_active=true",
            (user_id_val,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return None
        user_id, user_name, full_name, user_pwd_hash, user_pwd_plain = row
        # Validasi password — based on user_id
        if user_pwd_hash:
            h = hashlib.sha256((password).encode()).hexdigest()
            if h != user_pwd_hash:
                return None
        elif user_pwd_plain:
            if password != user_pwd_plain:
                return None
        else:
            return None
        return {"user_id": str(user_id), "fullname": full_name or user_name, "role": "staff"}
    except Exception as e:
        return None


def create_token(user: dict) -> str:
    """Bikin JWT token."""
    payload = {
        "user_id": user["user_id"],
        "fullname": user["fullname"],
        "role": user["role"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def decode_token(token: str) -> Optional[dict]:
    """Decode JWT — return None kalo invalid/expired."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except Exception:
        return None


def get_user_from_cookie(token: Optional[str] = None) -> Optional[dict]:
    """Ambil user dari token cookie."""
    if not token:
        return None
    return decode_token(token)


# ── Routes ──

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return TemplateResponse("kop_apex_login.html", {"request": request})


@router.post("/api/login")
async def api_login(request: Request):
    """Login — dapetin JWT token, simpen di httpOnly cookie."""
    # Handle both JSON and form-encoded
    ct = request.headers.get("content-type", "")
    if "json" in ct:
        data = await request.json()
    else:
        form = await request.form()
        data = dict(form)
    username = (data.get("user_id") or data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    if not username or not password:
        return JSONResponse({"ok": False, "status": "error", "error": "User ID & password wajib"}, status_code=400)

    # Rate limiting: 5 attempts per 60 detik per username
    if not _check_rate_limit(f"login:{username}"):
        return JSONResponse({"ok": False, "error": "Terlalu banyak percobaan login. Coba lagi dalam 60 detik."}, status_code=429)

    user = _oracle_login(username, password)
    if not user:
        user = _local_login(username, password)
    if not user:
        return JSONResponse({"ok": False, "error": "Username/password salah"}, status_code=401)

    token = create_token(user)

    resp = JSONResponse({"ok": True, "status": "sukses", "redirect": "/survey/kantor-checklist", "pesan": "Berhasil"})
    resp.set_cookie(
        key="session",
        value=token,
        httponly=True,
        secure=True,
        max_age=JWT_EXPIRY_HOURS * 3600,
        expires=JWT_EXPIRY_HOURS * 3600,
        samesite="lax",
    )
    return resp


@router.get("/api/logout")
async def logout():
    resp = RedirectResponse(url="/login")
    resp.delete_cookie("session")
    return resp
