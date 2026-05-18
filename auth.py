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

JWT_SECRET = os.getenv("ORIGO_FLASK_SECRET", "survey-app-default-secret-2026")
JWT_ALGO = "HS256"
JWT_EXPIRY_HOURS = 8

router = APIRouter()


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
_DB_USER = os.getenv("FAST_JKT_DB_USER", "")
_DB_PASS = os.getenv("FAST_JKT_DB_PASS", "")
_DB_DSN = os.getenv("FAST_JKT_DB_DSN", "")
_ORACLE_OK = bool(_DB_USER and _DB_PASS and _DB_DSN)


def _oracle_login(user_id_val: str, password: str) -> Optional[dict]:
    if not _ORACLE_OK:
        return None
    try:
        import oracledb
        conn = oracledb.connect(user=_DB_USER, password=_DB_PASS, dsn=_DB_DSN)
        cur = conn.cursor()
        cur.execute(
            "SELECT enkripsi.decrypt(pwd,'FIFGROUP') as pwd, user_id, fullname, role "
            "FROM fifapps.fs_sec_users WHERE user_id=:1",
            (user_id_val,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row and row[0] == password:
            return {"user_id": str(row[1]), "fullname": row[2], "role": row[3]}
    except Exception:
        pass
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
