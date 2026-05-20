"""
checklist.py - Kantor Checklist routes. FastAPI.
Form 100% server-side render - NO JS dependency buat nampilin form.
"""
import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Cookie, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from auth import get_user_from_cookie

_APP_DIR = Path(__file__).resolve().parent
load_dotenv(_APP_DIR / ".env", override=False)
from templates import TemplateResponse

# ── Analisa Gambar (provider-agnostic) ──
import base64
import httpx

# Provider: "gemini" | "blackbox"
_ANALISA_PROVIDER = os.getenv("ANALISA_PROVIDER", "blackbox").strip().lower()

# Gemini config
_ANALISA_GEMINI_MODEL = "gemini-2.5-flash"
_ANALISA_GEMINI_KEY = os.getenv("GEMINI_ANALISA_KEY", "")

# Blackbox config
_ANALISA_BLACKBOX_API_KEY = os.getenv("BLACKBOX_API_KEY", "")
_ANALISA_BLACKBOX_MODEL = os.getenv("ANALISA_BLACKBOX_MODEL", "blackboxai/qwen3-vl-32b")


def _get_kurs() -> float:
    """Ambil kurs IDR dari API, fallback 16500."""
    try:
        kr = httpx.get("https://open.er-api.com/v6/latest/USD", timeout=5)
        if kr.status_code == 200:
            return kr.json()["rates"].get("IDR", 16500)
    except:
        pass
    return 16500


def _save_usage(kantor_code: str, item_idx: int, item_label: str, model: str,
                input_tokens: int, output_tokens: int, img_size_kb: int,
                cost_idr: int, relevan: bool, saran: str):
    """Log pemakaian ke DB."""
    try:
        conn_log = get_db(); cur_log = conn_log.cursor()
        cur_log.execute(
            """INSERT INTO origo.survey_ai_usage
               (kantor_code, item_idx, item_label, model, input_tokens, output_tokens,
                image_count, image_size_kb, estimated_cost_idr, relevan, saran)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (kantor_code, item_idx, item_label, model,
             input_tokens, output_tokens, 1, img_size_kb, cost_idr,
             relevan, saran[:500]))
        conn_log.commit(); cur_log.close(); conn_log.close()
    except Exception as e:
        pass  # log failure bukan failure fatal


def analisa_foto_gemini(img_bytes: bytes, item_label: str, item_cat: str, kantor_code: str = "", item_idx: int = 0) -> dict:
    """
    Delegasi ke provider yang aktif.
    Selalu catat pemakaian ke tabel origo.survey_ai_usage.
    Return {"deskripsi": str, "relevan": bool, "saran": str, "cost_idr": int}
    """
    if _ANALISA_PROVIDER == "blackbox":
        return _analisa_foto_blackbox(img_bytes, item_label, item_cat, kantor_code, item_idx)
    else:
        return _analisa_foto_gemini_direct(img_bytes, item_label, item_cat, kantor_code, item_idx)


def _analisa_foto_gemini_direct(img_bytes: bytes, item_label: str, item_cat: str, kantor_code: str = "", item_idx: int = 0) -> dict:
    """
    Panggil Gemini API langsung. Selalu catat pemakaian ke DB.
    Return {"deskripsi": str, "relevan": bool, "saran": str, "cost_idr": int}
    """
    if not _ANALISA_GEMINI_KEY:
        return {"deskripsi": "(API key tidak tersedia)", "relevan": True, "saran": "", "cost_idr": 0}

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{_ANALISA_GEMINI_MODEL}:generateContent?key={_ANALISA_GEMINI_KEY}"
    img_b64 = base64.b64encode(img_bytes).decode()
    img_size_kb = len(img_bytes) // 1024

    prompt = _buat_prompt(item_label, item_cat)

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
            ]
        }]
    }

    input_tokens = 0; output_tokens = 0
    result_data = {"deskripsi": "(gagal)", "relevan": True, "saran": "", "cost_idr": 0}

    try:
        r = httpx.post(url, json=payload, timeout=20)
        if r.status_code == 200:
            resp = r.json()
            usage = resp.get("usageMetadata", {})
            if usage:
                input_tokens = usage.get("promptTokenCount", 0)
                output_tokens = usage.get("candidatesTokenCount", 0)

            relevan, saran, deskripsi = _parse_gemini_response(resp)
            result_data = {"deskripsi": deskripsi, "relevan": relevan, "saran": saran, "cost_idr": 0}
        else:
            result_data = {"deskripsi": f"(error API: {r.status_code})", "relevan": True, "saran": "", "cost_idr": 0}
    except Exception as e:
        result_data = {"deskripsi": f"(error: {str(e)[:50]})", "relevan": True, "saran": "", "cost_idr": 0}

    kurs = _get_kurs()
    cost_input_usd = (input_tokens / 1_000_000) * 0.30
    cost_output_usd = (output_tokens / 1_000_000) * 2.50
    cost_idr = round((cost_input_usd + cost_output_usd) * kurs)
    if cost_idr < 1: cost_idr = 1
    result_data["cost_idr"] = cost_idr

    _save_usage(kantor_code, item_idx, item_label, _ANALISA_GEMINI_MODEL,
                input_tokens, output_tokens, img_size_kb, cost_idr,
                result_data.get("relevan", True), result_data.get("saran", ""))
    return result_data


def _analisa_foto_blackbox(img_bytes: bytes, item_label: str, item_cat: str, kantor_code: str = "", item_idx: int = 0) -> dict:
    """
    Panggil Qwen VL via Blackbox API. Selalu catat pemakaian ke DB.
    Return {"deskripsi": str, "relevan": bool, "saran": str, "cost_idr": int}
    """
    api_key = _ANALISA_BLACKBOX_API_KEY
    if not api_key:
        return {"deskripsi": "(BLACKBOX_API_KEY tidak tersedia)", "relevan": True, "saran": "", "cost_idr": 0}

    url = "https://api.blackbox.ai/v1/chat/completions"
    img_b64 = base64.b64encode(img_bytes).decode()
    img_size_kb = len(img_bytes) // 1024
    prompt = _buat_prompt(item_label, item_cat)

    payload = {
        "model": _ANALISA_BLACKBOX_MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
        ]}],
        "max_tokens": 500,
        "temperature": 0.1
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    input_tokens = 0; output_tokens = 0; cost_idr = 0
    result_data = {"deskripsi": "(gagal)", "relevan": True, "saran": "", "cost_idr": 0}

    try:
        r = httpx.post(url, json=payload, headers=headers, timeout=60)
        if r.status_code == 200:
            data = r.json()
            usage = data.get("usage", {})
            if usage:
                input_tokens = usage.get("prompt_tokens", 0) or 0
                output_tokens = usage.get("completion_tokens", 0) or 0
                cost_usd = usage.get("cost", 0) or 0
                cost_idr = round(float(cost_usd) * _get_kurs())

            relevan, saran, deskripsi = _parse_blackbox_response(data)
            result_data = {"deskripsi": deskripsi, "relevan": relevan, "saran": saran, "cost_idr": cost_idr}
        else:
            result_data = {"deskripsi": f"(error Blackbox: {r.status_code})", "relevan": True, "saran": "", "cost_idr": 0}
    except Exception as e:
        result_data = {"deskripsi": f"(error: {str(e)[:50]})", "relevan": True, "saran": "", "cost_idr": 0}

    if cost_idr < 1: cost_idr = 1
    result_data["cost_idr"] = cost_idr

    _save_usage(kantor_code, item_idx, item_label, _ANALISA_BLACKBOX_MODEL,
                input_tokens, output_tokens, img_size_kb, cost_idr,
                result_data.get("relevan", True), result_data.get("saran", ""))
    return result_data


# ── Helper functions untuk analisa foto ─────────────────────────────

def _buat_prompt(item_label: str, item_cat: str) -> str:
    return f"""\
Foto ini adalah dokumentasi survey kantor untuk item: [{item_cat}] {item_label}

Analisa apakah foto ini relevan dengan item tersebut.
Jawab dalam JSON (hanya JSON, tanpa markdown):
{{
  "deskripsi": "deskripsi singkat apa yang terlihat (1 kalimat, Bahasa Indonesia)",
  "relevan": true,
  "saran": ""
}}
"""


def _parse_gemini_response(resp: dict) -> tuple:
    """Parse Gemini response -> (relevan bool, saran str, deskripsi str)."""
    try:
        raw = resp['candidates'][0]['content']['parts'][0]['text']
        raw = raw.strip()
        if raw.startswith('```'):
            raw = raw.split('\n', 1)[-1]
            raw = raw.rsplit('\n```', 1)[0] if '\n```' in raw else raw.replace('```json','').replace('```','').strip()
        result = json.loads(raw)
        return (
            bool(result.get("relevan", True)),
            result.get("saran", ""),
            result.get("deskripsi", "(deskripsi tidak tersedia)")
        )
    except Exception:
        return True, "", "(gagal parse respons)"


def _parse_blackbox_response(data: dict) -> tuple:
    """Parse Blackbox AI response -> (relevan bool, saran str, deskripsi str)."""
    try:
        raw = data['choices'][0]['message']['content']
        raw = raw.strip()
        if raw.startswith('```'):
            raw = raw.split('\n', 1)[-1]
            raw = raw.rsplit('\n```', 1)[0] if '\n```' in raw else raw.replace('```json','').replace('```','').strip()
        result = json.loads(raw)
        return (
            bool(result.get("relevan", True)),
            result.get("saran", ""),
            result.get("deskripsi", "(deskripsi tidak tersedia)")
        )
    except Exception:
        return True, "", "(gagal parse respons)"


router = APIRouter()

def get_db():
    import psycopg2
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", 5432)),
        dbname=os.getenv("PG_DB", "db_gabungan"),
        user=os.getenv("PG_USER", "postgres"),
        password=os.getenv("PG_PASS", "iCos2023"),
    )

@router.get("/survey/api/master-data")
async def master_data(request: Request):
    """Semua data master dalam 1 response - kategori, item, options."""
    try:
        conn = get_db()
        cur = conn.cursor()

        cur.execute("SELECT id, cat_code, cat_name, color_hex FROM origo.survey_categories WHERE is_active = true ORDER BY sort_order")
        categories = [{"id": r[0], "code": r[1], "name": r[2], "color": r[3]} for r in cur.fetchall()]

        cur.execute("""
            SELECT i.id, i.cat_id, c.cat_code, i.item_idx, i.label, i.tip,
                   t.type_code, i.weight, i.wajib_foto_policy, i.wajib_catatan
            FROM origo.survey_checklist_items i
            JOIN origo.survey_categories c ON i.cat_id = c.id
            JOIN origo.survey_question_types t ON i.type_id = t.id
            WHERE i.is_active = true
            ORDER BY i.item_idx
        """)
        item_rows = cur.fetchall()

        # Options grouped by type
        cur.execute("""
            SELECT t.type_code, o.opt_value, o.opt_label, o.weight_mult, o.is_no, o.sort_order
            FROM origo.survey_type_options o
            JOIN origo.survey_question_types t ON o.type_id = t.id
            ORDER BY t.type_code, o.sort_order
        """)
        opts_by_type = {}
        for r in cur.fetchall():
            tc = r[0]
            if tc not in opts_by_type:
                opts_by_type[tc] = []
            opts_by_type[tc].append({"value": r[1], "label": r[2], "mult": float(r[3]), "is_no": r[4]})

        items = []
        for r in item_rows:
            items.append({
                "id": r[0], "cat_id": r[1], "cat_code": r[2], "idx": r[3],
                "label": r[4], "tip": r[5] or "",
                "type_code": r[6], "weight": float(r[7]),
                "wajib_foto_policy": r[8], "wajib_catatan": r[9],
                "helper": "",
                "options": opts_by_type.get(r[6], [])
            })

        cur.close()
        conn.close()
        return {"ok": True, "categories": categories, "items": items}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

# ── Halaman utama: pilih kantor ──
@router.get("/survey/kantor-checklist", response_class=HTMLResponse)
async def index(request: Request, session: Optional[str] = Cookie(None)):
    user = get_user_from_cookie(session)
    if not user:
        return HTMLResponse(status_code=302, headers={"Location": "/login"})

    kantor_list = []
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT n.office_code, n.display_name
            FROM origo.network_tree_node n
            JOIN origo.network_tree_version v ON n.version_id = v.id
            WHERE v.is_published = true
              AND n.office_code IS NOT NULL
              AND n.display_name IS NOT NULL
              AND n.office_code ~ '^[1-9][0-9]{4}$'
              AND n.branch_kind IN ('cbg_besar','cbg_kecil','pos','kios')
            ORDER BY n.office_code
        """)
        rows = cur.fetchall()
        kantor_list = [{"node_code": r[0], "display_name": r[1]} for r in rows]

        # Ambil status workflow tiap kantor
        codes = [r[0] for r in rows]
        status_map = {}
        if codes:
            import psycopg2.extras
            placeholders = ','.join(['%s'] * len(codes))
            cur.execute(f"""
                SELECT kantor_code, workflow_status, yes_count, total_items, pic
                FROM origo.kantor_checklist_data
                WHERE kantor_code IN ({placeholders})
                  AND workflow_status IS NOT NULL
                  AND survey_seq = (
                    SELECT MAX(sub.survey_seq)
                    FROM origo.kantor_checklist_data sub
                    WHERE sub.kantor_code = kantor_checklist_data.kantor_code
                  )
            """, codes)
            for sr in cur.fetchall():
                status_map[sr[0]] = {
                    "workflow": sr[1],
                    "yes": sr[2],
                    "total": sr[3],
                    "pic": sr[4] or ""
                }
        # Ambil lock timestamp juga - SEBELUM cur.close()
        lock_map = {}
        if codes:
            cur.execute(f"""
                SELECT kantor_code, updated_at, pic
                FROM origo.kantor_checklist_data
                WHERE kantor_code IN ({placeholders})
                  AND workflow_status = 'draft'
                  AND survey_seq = (
                    SELECT MAX(sub.survey_seq)
                    FROM origo.kantor_checklist_data sub
                    WHERE sub.kantor_code = kantor_checklist_data.kantor_code
                  )
            """, codes)
            for lr in cur.fetchall():
                lock_map[lr[0]] = {"updated_at": lr[1], "pic": lr[2] or ""}
        cur.close()
        conn.close()

        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        lock_timeout = timedelta(minutes=30)

        for k in kantor_list:
            s = status_map.get(k["node_code"], {})
            k["workflow"] = s.get("workflow", "")
            k["pic"] = s.get("pic", "")
            if s.get("total"):
                k["skor_pct"] = round(s["yes"] / s["total"] * 100, 1) if s["total"] > 0 else 0
            else:
                k["skor_pct"] = None

            # Lock timeout check
            lock = lock_map.get(k["node_code"])
            if lock and lock["pic"] != user["user_id"]:
                lock_ts = lock["updated_at"] if lock["updated_at"].tzinfo else lock["updated_at"].replace(tzinfo=timezone.utc)
                lock_age = now - lock_ts
                if lock_age > lock_timeout:
                    # Lock expired - treat sebagai available, bukan conflict
                    k["workflow"] = "draft_expired"
                    k["expired_pic"] = lock["pic"]
                    k["expired_ago"] = int(lock_age.total_seconds() / 60)
    except Exception as e:
        import traceback; traceback.print_exc()

    return TemplateResponse(
        "survey_index.html",
        {
            "request": request,
            "user_name": user["fullname"], "fullname": user["fullname"],
            "user_id_pic": user["user_id"],
            "kantor_list": kantor_list,
            "today_str": date.today().isoformat(),
            "menu_items": _get_menu(),
        },
    )

# ── Form langsung ──
@router.get("/survey/kantor-checklist/form/{kantor_code}", response_class=HTMLResponse)
async def form(request: Request, kantor_code: str, session: Optional[str] = Cookie(None)):
    user = get_user_from_cookie(session)
    if not user:
        return HTMLResponse(status_code=302, headers={"Location": "/login"})

    kantor_label = kantor_code
    workflow_status = ""
    existing_pic = ""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT display_name FROM origo.network_tree_node WHERE office_code=%s LIMIT 1",
            (kantor_code,),
        )
        row = cur.fetchone()
        if row:
            kantor_label = row[0]

        # Cek status survei terbaru untuk kantor ini
        cur.execute(
            """SELECT workflow_status, pic FROM origo.kantor_checklist_data
               WHERE kantor_code = %s
               ORDER BY survey_seq DESC LIMIT 1""",
            (kantor_code,),
        )
        srow = cur.fetchone()
        if srow:
            workflow_status = srow[0] or ""
            existing_pic = srow[1] or ""
        cur.close()
        conn.close()
    except Exception:
        pass

    from datetime import datetime, timezone, timedelta

    current_pic = user.get("user_id", "")

    # Lock timeout - draft expired setelah 30 menit inactivity
    lock_expired = False
    same_user_refresh = (workflow_status == "draft") and existing_pic and existing_pic == current_pic

    if workflow_status == "draft" and existing_pic and existing_pic != current_pic and not same_user_refresh:
        try:
            conn2 = get_db()
            cur2 = conn2.cursor()
            cur2.execute(
                "SELECT updated_at FROM origo.kantor_checklist_data WHERE kantor_code=%s AND workflow_status='draft' ORDER BY survey_seq DESC LIMIT 1",
                (kantor_code,)
            )
            urow = cur2.fetchone()
            cur2.close(); conn2.close()
            if urow and urow[0]:
                ut = urow[0]
                ut_aware = ut.replace(tzinfo=timezone.utc) if ut.tzinfo is None else ut
                if (datetime.now(timezone.utc) - ut_aware) > timedelta(minutes=30):
                    lock_expired = True
        except Exception:
            pass

    is_draft = (workflow_status == "draft") and not lock_expired
    is_submitted = (workflow_status in ("submitted", "final"))
    same_user_refresh = (workflow_status == "draft") and existing_pic and existing_pic == current_pic
    conflict_mode = (workflow_status == "draft") and not lock_expired and not same_user_refresh and existing_pic and existing_pic != current_pic
    lock_expired_mode = lock_expired

    # Ambil draft data untuk server-side render (biar foto langsung muncul)
    initial_status = None
    if workflow_status in ("draft", "submitted", "final"):
        try:
            conn3 = get_db()
            cur3 = conn3.cursor()
            cur3.execute(
                "SELECT status_data FROM origo.kantor_checklist_data WHERE kantor_code=%s ORDER BY survey_seq DESC LIMIT 1",
                (kantor_code,)
            )
            srow3 = cur3.fetchone()
            if srow3 and srow3[0]:
                initial_status = srow3[0]
            cur3.close(); conn3.close()
        except Exception:
            pass

    return TemplateResponse(
        "survey_form.html",
        {
            "request": request,
            "user_name": user["fullname"], "fullname": user["fullname"],
            "user_id_pic": user["user_id"],
            "kantor_code": kantor_code,
            "kantor_label": kantor_label,
            "menu_items": _get_menu(),
            "items": _get_items_from_db(),
            "cat_names": _get_cat_names(),
            "cat_items": _get_items_from_db(),
            "type_options": _get_type_options_map(),
            "today_str": date.today().isoformat(),
            "workflow_status": workflow_status,
            "existing_pic": existing_pic,
            "initial_status_data": initial_status,
            "is_draft": is_draft,
            "is_submitted": is_submitted,
            "conflict_mode": conflict_mode,
            "lock_expired_mode": lock_expired_mode,
            "current_pic": current_pic,
            "item_count": ITEM_COUNT,
        },
    )

# ── API: Load session ──
@router.get("/survey/api/kantor-checklist/load-session")
async def api_load_session(
    kantor_code: str = Query(...),
    session: Optional[str] = Cookie(None),
):
    user = get_user_from_cookie(session)
    if not user:
        return JSONResponse({"ok": False, "error": "Not logged in"}, status_code=401)

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM origo.kantor_checklist_data WHERE kantor_code=%s",
            (kantor_code,),
        )
        cols = [d[0] for d in cur.description]
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return JSONResponse({"ok": False, "error": "Belum ada data"}, status_code=200)
        d = dict(zip(cols, row))
        d["tgl_cek"] = str(d["tgl_cek"]) if d.get("tgl_cek") else ""
        return {"ok": True, "data": d}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

# ── API: Submit ──
@router.post("/survey/api/kantor-checklist/submit-session")
async def api_submit(request: Request, session: Optional[str] = Cookie(None)):
    user = get_user_from_cookie(session)
    if not user:
        return JSONResponse({"ok": False, "error": "Not logged in"}, status_code=401)

    # Accept both JSON and form-encoded
    content_type = request.headers.get('content-type', '').lower()
    if 'application/json' in content_type:
        body = await request.json()
        kantor_code = body.get('kantor_code', '').strip()
        pic = body.get('pic', '')
        tgl_cek = body.get('tgl_cek', '')
        raw_sd = body.get('status_data', '[]')
        if isinstance(raw_sd, str):
            try: status_data = json.loads(raw_sd)
            except: status_data = []
        else:
            status_data = raw_sd
        workflow_status = body.get('workflow_status', 'draft')
        photo_raw = body.get('photo_data', '{}')
        items_raw = body.get('items', None)
        if items_raw is not None and (status_data == '[]' or (isinstance(status_data, list) and len(status_data) == 0)):
            # Convert items dict to flat status_data list
            status_data = []
            for k in sorted(items_raw.keys(), key=lambda x: int(x)):
                val = items_raw[k]
                if isinstance(val, dict):
                    sv = val.get('status', '')
                    if sv == '' or sv is None:
                        sv = ''
                    else:
                        try: sv = int(sv)
                        except: pass
                    status_data.append({"status": sv, "note": val.get('note', ''), "foto": val.get('foto', ''), "video_path": val.get('video_path', '')})
                else:
                    status_data.append({"status": val})
    else:
        form_data = await request.form()
        kantor_code = form_data.get('kantor_code', '').strip()
        pic = form_data.get('pic', '')
        tgl_cek = form_data.get('tgl_cek', '')
        raw_sd = form_data.get('status_data', '[]')
        try: status_data = json.loads(raw_sd)
        except: status_data = []
        workflow_status = form_data.get('workflow_status', 'draft')
        photo_raw = form_data.get('photo_data', '{}')

    # ── Validasi wajib foto per policy ──
    if workflow_status == "submitted":
        items_db = _get_items_from_db()
        dbitems = items_db if items_db else []
        try: photo_data = json.loads(photo_raw) if isinstance(photo_raw, str) else photo_raw
        except: photo_data = {}
        for i, s in enumerate(status_data):
            if i >= len(dbitems): break

            # ── Validasi wajib catatan ──
            if dbitems[i].get("wajib_catatan", False):
                note = s.get("note", "").strip()
                if not note:
                    return JSONResponse(
                        {"ok": False, "error": f"Item #{i} ('{dbitems[i].get('label','')}') - wajib isi catatan!"},
                        status_code=400
                    )

            policy = dbitems[i].get("wajib_foto_policy", "bermasalah")
            policy_if_no = dbitems[i].get("policy_if_no", False)
            try: sv = int(s.get("status", "99"))
            except: sv = 99

            # Policy dinamis: kalo 'policy_if_no=true' dan user pilih opsi 'no', override jadi 'tanpa'
            # Cek dari options apakah option ini is_no
            effective_policy = policy
            if policy_if_no:
                for opt in dbitems[i].get("options", []):
                    if opt.get("score", -1) == sv:
                        # weight_mult 0.0 atau option yang menunjukkan 'tidak'
                        if opt.get("weight_mult", 1.0) == 0.0:
                            effective_policy = "tanpa"
                        break

            needs_photo = False
            if effective_policy == "buktikan":
                needs_photo = True  # foto untuk SEMUA status
            elif effective_policy == "bermasalah" and sv > 0:
                needs_photo = True
            elif effective_policy == "ada_berfungsi" and sv == 0:
                needs_photo = True
            if needs_photo:
                key = str(i)
                # Cek juga apakah ada video (allow_video = true)
                has_photo = bool(key in photo_data and photo_data[key])
                if not has_photo:
                    # Fallback: cek foto dari status_data (di-parse dari items frontend)
                    foto_path = s.get("foto", "")
                    if foto_path:
                        from pathlib import Path
                        if foto_path.startswith("/survey/uploads/"):
                            fname = os.path.basename(foto_path)
                            fullpath = os.path.join(PHOTO_DIR, fname)
                        elif foto_path.startswith("/"):
                            fullpath = foto_path
                        else:
                            fullpath = os.path.join(PHOTO_DIR, foto_path)
                        if fullpath and Path(fullpath).exists():
                            has_photo = True
                has_video = False
                if not has_photo and dbitems[i].get("allow_video", False):
                    # Video disimpan di status_data[i].video_path
                    vid_path = s.get("video_path", "")
                    if vid_path:
                        # video_path mungkin berupa URL path (/survey/uploads/...) → konversi ke filesystem
                        from pathlib import Path
                        if vid_path.startswith("/survey/uploads/"):
                            fname = os.path.basename(vid_path)
                            vid_fs = os.path.join(PHOTO_DIR, fname)
                            has_video = Path(vid_fs).exists()
                        elif vid_path.startswith("/"):
                            has_video = Path(vid_path).exists()
                        else:
                            has_video = Path(vid_path).exists()
                if not has_photo and not has_video:
                    return JSONResponse(
                        {"ok": False, "error": f"Item #{i} ('{dbitems[i].get('label','')}') - butuh dokumentasi (foto/video)!"},
                        status_code=400
                    )

    if not pic:
        pic = user.get('user_id', '')
    if not tgl_cek:
        from datetime import date
        tgl_cek = str(date.today())
    if not kantor_code:
        return JSONResponse({"ok": False, "error": "kantor_code wajib"}, status_code=400)

    try:
        yes_count = sum(1 for s in status_data if int(s.get("status", "99")) == 0)
        no_count = sum(1 for s in status_data if int(s.get("status", "99")) in (1,2,3,4))
    except:
        yes_count = 0
        no_count = 0
    no_count = sum(1 for s in status_data if int(s.get('status', 99)) in (1,2,3,4))
    total_items = len(status_data)

    # Hitung weighted score
    try:
        db_items_for_score = _get_items_from_db()
        ws, _, _, _ = _hitung_weighted_score(status_data, db_items_for_score)
    except:
        ws = round(yes_count / total_items * 100, 1) if total_items > 0 else 0
    weighted_score = ws

    try:
        conn = get_db()
        cur = conn.cursor()
        # Cek draft session terakhir untuk kantor ini
        cur.execute(
            """SELECT id FROM origo.kantor_checklist_data
               WHERE kantor_code = %s AND workflow_status = 'draft'
               ORDER BY survey_seq DESC LIMIT 1""",
            (kantor_code,)
        )
        draft_row = cur.fetchone()

        if draft_row:
            # Update draft yang ada
            cur.execute(
                """UPDATE origo.kantor_checklist_data SET
                   pic=%s, tgl_cek=%s, status_data=%s, workflow_status=%s,
                   yes_count=%s, no_count=%s, total_items=%s,
                   weighted_score=%s,
                   updated_at=NOW(),
                   submitted_at=(CASE WHEN %s='submitted' THEN NOW() ELSE NULL END)
                   WHERE id=%s RETURNING id""",
                (pic, tgl_cek, json.dumps(status_data), workflow_status,
                 yes_count, no_count, total_items, weighted_score,
                 workflow_status, draft_row[0])
            )
        else:
            # Insert baru
            cur.execute(
                """INSERT INTO origo.kantor_checklist_data
                   (kantor_code, pic, tgl_cek, status_data, workflow_status,
                    yes_count, no_count, total_items, weighted_score, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, NOW())
                   RETURNING id""",
                (kantor_code, pic, tgl_cek, json.dumps(status_data), workflow_status,
                 yes_count, no_count, total_items, weighted_score),
            )
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return {"ok": True, "id": row[0] if row else None}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

# ── Dashboard ──
# Fungsi helper - ambil items dari DB


def _hitung_weighted_score(status_data, db_items):
    """Hitung weighted score 0-100 dari status_data dan bobot item+option.
    Item weight dihitung DINAMIS: cat_weight / jumlah_item_aktif_di_kategori.
    Item yang tidak terisi dianggap score 0 (weight_mult = 0).
    Returns (weighted_score, weighted_baik, weighted_total, detail_per_item).
    detail_per_item: list of dict dengan actual_score & max_score per item."""
    from collections import defaultdict

    # ── Hitung weight dinamis per kategori ──
    # Group items by category
    cat_items = defaultdict(list)
    for i, di in enumerate(db_items):
        cat_items[di['cat']].append(i)

    # Ambil cat_weight dari DB
    try:
        conn_local = get_db()
        cur_local = conn_local.cursor()
        cur_local.execute("SELECT cat_code, cat_weight FROM origo.survey_categories")
        cat_weights = {r[0]: float(r[1]) for r in cur_local.fetchall()}
        cur_local.close()
        conn_local.close()
    except:
        cat_weights = {}

    # Hitung item weight per kategori
    item_weight_map = {}
    for cat, idxs in cat_items.items():
        cat_w = cat_weights.get(cat, 0)
        n = len(idxs)
        per_item = cat_w / n if n > 0 else 0
        for idx in idxs:
            item_weight_map[idx] = per_item

    total_actual = 0.0
    total_max = 0.0
    details = []
    for i, di in enumerate(db_items):
        item_weight = item_weight_map.get(i, 0)
        max_possible = item_weight * 1.0

        # Cari status dari status_data (kalo ada)
        sv = -1
        if i < len(status_data):
            s = status_data[i] if isinstance(status_data[i], dict) else {}
            st = s.get("status", "")
            try:
                sv = int(st)
            except (ValueError, TypeError):
                sv = -1

        # Item tidak terisi = score 0
        if sv < 0:
            actual = 0.0
        else:
            wm = 1.0
            for opt in di.get("options", []):
                if opt.get("score", -1) == sv:
                    wm = opt.get("weight_mult", 1.0)
                    break
            actual = item_weight * wm

        total_actual += actual
        total_max += max_possible
        details.append({
            "actual": actual,
            "max": max_possible,
            "pct": round(actual / max_possible * 100, 1) if max_possible > 0 else 0
        })
    weighted_score = round(total_actual / total_max * 100, 1) if total_max > 0 else 0
    weighted_baik = round(total_actual / total_max * 100, 1) if total_max > 0 else 0
    weighted_total = round(total_max, 2)
    return (weighted_score, weighted_baik, weighted_total, details)

def _get_cat_names():
    """Ambil kategori dari DB — return {code: {label, weight}}"""
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT cat_code, cat_name, cat_weight FROM origo.survey_categories WHERE is_active = true ORDER BY sort_order")
        d = {r[0]: {"name": r[1], "weight": float(r[2])*100} for r in cur.fetchall()}
        cur.close(); conn.close()
        return d
    except:
        return {"A": {"name":"Lokasi & Akses","weight":15},"B": {"name":"Identitas & Visibilitas","weight":10},"C": {"name":"Ruang Konsumen","weight":15},"D": {"name":"Fasilitas Karyawan","weight":10},"E": {"name":"Alat Kerja","weight":15},"F": {"name":"Keamanan & Barang Sitaan","weight":25},"G": {"name":"Dokumen & Regulasi","weight":10}}


def _get_type_options_map():
    """Ambil mapping type_code → list of option dicts dari DB"""
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("""
            SELECT t.type_code, o.opt_value::int, o.opt_label, o.weight_mult::float, o.sort_order, o.css_class, o.label_short
            FROM origo.survey_question_types t
            JOIN origo.survey_type_options o ON t.id = o.type_id
            ORDER BY t.type_code, o.sort_order
        """)
        result = {}
        for tc, ov, ol, wm, so, css, ls in cur.fetchall():
            if tc not in result:
                result[tc] = []
            result[tc].append({
                "score": ov, "label": ol, "weight_mult": wm,
                "sort_order": so, "css_class": css, "label_short": ls
            })
        cur.close(); conn.close()
        return result
    except Exception as e:
        import traceback; traceback.print_exc()
        return {}


def _get_menu():
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT label, icon, url FROM origo.nav_menu WHERE is_active = true ORDER BY sort_order")
        items = [{"label":r[0],"icon":r[1],"url":r[2]} for r in cur.fetchall()]
        cur.close(); conn.close()
        return items
    except:
        return []

def _get_items_from_db():
    """Ambil 50 items dari DB dengan semua kategori & options per type"""
    try:
        conn = get_db(); cur = conn.cursor()
        # Ambil options per question type
        cur.execute("""
            SELECT t.type_code, o.opt_value::int, o.opt_label, o.weight_mult::float, o.sort_order
            FROM origo.survey_question_types t
            JOIN origo.survey_type_options o ON t.id = o.type_id
            ORDER BY t.type_code, o.sort_order
        """)
        _type_options = {}
        for tc, ov, ol, wm, so in cur.fetchall():
            if tc not in _type_options:
                _type_options[tc] = []
            _type_options[tc].append({"score": ov, "label": ol, "weight_mult": wm, "sort_order": so})

        cur.execute("""
            SELECT i.item_idx, c.cat_code, i.label, i.tip, t.type_code, i.weight, i.wajib_foto_policy, i.helper, i.options_json, i.policy_if_no, i.allow_video
            FROM origo.survey_checklist_items i
            JOIN origo.survey_categories c ON i.cat_id = c.id
            JOIN origo.survey_question_types t ON i.type_id = t.id
            WHERE i.is_active = true
            ORDER BY i.item_idx
        """)
        items = []
        for r in cur.fetchall():
            type_code = r[4]
            per_item_opts = r[8] if r[8] else None  # options_json - custom per-item labels
            item_opts = None
            if per_item_opts and isinstance(per_item_opts, list) and len(per_item_opts) > 0:
                # Custom per-item options (for special items with unique labels)
                item_opts = []
                base_opts = _type_options.get(type_code, [])
                for i_opt in per_item_opts:
                    score_val = i_opt.get("score", i_opt.get("v", 0))
                    if isinstance(score_val, str):
                        score_val = int(score_val)
                    label_val = i_opt.get("label", i_opt.get("l", f"Nilai {score_val}"))
                    # Find matching base for weight_mult, or use explicit 'w' from options_json
                    wm = 1.0
                    if 'w' in i_opt:
                        wm = float(i_opt['w'])
                    else:
                        for bo in base_opts:
                            if bo["score"] == score_val:
                                wm = bo["weight_mult"]
                                break
                    item_opts.append({"score": score_val, "label": label_val, "weight_mult": wm})
            else:
                item_opts = _type_options.get(type_code, [])

            items.append({
                "idx": r[0], "cat": r[1], "label": r[2], "tip": r[3],
                "type": type_code, "weight": float(r[5]),
                "wajib_foto_policy": r[6], "helper": r[7],
                "options_json": r[8], "options": item_opts,
                "policy_if_no": r[9] if len(r) > 9 else False,
                "allow_video": r[10] if len(r) > 10 else False
            })
        cur.close(); conn.close()
        return items
    except Exception as e:
        import traceback; traceback.print_exc()
        return []

_ITEMS = _get_items_from_db()
ITEM_COUNT = len(_ITEMS)  # total item aktif

@router.get("/survey/kantor-checklist/dashboard", response_class=HTMLResponse)
async def survey_dashboard(request: Request, session: Optional[str] = Cookie(None), sort: str = Query(""), dir_order: str = Query("asc")):
    user = get_user_from_cookie(session)
    if not user:
        return HTMLResponse(status_code=302, headers={"Location": "/login"})

    total_branches = 0; done_main = 0; done_mt = 0
    merged = []; top5 = []; worst5 = []
    problem_items = []; best_items = []; worst_items = []; terbaru = []

    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT office_code, office_name FROM origo.network_branch_monitoring_master WHERE branch_type IN ('cbg_besar','cbg_kecil','pos','kios') AND office_code ~ '^[1-9][0-9]{4}$' AND office_code IN (SELECT n.office_code FROM origo.network_tree_node n JOIN origo.network_tree_version v ON n.version_id = v.id WHERE v.is_published = true AND n.office_code IS NOT NULL AND n.display_name IS NOT NULL AND n.branch_kind IN ('cbg_besar','cbg_kecil','pos','kios')) ORDER BY office_name")
        branches = {r[0]: r[1] for r in cur.fetchall()}
        total_branches = len(branches)

        cur.execute("SELECT kantor_code, yes_count, total_items, pic, tgl_cek, status_data, workflow_status, created_at, submitted_at FROM origo.kantor_checklist_data WHERE yes_count IS NOT NULL AND total_items > 0 ORDER BY tgl_cek DESC")
        main_scores = {}
        for r in cur.fetchall():
            earned = float(r[1]) if r[1] else 0
            total = float(r[2]) if r[2] else 1
            sc = round(earned / total * 100) if total > 0 else 0
            ca, sa = r[7], r[8]
            dur = round((sa - ca).total_seconds() / 60) if ca and sa else None
            main_scores[r[0]] = {"score": sc, "pic": r[3] or "", "tgl": str(r[4]) if r[4] else "", "workflow": r[6] or "", "diu": dur}
        done_submit = len([x for x in main_scores.values() if x.get("workflow") == "submitted"])
        done_draft = len([x for x in main_scores.values() if x.get("workflow") == "draft"])
        done_main = len(main_scores)
        cur.close(); conn.close()

        # Fetch branch area/wilayah info
        _branch_area = {}
        try:
            _conn2 = get_db(); _cur2 = _conn2.cursor()
            _cur2.execute("""
                WITH RECURSIVE tree AS (
                    SELECT id, parent_id, node_code, display_name, branch_kind, office_code,
                           1 AS depth, CAST(node_code AS text) AS path_code, CAST(display_name AS text) AS path_name
                    FROM origo.network_tree_node
                    WHERE version_id = (SELECT id FROM origo.network_tree_version WHERE is_published = TRUE LIMIT 1)
                      AND parent_id IS NULL
                    UNION ALL
                    SELECT n.id, n.parent_id, n.node_code, n.display_name, n.branch_kind, n.office_code,
                           t.depth + 1,
                           t.path_code || '>' || n.node_code,
                           t.path_name || ' > ' || n.display_name
                    FROM origo.network_tree_node n
                    JOIN tree t ON n.parent_id = t.id
                    WHERE n.version_id = (SELECT id FROM origo.network_tree_version WHERE is_published = TRUE LIMIT 1)
                )
                SELECT office_code, display_name, path_code, path_name
                FROM tree
                WHERE branch_kind NOT IN ('area','wilayah') AND office_code IS NOT NULL
            """)
            for _r in _cur2.fetchall():
                _oc = _r[0]
                _pc = (_r[2] or "").split(">")
                _pn = (_r[3] or "").split(" > ")
                _branch_area[_oc] = {
                    "area_code": _pc[1] if len(_pc) >= 2 else "?",
                    "area_name": _pn[1] if len(_pn) >= 2 else "?",
                    "wilayah_code": _pc[2] if len(_pc) >= 3 else _pc[1] if len(_pc) >= 2 else "?",
                    "wilayah_name": _pn[2] if len(_pn) >= 3 else _pn[1] if len(_pn) >= 2 else "?",
                }
            _cur2.close(); _conn2.close()
        except Exception:
            pass

        for k, n in branches.items():
            m = main_scores.get(k)
            ba = _branch_area.get(k, {})
            merged.append({"kode": k, "label": n, "main": m["score"] if m else None, "main_pic": m["pic"] if m else None, "main_durasi": m["diu"] if m else None, "main_tgl": m["tgl"] if m else None, "main_workflow": m["workflow"] if m else None, "area_code": ba.get("area_code", "?"), "area_name": ba.get("area_name", "?"), "wilayah_code": ba.get("wilayah_code", "?"), "wilayah_name": ba.get("wilayah_name", "?")})



        scored = [x for x in merged if x["main"] is not None]
        ss = sorted(scored, key=lambda x: x["main"], reverse=True)
        top5 = ss[:5]; worst5 = list(reversed(ss))[:5]

        # ── Enhanced Problem Items with Weighted Score, Priority, Per-Kantor Breakdown ──
        dbitems_ic = _get_items_from_db()
        conn = get_db(); cur = conn.cursor()
        # Ambil status_data + kantor_code dari semua survey - hitung distribusi per opsi per item
        cur.execute("SELECT kcd.kantor_code, kcd.pic, kcd.status_data, COALESCE(nbmm.office_name, kcd.kantor_code) FROM origo.kantor_checklist_data kcd LEFT JOIN origo.network_branch_monitoring_master nbmm ON kcd.kantor_code = nbmm.office_code WHERE kcd.status_data IS NOT NULL")
        ic = {}; ic_count = {}; ic_baik = {}; ic_kurang = {}; twd = 0
        item_kantor_map = {}  # item_idx -> [{kantor_code, status, pic, sv}]
        for (kode_kc, pic_kc, sd, nama_kc) in cur.fetchall():
            if not sd: continue
            twd += 1
            for i, s in enumerate(sd):
                if i >= len(dbitems_ic): break
                st = s.get("status","") if isinstance(s,dict) else s
                try:
                    sv = int(st)
                    ic[i] = ic.get(i,0) + 1
                    if sv not in ic_count.setdefault(i, {}):
                        ic_count[i][sv] = 0
                    ic_count[i][sv] += 1
                    if sv == 0:
                        ic_baik[i] = ic_baik.get(i,0) + 1
                    else:
                        ic_kurang[i] = ic_kurang.get(i,0) + 1
                    # Per-kantor breakdown
                    # Extract foto path + AI relevance for this item
                    foto_path = s.get("foto", "") if isinstance(s, dict) else ""
                    foto_relevan = s.get("foto_relevan", True) if isinstance(s, dict) else True
                    foto_desc = s.get("foto_desc", "") if isinstance(s, dict) else ""
                    if i not in item_kantor_map:
                        item_kantor_map[i] = []
                    item_kantor_map[i].append({
                        "kantor_code": kode_kc,
                        "nama_kantor": str(nama_kc or ""),
                        "pic": str(pic_kc or ""),
                        "status": sv,
                        "foto": foto_path,
                        "foto_relevan": foto_relevan if isinstance(foto_relevan, bool) else str(foto_relevan).lower() == 'true',
                        "foto_desc": str(foto_desc or "")
                    })
                except: pass
        cur.close(); conn.close()
        # Ambil opt_labels + weight_mult dari DB untuk tipe pertanyaan
        conn_ol = get_db()
        cur_ol = conn_ol.cursor()
        cur_ol.execute("""
            SELECT t.type_code, o.opt_value::int, o.opt_label, COALESCE(o.is_no, false), o.weight_mult::float
            FROM origo.survey_question_types t
            JOIN origo.survey_type_options o ON t.id = o.type_id
            ORDER BY t.type_code, o.sort_order
        """)
        opt_labels = {}
        opt_weights = {}
        for tc, ov, lbl, inh, wm in cur_ol.fetchall():
            opt_labels.setdefault(tc, {})[ov] = {"label": lbl, "is_no": inh}
            opt_weights.setdefault(tc, {})[ov] = wm
        cur_ol.close(); conn_ol.close()

        # Bangun problem_items dengan weighted score + priority + kantor breakdown
        problem_items = []
        for i in sorted(ic.keys()):
            if i >= len(dbitems_ic): continue
            tc = dbitems_ic[i]["type"]
            item_w = dbitems_ic[i]["weight"]
            total_responses = ic.get(i, 0)

            # Weighted average: sum of (count * weight_mult) / total_responses
            weighted_sum = 0.0
            opts_list = []
            for ov, oi in sorted(opt_labels.get(tc, {}).items()):
                cnt = ic_count.get(i, {}).get(ov, 0)
                wm = opt_weights.get(tc, {}).get(ov, 0.0)
                weighted_sum += cnt * wm
                opts_list.append({
                    "val": ov, "count": cnt,
                    "label": oi["label"], "is_no": oi["is_no"]
                })

            avg_score = round(weighted_sum / total_responses * 100, 1) if total_responses > 0 else 0

            baik = ic_baik.get(i, 0)
            kurang = ic_kurang.get(i, 0)

            # Priority = (kurang/total) * (1 - avg_score/100) * item_weight
            kurang_ratio = kurang / total_responses if total_responses > 0 else 0
            score_gap = 1 - (avg_score / 100)
            priority_score = round(kurang_ratio * score_gap * item_w, 4)

            # Count AI foto warnings for this item
            foto_issues = sum(1 for k in item_kantor_map.get(i, []) if not k.get("foto_relevan", True))

            problem_items.append({
                "idx": i,
                "cat": dbitems_ic[i]["cat"],
                "label": dbitems_ic[i]["label"],
                "type": tc,
                "weight": item_w,
                "total": total_responses,
                "opts": opts_list,
                "avg_score": avg_score,
                "baik": baik,
                "kurang": kurang,
                "priority": priority_score,
                "foto_issues": foto_issues,
                "kantors": item_kantor_map.get(i, [])
            })

        # Sort by priority descending
        problem_items.sort(key=lambda x: -x["priority"])
        # Re-assign index after sort
        for pi, pit in enumerate(problem_items):
            pit["rank"] = pi + 1

        # Compute priority thresholds
        priorities = [p["priority"] for p in problem_items if p["priority"] > 0]
        if priorities:
            import statistics
            priority_median = statistics.median(priorities)
        else:
            priority_median = 0
        priority_high = priority_median * 1.5

        # Mark priority level
        for pit in problem_items:
            if pit["priority"] >= priority_high and priority_high > 0:
                pit["priority_label"] = "tinggi"
            elif pit["priority"] >= priority_median and priority_median > 0:
                pit["priority_label"] = "sedang"
            else:
                pit["priority_label"] = "rendah"

        # Best/worst by avg_score (not yes_pct) - use stored .idx from problem_items
        best_items = sorted(problem_items, key=lambda x: -x["avg_score"])[:5]
        worst_items = sorted([p for p in problem_items if p["avg_score"] > 0], key=lambda x: x["avg_score"])[:5]

        # Extract kantor breakdown for client-side expandable rows - ALL kantor
        # Get opt_labels for status labels
        conn_ol2 = get_db()
        cur_ol2 = conn_ol2.cursor()
        cur_ol2.execute("""
            SELECT t.type_code, o.opt_value::int, o.opt_label, COALESCE(o.is_no, false)
            FROM origo.survey_question_types t
            JOIN origo.survey_type_options o ON t.id = o.type_id
            ORDER BY t.type_code, o.sort_order
        """)
        opt_labels_all = {}
        for tc, ov, lbl, inh in cur_ol2.fetchall():
            opt_labels_all.setdefault(tc, {})[ov] = {"label": lbl, "is_no": inh}
        cur_ol2.close(); conn_ol2.close()

        kantor_breakdown = {}
        for pit in problem_items:
            item_idx = pit["idx"]
            tc = pit["type"]
            ol = opt_labels_all.get(tc, {})
            kantor_breakdown[item_idx] = [
                {
                    "kantor_code": k["kantor_code"],
                    "nama_kantor": k.get("nama_kantor", ""),
                    "pic": k["pic"],
                    "status": k["status"],
                    "status_label": ol.get(k["status"], {}).get("label", f"Status {k['status']}"),
                    "status_is_no": ol.get(k["status"], {}).get("is_no", False),
                    "foto": k.get("foto", ""),
                    "foto_relevan": k.get("foto_relevan", True),
                    "foto_desc": k.get("foto_desc", "")[:120]
                }
                for k in item_kantor_map.get(item_idx, [])
            ]

        latest = sorted([x for x in merged if x["main_tgl"]], key=lambda x: x["main_tgl"] or "", reverse=True)[:3]
        sl = [x["main"] for x in scored]
        avg_main = round(sum(sl)/len(sl)) if sl else 0
        dl = [x["main_durasi"] for x in merged if x["main_durasi"] is not None]
        avg_dur = round(sum(dl)/len(dl)) if dl else 0
    except Exception as e:
        import traceback; traceback.print_exc()

    if 'latest' not in locals(): latest = []
    if 'sl' not in locals(): sl = []
    if 'avg_main' not in locals(): avg_main = 0
    if 'dl' not in locals(): dl = []
    if 'avg_dur' not in locals(): avg_dur = 0

    mws = [x for x in merged if x["main"] is not None]
    dr = [x for x in merged if x.get("main_workflow") == "draft"]

    # ── Analisa Dokumentasi ──
    foto_warnings_list = []
    foto_referensi = {}  # item_idx -> {status_val: {kode, foto, desc}}
    dbi_fw = _get_items_from_db()
    try:
        conn_fw = get_db(); cur_fw = conn_fw.cursor()
        cur_fw.execute("""
            SELECT kantor_code, pic, tgl_cek, status_data
            FROM origo.kantor_checklist_data
            WHERE status_data IS NOT NULL AND jsonb_array_length(status_data) > 0
            ORDER BY tgl_cek DESC
        """)
        for (kode_fw, pic_fw, tgl_fw, sd_fw) in cur_fw.fetchall():
            for i_fw, s_fw in enumerate(sd_fw):
                if i_fw >= len(dbi_fw): break
                if not isinstance(s_fw, dict): continue
                frelevan = s_fw.get("foto_relevan", True)
                fdesc = s_fw.get("foto_desc", "")
                fp = s_fw.get("foto", "")
                st = s_fw.get("status", "")
                try: sv = int(st)
                except: sv = -1

                # Warning untuk foto tidak sesuai
                if fp and frelevan == False:
                    foto_warnings_list.append({
                        "kode": kode_fw,
                        "pic": str(pic_fw or ""),
                        "tgl": str(tgl_fw)[:10] if tgl_fw else "",
                        "cat": dbi_fw[i_fw]["cat"],
                        "item": dbi_fw[i_fw]["label"],
                        "desc": (fdesc or "Foto tidak sesuai")[:100],
                        "status_value": sv
                    })

                # Kumpulkan foto referensi - cari yang relevan per item per status
                # Simpan foto dengan skor: relevan=true > relevan=false, score rendah > score tinggi
                if fp and sv >= 0:
                    if i_fw not in foto_referensi:
                        foto_referensi[i_fw] = {}
                    if sv not in foto_referensi[i_fw]:
                        foto_referensi[i_fw][sv] = []
                    foto_referensi[i_fw][sv].append({
                        "kode": kode_fw,
                        "foto": fp,
                        "desc": fdesc[:80],
                        "relevan": frelevan,
                        "score": sv
                    })

        # Sort & pilih foto terbaik per item per status - prioritaskan relevan=true
        for idx in foto_referensi:
            for sv in foto_referensi[idx]:
                foto_referensi[idx][sv].sort(key=lambda x: (0 if x["relevan"] else 1, x["score"]))
                foto_referensi[idx][sv] = foto_referensi[idx][sv][:3]  # max 3 foto per status

        cur_fw.close(); conn_fw.close()
    except Exception:
        import traceback; traceback.print_exc()
        foto_warnings_list = []
        foto_referensi = {}
    all_sessions = []
    try:
        conn_all = get_db()
        cur_all = conn_all.cursor()
        cur_all.execute("""
            SELECT kantor_code, pic, tgl_cek, workflow_status, yes_count, total_items, created_at
            FROM origo.kantor_checklist_data
            ORDER BY updated_at DESC
        """)
        for r_all in cur_all.fetchall():
            yes_f = float(r_all[4]) if r_all[4] else 0
            tot_f = float(r_all[5]) if r_all[5] else 1
            score_s = round(yes_f / tot_f * 100) if tot_f > 0 else 0
            all_sessions.append({
                "kode": r_all[0], "pic": r_all[1] or "", "tgl": str(r_all[2]) if r_all[2] else "",
                "workflow": r_all[3] or "", "score": score_s
            })
        cur_all.close(); conn_all.close()
    except Exception:
        pass

    # ── Trend: membaik/memburuk/stabil - bandingkan skor antar survey (Feature #3) ──
    trend_icon = "➡️"
    try:
        conn_tr = get_db(); cur_tr = conn_tr.cursor()
        cur_tr.execute(
            """SELECT kantor_code, survey_seq, weighted_score
               FROM origo.kantor_checklist_data
               WHERE yes_count IS NOT NULL AND total_items > 0 AND weighted_score IS NOT NULL
               ORDER BY kantor_code, survey_seq ASC"""
        )
        kantor_scores = {}
        for r_tr in cur_tr.fetchall():
            kc_tr, seq_tr, ws_tr = r_tr
            if kc_tr not in kantor_scores:
                kantor_scores[kc_tr] = []
            kantor_scores[kc_tr].append(float(ws_tr))
        cur_tr.close(); conn_tr.close()

        better = 0
        worse = 0
        for kc_tr, scs in kantor_scores.items():
            if len(scs) >= 2:
                if scs[-1] > scs[-2]:
                    better += 1
                elif scs[-1] < scs[-2]:
                    worse += 1
        if better > worse:
            trend_icon = "📈"
        elif worse > better:
            trend_icon = "📉"
        else:
            trend_icon = "➡️"
    except Exception:
        trend_icon = "➡️"

    ctl = _get_cat_names()

    import json
    item_kantors_json_str = json.dumps(kantor_breakdown, default=str)

    # ── Feature #2: Area/Wilayah Summaries ──
    area_summaries = []
    try:
        from collections import defaultdict
        area_groups = defaultdict(lambda: {"area_code": "?", "area_name": "?", "branches": [], "scores": [], "submitted": 0, "draft": 0, "total": 0})
        wilayah_groups = defaultdict(lambda: {"area_code": "?", "area_name": "?", "wilayah_code": "?", "wilayah_name": "?", "branches": [], "scores": [], "submitted": 0, "draft": 0, "total": 0})
        for m in merged:
            ac = m.get("area_code", "?")
            an = m.get("area_name", "?")
            wc = m.get("wilayah_code", "?")
            wn = m.get("wilayah_name", "?")
            sc = m.get("main")
            wf = m.get("main_workflow", "")
            wk = f"{ac}>{wc}"
            # Area
            area_groups[ac]["area_code"] = ac
            area_groups[ac]["area_name"] = an
            area_groups[ac]["total"] += 1
            if sc is not None:
                area_groups[ac]["scores"].append(sc)
                if wf in ("submitted", "final"):
                    area_groups[ac]["submitted"] += 1
            if wf == "draft":
                area_groups[ac]["draft"] += 1
            # Wilayah
            wilayah_groups[wk]["area_code"] = ac
            wilayah_groups[wk]["area_name"] = an
            wilayah_groups[wk]["wilayah_code"] = wc
            wilayah_groups[wk]["wilayah_name"] = wn
            wilayah_groups[wk]["total"] += 1
            if sc is not None:
                wilayah_groups[wk]["scores"].append(sc)
                if wf in ("submitted", "final"):
                    wilayah_groups[wk]["submitted"] += 1
            if wf == "draft":
                wilayah_groups[wk]["draft"] += 1
        # Build area summaries with nested wilayah
        for ac in sorted(area_groups.keys()):
            ag = area_groups[ac]
            wilayah_list = []
            for wk in sorted(wilayah_groups.keys()):
                wg = wilayah_groups[wk]
                if wg["area_code"] == ac:
                    avg_w = round(sum(wg["scores"]) / len(wg["scores"]), 1) if wg["scores"] else None
                    draft_w = wg["draft"] if wg.get("draft") else 0
                    wilayah_list.append({
                        "wilayah_code": wg["wilayah_code"],
                        "wilayah_name": wg["wilayah_name"],
                        "total": wg["total"],
                        "submitted": wg["submitted"],
                        "draft": draft_w,
                        "avg_score": avg_w,
                    })
            avg_a = round(sum(ag["scores"]) / len(ag["scores"]), 1) if ag["scores"] else None
            pct_a = round(ag["submitted"] / ag["total"] * 100, 1) if ag["total"] > 0 else 0
            draft_a = ag["draft"] if ag.get("draft") else 0
            belum_a = ag["total"] - ag["submitted"] - draft_a
            area_summaries.append({
                "area_code": ac,
                "area_name": ag["area_name"],
                "total": ag["total"],
                "submitted": ag["submitted"],
                "draft": draft_a,
                "belum": belum_a,
                "avg_score": avg_a,
                "pct_complete": pct_a,
                "wilayahs": wilayah_list,
            })
    except Exception:
        pass

    # ── Feature #3: PIC Activity Stats (replaced findings_list) ──
    pic_activities = []
    active_pic_count = 0
    draft_count = 0
    today_submit_count = 0
    total_pic = 0
    try:
        conn_pic = get_db(); cur_pic = conn_pic.cursor()
        cur_pic.execute("""
            SELECT kd.pic,
                   kd.kantor_code,
                   kd.kantor_label,
                   kd.workflow_status,
                   GREATEST(COALESCE(kd.updated_at, '1970-01-01'::timestamp),
                            COALESCE(kd.submitted_at, '1970-01-01'::timestamp)) as last_activity,
                   (SELECT COUNT(*) FROM origo.kantor_checklist_data kd2
                    WHERE kd2.pic = kd.pic AND DATE(kd2.submitted_at) = CURRENT_DATE) as today_count
            FROM origo.kantor_checklist_data kd
            WHERE kd.pic IS NOT NULL AND kd.pic != ''
            ORDER BY last_activity DESC
        """)
        now_pic = datetime.now()
        seen_pics = set()
        unique_pics = set()
        for r in cur_pic.fetchall():
            pic_id = r[0]
            kantor_code = r[1]
            kantor_label = r[2]
            workflow = r[3]
            last_act = r[4]
            today_cnt = r[5]

            unique_pics.add(pic_id)

            if workflow == 'draft':
                draft_count += 1

            if workflow == 'submitted' and today_cnt and today_cnt > 0:
                today_submit_count += 1

            # Avoid duplicates: only first (most recent) row per PIC
            if pic_id in seen_pics:
                continue
            seen_pics.add(pic_id)

            # Classify status
            if workflow == 'submitted':
                status = '✅ kirim'
            elif last_act and (now_pic - last_act).total_seconds() < 1800:  # < 30 min
                status = '🟡 isi'
                active_pic_count += 1
            else:
                status = '💤 tidur'

            # Idle time
            idle_hours = None
            idle_display = ''
            if last_act and workflow == 'draft':
                idle_sec = int((now_pic - last_act).total_seconds())
                if idle_sec < 60:
                    idle_display = f'{idle_sec} detik'
                elif idle_sec < 3600:
                    idle_display = f'{idle_sec // 60} menit'
                elif idle_sec < 86400:
                    idle_display = f'{idle_sec // 3600} jam'
                else:
                    idle_display = f'{idle_sec // 86400} hari'
                idle_hours = round(idle_sec / 3600, 1)
            elif workflow == 'submitted':
                idle_display = '-'

            # Since display
            sejak_display = ''
            if last_act:
                diff_sec = int((now_pic - last_act).total_seconds())
                if diff_sec < 60:
                    sejak_display = 'baru saja'
                elif diff_sec < 3600:
                    sejak_display = f'{diff_sec // 60} menit'
                elif diff_sec < 86400:
                    sejak_display = last_act.strftime('%H:%M')
                else:
                    sejak_display = last_act.strftime('%d/%m %H:%M')

            pic_activities.append({
                'pic': pic_id,
                'kantor_code': kantor_code,
                'kantor_label': kantor_label,
                'status': status,
                'workflow': workflow,
                'sejak': sejak_display,
                'idle': idle_display,
                'idle_hours': idle_hours,
                'today_count': today_cnt,
                'last_activity': last_act,
            })

        total_pic = len(unique_pics)
        cur_pic.close(); conn_pic.close()
    except Exception as e:
        print(f"[PIC Activity] Error: {e}")
        import traceback
        traceback.print_exc()

    return TemplateResponse("survey_dashboard.html", {"request": request, "user_id": user["user_id"], "user_name": user["fullname"], "fullname": user["fullname"], "fullname": user["fullname"], "user_role": user.get("role",""), "current_path": "/survey/kantor-checklist/dashboard", "total_branches": total_branches, "done_main": done_main, "done_submit": done_submit, "done_draft": done_draft, "done_mt": done_mt, "merged": merged, "top5": top5, "worst5": worst5, "problem_items": problem_items, "best_items": best_items, "worst_items": worst_items, "terbaru": latest, "merged_with_score": mws, "scores_list": sl, "draft_list": dr, "avg_dur": avg_dur, "avg_main": avg_main, "k": ctl, "v": ctl, "cat_names": ctl, "all_sessions": all_sessions, "menu_items": _get_menu(), "foto_warnings": foto_warnings_list, "foto_referensi": foto_referensi, "db_items_ref": dbi_fw, "item_kantors_json": item_kantors_json_str, "trend_icon": trend_icon, "area_summaries": area_summaries, "pic_activities": pic_activities, "active_pic_count": active_pic_count, "draft_count": draft_count, "today_submit_count": today_submit_count, "total_pic": total_pic})

@router.get("/survey/api/kantor-checklist/dashboard-data")
async def dashboard_data_api(request: Request, session: Optional[str] = Cookie(None), cat: str = Query(""), item: str = Query(""), kantor_code: str = Query("")):
    user = get_user_from_cookie(session)
    if not user:
        return JSONResponse({"ok": False, "error": "Not logged in"}, status_code=401)

    try:
        conn = get_db(); cur = conn.cursor()

        # Ambil sessions berdasarkan filter kantor
        if kantor_code:
            cur.execute("""
                SELECT kantor_code, nomor_survei, survey_seq, status_data, yes_count, no_count, total_items, workflow_status
                FROM origo.kantor_checklist_data
                WHERE kantor_code = %s AND status_data IS NOT NULL AND jsonb_array_length(status_data) > 0
                ORDER BY survey_seq ASC
            """, (kantor_code,))
        else:
            cur.execute("""
                SELECT kantor_code, nomor_survei, survey_seq, status_data, yes_count, no_count, total_items, workflow_status
                FROM origo.kantor_checklist_data
                WHERE status_data IS NOT NULL AND jsonb_array_length(status_data) > 0
            """)

        sessions = []
        all_status = []
        for r in cur.fetchall():
            kc = r[0]
            sd = r[3]
            all_status.extend([s.get("status") if isinstance(s, dict) else s for s in sd] if sd else [])
            sessions.append({
                    "kantor_code": kc,
                    "nomor_survei": r[1],
                    "survey_seq": r[2],
                    "status_data_raw": sd,
                    "stats": {"yes": float(r[4] or 0), "no": float(r[5] or 0), "total": float(r[6] or 0)},
                    "status_data": [s.get("status") if isinstance(s, dict) else s for s in sd] if sd else []
                })

        # ── Perbandingan antar survei ──
        comparisons = []
        if len(sessions) >= 2:
            prev = sessions[-2]
            latest = sessions[-1]
            pd_prev = prev.get("status_data_raw", [])
            pd_latest = latest.get("status_data_raw", [])
            for di_idx in range(len(dbitems)):
                sv_prev = 99
                sv_latest = 99
                if di_idx < len(pd_prev) and isinstance(pd_prev[di_idx], dict):
                    try: sv_prev = int(pd_prev[di_idx].get("status", 99))
                    except: pass
                if di_idx < len(pd_latest) and isinstance(pd_latest[di_idx], dict):
                    try: sv_latest = int(pd_latest[di_idx].get("status", 99))
                    except: pass

                if sv_prev == 99 and sv_latest == 99:
                    trend = "unknown"
                elif sv_prev == 99:
                    trend = "new"
                elif sv_latest < sv_prev:
                    trend = "membaik"
                elif sv_latest > sv_prev:
                    trend = "memburuk"
                else:
                    trend = "stabil"
                comparisons.append({"idx": di_idx, "trend": trend, "prev_status": sv_prev if sv_prev != 99 else None, "latest_status": sv_latest if sv_latest != 99 else None})

        # Ambil items dari DB untuk filter + mapping
        dbitems = _get_items_from_db()
        if not dbitems:
            return JSONResponse({"ok": False, "error": "No items in DB"}, status_code=500)

        # Ambil semua opsi dari DB - weight_mult + label + is_no per tipe pertanyaan
        cur2 = conn.cursor()
        cur2.execute("""
            SELECT t.type_code, o.opt_value::int, o.weight_mult, o.opt_label, COALESCE(o.is_no, false)
            FROM origo.survey_question_types t
            JOIN origo.survey_type_options o ON t.id = o.type_id
            ORDER BY t.type_code, o.sort_order
        """)
        wm_map = {}
        opt_labels = {}  # type_code -> {opt_value: {label, is_no}}
        for tc, ov, wm, lbl, inh in cur2.fetchall():
            wm_map.setdefault(tc, {})[ov] = float(wm)
            opt_labels.setdefault(tc, {})[ov] = {"label": lbl, "is_no": inh}
        cur2.close()

        # Ambil categories + bobot
        cur2 = conn.cursor()
        cur2.execute("SELECT cat_code, cat_name, cat_weight FROM origo.survey_categories")
        cats_data = {r[0]: {"name": r[1], "weight": float(r[2])} for r in cur2.fetchall()}
        cur2.close()

        # Kumpulin stat per opsi: {item_idx: {opt_value: count, ...}}
        ist = {i: {"total": 0, "score_sum": 0.0, "opts": {}} for i in range(len(dbitems))}
        for st in all_status:
            try: sv = int(st)
            except: continue
            for i in range(len(dbitems)):
                tc = dbitems[i]["type"]
                wm = wm_map.get(tc, {}).get(sv, 0.0)
                ist[i]["total"] += 1
                ist[i]["opts"][sv] = ist[i]["opts"].get(sv, 0) + 1
                ist[i]["score_sum"] += wm
        cur.close(); conn.close()

        # Hitung weighted score per item + per kategori
        detail = []
        cat_scores = {k: {"score": 0.0, "total_weight": 0.0} for k in cats_data}

        for i in range(len(dbitems)):
            if cat and dbitems[i]["cat"] != cat: continue
            if item and str(i) != item: continue
            s = ist[i]
            item_w = dbitems[i]["weight"]
            cat_c = dbitems[i]["cat"]
            cat_w = cats_data.get(cat_c, {}).get("weight", 1.0)

            # avg_raw = rata-rata weight_mult per item dari semua survei (0-1)
            # avg_score = persentase (0-100%)
            if ist[i]["total"] > 0:
                avg_raw = s["score_sum"] / ist[i]["total"]
            else:
                avg_raw = 0

            # Skor per item: rata-rata weight_mult (0-1), dikali 100 jadi persen
            item_score = round(avg_raw * 100, 1) if avg_raw > 0 else 0

            # Opsi dinamis - pake label & is_no dari DB per tipe
            tc = dbitems[i]["type"]
            item_opts = []
            for ov in sorted(ist[i]["opts"].keys()):
                ol = opt_labels.get(tc, {}).get(ov, {})
                item_opts.append({
                    "val": ov,
                    "count": ist[i]["opts"][ov],
                    "label": ol.get("label", f"Nilai {ov}"),
                    "is_no": ol.get("is_no", False)
                })

            detail.append({
                "idx": i, "cat": cat_c,
                "label": dbitems[i]["label"],
                "weight": item_w,
                "avg_score": item_score,
                "opts": item_opts,
                "total_dinilai": ist[i]["total"]
            })
            # Bobot kontribusi ke kategori = item_weight * category_weight
            # score_sum: rata-rata weight_mult * total_survei × item_w × cat_w
            if ist[i]["total"] > 0:
                cat_score = (s["score_sum"] / ist[i]["total"]) * item_w * cat_w * 100
            else:
                cat_score = 0
            cat_scores[cat_c]["score"] += cat_score
            cat_scores[cat_c]["total_weight"] += item_w * cat_w * 100

        cat_summary = {}
        for k, v in cats_data.items():
            cs = cat_scores[k]
            cat_pct = round(cs["score"] / cs["total_weight"] * 100, 1) if cs["total_weight"] > 0 else 0
            cat_summary[k] = {"name": v["name"], "score": cat_pct, "weight": v["weight"]}

        return {"ok": True, "items": detail, "total_items": len(detail), "cats": cat_summary, "cat_filter": cat, "item_filter": item, "sessions": sessions, "comparisons": comparisons}
    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@router.get("/survey/api/kantor-checklist/list-sessions")
async def survey_list_sessions(request: Request, session: Optional[str] = Cookie(None), limit: int = 200):
    user = get_user_from_cookie(session)
    if not user:
        return JSONResponse({"ok": False, "error": "Not logged in"}, status_code=401)
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT kantor_code, pic, tgl_cek, yes_count, total_items, no_count, weighted_score, created_at, updated_at, workflow_status, submitted_at, updated_by FROM origo.kantor_checklist_data ORDER BY updated_at DESC LIMIT %s", (limit,))
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for d in rows:
            cur.execute("SELECT display_name FROM origo.network_tree_node WHERE office_code=%s LIMIT 1", (d.get("kantor_code",""),))
            lbl = cur.fetchone()
            d["kantor_label"] = lbl[0] if lbl else d.get("kantor_code","")
            d["tgl_cek"] = str(d["tgl_cek"]) if d.get("tgl_cek") else ""
            d["created_at"] = str(d["created_at"]) if d.get("created_at") else ""
            d["updated_at"] = str(d["updated_at"]) if d.get("updated_at") else ""
            d["submitted_at"] = str(d["submitted_at"]) if d.get("submitted_at") else ""
            d["workflow"] = d.get("workflow_status", "draft")
            # Pake weighted_score kalo ada, fallback ke yes/total
            ws_col = d.get("weighted_score")
            if ws_col is not None:
                d["score"] = round(float(ws_col))
            else:
                yes = float(d.get("yes_count") or 0)
                total = float(d.get("total_items") or 1)
                d["score"] = round(yes / total * 100) if total > 0 else 0
        cur.close(); conn.close()
        return {"ok": True, "sessions": rows}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@router.post("/survey/api/kantor-checklist/delete-session")
async def survey_delete_session(request: Request, session: Optional[str] = Cookie(None)):
    user = get_user_from_cookie(session)
    if not user:
        return JSONResponse({"ok": False, "error": "Not logged in"}, status_code=401)
    if user.get("user_id") != "17012956":
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=403)

    form_data = await request.form()
    kode = form_data.get('kantor_code', '').strip()
    if not kode:
        return JSONResponse({"ok": False, "error": "kantor_code required"}, status_code=400)

    try:
        conn = get_db(); cur = conn.cursor()
        # Ambil dulu semua foto path sebelum delete
        cur.execute("SELECT status_data FROM origo.kantor_checklist_data WHERE kantor_code=%s ORDER BY survey_seq", (kode,))
        foto_files = []
        for (sd_row,) in cur.fetchall():
            if sd_row:
                for item in (sd_row if isinstance(sd_row, list) else []):
                    fp = item.get("foto", "") if isinstance(item, dict) else ""
                    if fp:
                        foto_files.append(fp)

        cur.execute("DELETE FROM origo.kantor_checklist_data WHERE kantor_code=%s RETURNING kantor_code", (kode,))
        row = cur.fetchone()
        conn.commit(); cur.close(); conn.close()

        # Hapus file foto di filesystem
        deleted_files = 0
        PHOTO_DIR = "/home/bhc0104/survey_app/uploads"
        for fp in foto_files:
            fname = fp.split("/")[-1]  # /survey/uploads/xxx.jpg → xxx.jpg
            fpath = os.path.join(PHOTO_DIR, fname)
            if os.path.exists(fpath):
                os.remove(fpath)
                deleted_files += 1

        if row:
            return {"ok": True, "deleted": kode, "foto_hapus": deleted_files}
        else:
            return JSONResponse({"ok": False, "error": "No data found"}, status_code=404)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@router.post("/survey/api/kantor-checklist/hapus-session")
async def survey_hapus_session(request: Request, session: Optional[str] = Cookie(None)):
    user = get_user_from_cookie(session)
    if not user:
        return JSONResponse({"ok": False, "error": "Not logged in"}, status_code=401)
    if user.get("user_id") != "17012956":
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=403)

    form = await request.form()
    kode = form.get("kantor_code", "")
    if not kode:
        return JSONResponse({"ok": False, "error": "kantor_code required"}, status_code=400)

    try:
        conn = get_db(); cur = conn.cursor()
        # Ambil dulu semua foto path sebelum delete
        cur.execute("SELECT status_data FROM origo.kantor_checklist_data WHERE kantor_code=%s ORDER BY survey_seq", (kode,))
        foto_files = []
        for (sd_row,) in cur.fetchall():
            if sd_row:
                for item in (sd_row if isinstance(sd_row, list) else []):
                    fp = item.get("foto", "") if isinstance(item, dict) else ""
                    if fp:
                        foto_files.append(fp)

        cur.execute("DELETE FROM origo.kantor_checklist_data WHERE kantor_code=%s RETURNING kantor_code", (kode,))
        row = cur.fetchone()
        conn.commit(); cur.close(); conn.close()

        # Hapus file foto di filesystem
        deleted_files = 0
        PHOTO_DIR = "/home/bhc0104/survey_app/uploads"
        for fp in foto_files:
            fname = fp.split("/")[-1]
            fpath = os.path.join(PHOTO_DIR, fname)
            if os.path.exists(fpath):
                os.remove(fpath)
                deleted_files += 1

        if row:
            return {"ok": True, "deleted": kode, "kode": kode, "foto_hapus": deleted_files}
        else:
            return JSONResponse({"ok": False, "error": "Data tidak ditemukan"}, status_code=404)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# ── Helper dinamis (server-side) ──
@router.post("/survey/api/kantor-checklist/helper-status")
async def helper_status(request: Request, session: Optional[str] = Cookie(None)):
    user = get_user_from_cookie(session)
    if not user:
        return JSONResponse({"ok": False, "error": "Not logged in"}, status_code=401)

    form_data = await request.form()
    try: idx = int(form_data.get('idx', -1))
    except: idx = -1
    value = form_data.get('value', '0')

    if idx < 0:
        return JSONResponse({"ok": False, "error": "Invalid idx"}, status_code=400)

    sv = int(value)

    # Ambil helper_foto langsung dari DB
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT helper_foto FROM origo.survey_checklist_items WHERE item_idx = %s AND is_active = true",
        (idx,)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return JSONResponse({"ok": False, "error": "Item not found"}, status_code=404)

    hf = row[0] or {}
    msg = hf.get(str(sv), "")
    if not msg and sv == 0:
        msg = "✅ Kondisi baik"

    return {"ok": True, "helper": msg, "idx": idx}

# ── Auto-save (perubahan status/catatan/foto realtime) ──
@router.post("/survey/api/kantor-checklist/new-survey")
async def api_new_survey(request: Request, session: Optional[str] = Cookie(None)):
    user = get_user_from_cookie(session)
    if not user:
        return JSONResponse({"ok": False, "error": "Not logged in"}, status_code=401)

    try:
        form_data = await request.form()
        kantor_code = form_data.get("kantor_code", "").strip()
        if not kantor_code:
            return JSONResponse({"ok": False, "error": "kantor_code required"}, status_code=400)

        conn = get_db(); cur = conn.cursor()

        # Cek apakah masih ada draft tersimpan
        cur.execute(
            "SELECT nomor_survei FROM origo.kantor_checklist_data WHERE kantor_code = %s AND workflow_status = 'draft'",
            (kantor_code,)
        )
        existing = cur.fetchone()
        if existing:
            # Ada draft - redirect ke form yang udah ada
            conn.close()
            return {"ok": True, "redirect": f"/survey/kantor-checklist/form/{kantor_code}", "nomor_survei": existing[0], "existing_draft": True}

        # Generate nomor baru
        from datetime import datetime
        tgl = datetime.now().strftime('%Y%m%d')
        # Hapus draft expired (created more than 24h ago) sebelum generate
        cur.execute(
            """DELETE FROM origo.kantor_checklist_data
               WHERE kantor_code = %s AND workflow_status = 'draft' AND created_at < NOW() - INTERVAL '24 hours'""",
            (kantor_code,)
        )
        cur.execute(
            """SELECT COALESCE(MAX(survey_seq), 0) + 1
               FROM origo.kantor_checklist_data
               WHERE kantor_code = %s AND created_at::date = CURRENT_DATE""",
            (kantor_code,)
        )
        next_seq = cur.fetchone()[0] or 1
        nomor_survei = f'SRV-{kantor_code}-{tgl}-{next_seq:03d}'

        blank_items = [{"status":"", "note":"", "foto":""} for _ in range(ITEM_COUNT)]
        cur.execute(
            """INSERT INTO origo.kantor_checklist_data
               (kantor_code, nomor_survei, survey_seq, pic, tgl_cek, status_data, workflow_status, yes_count, no_count, total_items, created_at)
               VALUES (%s, %s, %s, %s, CURRENT_DATE, %s, 'draft', 0, 0, 0, NOW())""",
            (kantor_code, nomor_survei, next_seq, user.get("user_id", ""), json.dumps(blank_items))
        )
        conn.commit()
        cur.close(); conn.close()

        return {"ok": True, "redirect": f"/survey/kantor-checklist/form/{kantor_code}", "nomor_survei": nomor_survei, "existing_draft": False}
    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/survey/api/kantor-checklist/auto-save")
async def api_auto_save(request: Request, session: Optional[str] = Cookie(None)):
    user = get_user_from_cookie(session)
    if not user:
        return JSONResponse({"ok": False, "error": "Not logged in"}, status_code=401)

    form_data = await request.form()
    kantor_code = form_data.get('kantor_code', '').strip()
    try: idx = int(form_data.get('idx', -1))
    except: idx = -1
    field = form_data.get('field', '')
    value = form_data.get('value', '')

    if not kantor_code or idx < 0 or not field:
        return JSONResponse({"ok": False, "error": "kantor_code, idx, field wajib"}, status_code=400)

    try:
        conn = get_db(); cur = conn.cursor()

        # Cek atau buat session
        cur.execute(
            "SELECT kantor_code, status_data FROM origo.kantor_checklist_data WHERE kantor_code = %s AND workflow_status = 'draft'",
            (kantor_code,)
        )
        row = cur.fetchone()

        if not row:
            # Buat session draft baru
            blank_items = [{"status":"", "note":"", "foto":""} for _ in range(ITEM_COUNT)]
            from datetime import datetime
            tgl = datetime.now().strftime('%Y%m%d')
            # Cari nomor urut berikutnya untuk kantor ini hari ini
            cur.execute(
                """SELECT COALESCE(MAX(survey_seq), 0) + 1
                   FROM origo.kantor_checklist_data
                   WHERE kantor_code = %s AND created_at::date = CURRENT_DATE""",
                (kantor_code,)
            )
            next_seq = cur.fetchone()[0] or 1
            nomor_survei = f'SRV-{kantor_code}-{tgl}-{next_seq:03d}'
            cur.execute(
                """INSERT INTO origo.kantor_checklist_data
                   (kantor_code, nomor_survei, survey_seq, pic, tgl_cek, status_data, workflow_status, yes_count, no_count, total_items, created_at)
                   VALUES (%s, %s, %s, %s, CURRENT_DATE, %s, 'draft', 0, 0, 0, NOW())
                   RETURNING kantor_code""",
                (kantor_code, nomor_survei, next_seq, user.get("user_id", ""), json.dumps(blank_items))
            )
            session_id = cur.fetchone()[0]
            status_data = blank_items
        else:
            session_id, sd = row
            status_data = sd if sd else [{"status":"", "note":"", "foto":""} for _ in range(ITEM_COUNT)]

        # Pastikan array cukup panjang
        while len(status_data) <= idx:
            status_data.append({"status":"", "note":"", "foto":""})

        # Update field
        if isinstance(status_data[idx], dict):
            status_data[idx][field] = value
        else:
            status_data[idx] = {field: value}

        # Hitung ulang
        yes_count = 0
        no_count = 0
        filled = 0
        for s in status_data:
            if not isinstance(s, dict): continue
            sv_str = s.get("status", "")
            if sv_str == "" or sv_str is None: continue
            filled += 1
            try:
                sv = int(sv_str)
                if sv == 0: yes_count += 1
                elif sv in (1,2,3,4): no_count += 1
            except:
                pass

        cur.execute(
            """UPDATE origo.kantor_checklist_data
               SET status_data = %s, yes_count = %s, no_count = %s, total_items = %s, updated_at = NOW()
               WHERE kantor_code = %s""",
            (json.dumps(status_data), yes_count, no_count, filled, session_id)
        )
        conn.commit()
        cur.close(); conn.close()

        return {"ok": True, "kantor_code": session_id, "yes": yes_count, "no": no_count, "filled": filled}
    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
@router.get("/survey/api/kantor-checklist/pdf/{kantor_code}")
async def pdf_survey(request: Request, kantor_code: str, dl: int = Query(0), session: Optional[str] = Cookie(None)):
    user = get_user_from_cookie(session)
    if not user:
        return HTMLResponse(status_code=302, headers={"Location": "/login"})
    try:
        conn = get_db(); cur = conn.cursor()
        from datetime import datetime as dtdt
        cur.execute(
            """SELECT kantor_code, pic, tgl_cek, status_data, yes_count, total_items,
                      nomor_survei, survey_seq, workflow_status, created_at, submitted_at, media_data
               FROM origo.kantor_checklist_data
               WHERE kantor_code = %s
               ORDER BY survey_seq DESC LIMIT 1""",
            (kantor_code,)
        )
        row = cur.fetchone()
        cur.close(); conn.close()
        if not row:
            return HTMLResponse("<h2>Data tidak ditemukan</h2>", status_code=404)

        kode, pic, tgl, sd, yes, tot, nomor, seq, wf, ca, sa, md = row
        items = sd if sd else []
        db_items = _get_items_from_db()

        tgl_str = str(tgl) if tgl else "-"
        wf_label = {"draft":"Draft","submitted":"Terkirim","final":"Final"}.get(wf, wf or "-")
        # Hitung weighted score
        db_items_all = _get_items_from_db()
        if md and isinstance(md, dict) and md.get("weighted_score") is not None:
            skor = round(float(md["weighted_score"]), 1)
        else:
            ws_pdf, _, _, _ = _hitung_weighted_score(items, db_items_all)
            skor = ws_pdf

        # ── Bangun data per kategori ──
        vlbl = {0:"✅ Baik", 1:"⚠️ Rusak", 2:"❌ Tidak", 3:"❌ Kurang", 4:"❌ Tidak"}
        from collections import defaultdict
        cat_data = defaultdict(lambda: {"items":[], "baik":0, "rusak":0, "total":0, "label":""})
        lampiran_foto = []

        for i, it in enumerate(items):
            if i >= len(db_items):
                continue
            di = db_items[i]
            st = it.get("status","") if isinstance(it, dict) else ""
            note = it.get("note","") if isinstance(it, dict) else ""
            foto_path = it.get("foto","") if isinstance(it, dict) else ""
            foto_desc = it.get("foto_desc","") if isinstance(it, dict) else ""
            foto_relevan = it.get("foto_relevan", True) if isinstance(it, dict) else True
            geo = it.get("geo","") if isinstance(it, dict) else ""
            try: sv = int(st)
            except: sv = -1
            label = vlbl.get(sv, st if st else "-")
            is_baik = (sv == 0)
            is_rusak = (sv > 0)

            cat_code = di['cat']
            cat_data[cat_code]["label"] = di['cat']
            cat_data[cat_code]["total"] += 1
            if is_baik: cat_data[cat_code]["baik"] += 1
            if is_rusak: cat_data[cat_code]["rusak"] += 1

            cat_data[cat_code]["items"].append({
                "num": len(cat_data[cat_code]["items"]) + 1,
                "label": di['label'],
                "status": label,
                "note": note,
                "foto_path": foto_path,
                "foto_desc": foto_desc,
                "foto_relevan": foto_relevan
            })

            # Lampiran foto full-size
            if foto_path and foto_path.startswith("/survey/uploads/"):
                fname = foto_path.replace("/survey/uploads/", "")
                fpath = os.path.join(PHOTO_DIR, fname)
                if os.path.exists(fpath):
                    try:
                        with open(fpath, "rb") as fimg:
                            b64 = b64encode(fimg.read()).decode()
                        lampiran_foto.append({
                            "cat": di['cat'],
                            "item": di['label'],
                            "b64": b64,
                            "desc": foto_desc,
                            "relevan": foto_relevan,
                            "geo": geo
                        })
                    except:
                        pass

        skor_color = "#16a34a" if skor >= 70 else "#d97706" if skor >= 40 else "#dc2626"

        # ── Build CSS ──
        css = f"""@page {{ size:A4; margin:14mm 10mm; }}
  body {{ font-family:'DejaVu Sans',sans-serif; font-size:9pt; color:#111; }}
  h1 {{ font-size:14pt; text-align:center; margin:0 0 4px 0; }}
  h2 {{ font-size:10pt; text-align:center; margin:0 0 8px 0; color:#666; }}
  h3 {{ font-size:10pt; margin:12px 0 6px 0; border-bottom:1px solid #ccc; padding-bottom:3px; }}
  table {{ width:100%%; border-collapse:collapse; margin:6px 0; }}
  th, td {{ border:1px solid #555; padding:3px 5px; text-align:left; font-size:7.5pt; }}
  th {{ background:#e5e7eb; font-weight:bold; text-align:center; font-size:7pt; }}
  .meta {{ margin:4px 0; font-size:8pt; line-height:1.6; }}
  .meta span {{ margin-right:14px; }}
  .skor-main {{ text-align:center; padding:14px 0; }}
  .skor-circle {{ display:inline-block; width:70px; height:70px; line-height:70px; border-radius:50%%; font-size:20pt; font-weight:bold; color:white; text-align:center; background:{skor_color}; }}
  .footer {{ margin-top:10px; font-size:6.5pt; color:#999; text-align:center; }}
  .page-break {{ page-break-before:always; }}
  .lamp-grid {{ display:flex; flex-wrap:wrap; gap:6px; }}
  .lamp-item {{ width:175px; border:1px solid #ddd; border-radius:5px; padding:6px; margin:3px; display:inline-block; vertical-align:top; }}
  .lamp-item img {{ width:100%%; height:130px; object-fit:cover; border-radius:3px; }}
  .lamp-item .lamp-label {{ font-size:7pt; color:#333; }}
  .lamp-item .lamp-desc {{ font-size:6.5pt; color:#666; }}
  .lamp-item .lamp-geo {{ font-size:6pt; color:#888; }}"""

        html_head = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Hasil Survei {kode}</title>
<style>{css}</style></head><body>"""

        # ════════════  HALAMAN 1: SUMMARY  ════════════
        pages = [html_head]

        cat_rows_summary = []
        for ck in sorted(cat_data.keys()):
            cd = cat_data[ck]
            cpct = round(cd["baik"] / cd["total"] * 100, 1) if cd["total"] > 0 else 0
            ccol = "#16a34a" if cpct >= 70 else "#d97706" if cpct >= 40 else "#dc2626"
            cat_rows_summary.append(
                f"<tr><td>{cd['label']}</td><td style='text-align:center'>{cd['total']}</td>"
                f"<td style='text-align:center;color:#16a34a'>{cd['baik']}/{cd['total']}</td>"
                f"<td style='text-align:center;color:#dc2626'>{cd['rusak']}/{cd['total']}</td>"
                f"<td style='text-align:center'><span style='display:inline-block;padding:1px 6px;border-radius:3px;font-weight:bold;color:white;background:{ccol};font-size:8pt;'>{cpct}%%</span></td></tr>"
            )

        summary = f"""
<h1>Laporan Hasil Survei Ceklist Kantor</h1>
<h2>{nomor or "Belum dinomori"}</h2>

<div class="skor-main">
  <div class="skor-circle">{skor}%</div>
</div>

<div class="meta">
  <span><strong>Kantor:</strong> {kode}</span>
  <span><strong>PIC:</strong> {pic or "-"}</span>
  <span><strong>Tgl Cek:</strong> {tgl_str}</span><br>
  <span><strong>Status:</strong> {wf_label}</span>
  <span><strong>Terisi:</strong> {yes}/{tot} item</span>
</div>

<h3>📊 Skor per Kategori</h3>
<table>
<thead><tr><th>Kategori</th><th style='width:40px'>Total</th><th style='width:50px'>Baik</th><th style='width:50px'>Rusak</th><th style='width:45px'>Skor</th></tr></thead>
<tbody>
{"".join(cat_rows_summary)}
</tbody>
</table>
"""
        pages.append(summary)

        # Best / Worst
        baik_items = [(i,it) for i,it in enumerate(items) if i < len(db_items) and isinstance(it,dict) and str(it.get("status","")).isdigit() and int(it.get("status","99")) == 0]
        rusak_items = [(i,it) for i,it in enumerate(items) if i < len(db_items) and isinstance(it,dict) and str(it.get("status","")).isdigit() and int(it.get("status","99")) > 0]

        pages.append("<h3>🏆 Top 5 Terbaik</h3><table><thead><tr><th style='width:22px'>#</th><th>Item</th><th style='width:35px'>Status</th></tr></thead><tbody>")
        for ii, it in baik_items[:5]:
            di = db_items[ii]
            st = int(it.get("status","0"))
            pages.append(f"<tr><td style='text-align:center'>{ii+1}</td><td>{di['cat']} - {di['label']}</td><td style='text-align:center'>{vlbl.get(st,'-')}</td></tr>")
        if not baik_items:
            pages.append("<tr><td colspan='3' style='text-align:center;color:#999'>Tidak ada item baik</td></tr>")
        pages.append("</tbody></table>")

        # ════════════  BEST / WORST 5  ════════════
        baik_items = [(i,it) for i,it in enumerate(items) if i < len(db_items) and isinstance(it,dict) and str(it.get("status","")).isdigit() and int(it.get("status",99)) == 0]
        rusak_items = [(i,it) for i,it in enumerate(items) if i < len(db_items) and isinstance(it,dict) and str(it.get("status","")).isdigit() and int(it.get("status",99)) > 0]

        pages.append("<h3>🏆 Top 5 Terbaik</h3><table><thead><tr><th style='width:22px'>#</th><th>Item</th><th style='width:35px'>Status</th></tr></thead><tbody>")
        for ii, it in baik_items[:5]:
            di = db_items[ii]
            st = int(it.get("status","0"))
            pages.append(f"<tr><td style='text-align:center'>{ii+1}</td><td>{di['cat']} - {di['label']}</td><td style='text-align:center'>{vlbl.get(st,'-')}</td></tr>")
        if not baik_items:
            pages.append("<tr><td colspan='3' style='text-align:center;color:#999'>Tidak ada item baik</td></tr>")
        pages.append("</tbody></table>")

        pages.append("<h3>🔻 Top 5 Terburuk</h3><table><thead><tr><th style='width:22px'>#</th><th>Item</th><th style='width:35px'>Status</th></tr></thead><tbody>")
        for ii, it in rusak_items[:5]:
            di = db_items[ii]
            st = int(it.get("status","0"))
            pages.append(f"<tr><td style='text-align:center'>{ii+1}</td><td>{di['cat']} - {di['label']}</td><td style='text-align:center'>{vlbl.get(st,'-')}</td></tr>")
        if not rusak_items:
            pages.append("<tr><td colspan='3' style='text-align:center;color:#999'>Semua item baik</td></tr>")
        pages.append("</tbody></table>")

        # ════════════  WARNING DOKUMENTASI  ════════════
        foto_warnings = []
        for i, it in enumerate(items):
            if i >= len(db_items): continue
            di = db_items[i]
            fpath = it.get("foto","") if isinstance(it, dict) else ""
            frelevan = it.get("foto_relevan", True) if isinstance(it, dict) else True
            fdesc = it.get("foto_desc", "") if isinstance(it, dict) else ""
            if fpath and frelevan == False:
                foto_warnings.append({
                    "cat": di['cat'],
                    "label": di['label'],
                    "desc": fdesc[:60] if fdesc else "Foto tidak sesuai"
                })

        if foto_warnings:
            pages.append("""
<h3>⚠️ Peringatan Dokumentasi</h3>
<p style='font-size:7.5pt;color:#dc2626;margin:0 0 6px 0;'>
  Foto-foto berikut terindikasi tidak sesuai dengan konteks pernyataan.
  Disarankan untuk melakukan dokumentasi ulang.
</p>
<table>
<thead><tr><th style='width:22px'>#</th><th>Item</th><th style='width:120px'>Catatan AI</th></tr></thead>
<tbody>""")
            for idx, fw in enumerate(foto_warnings):
                pages.append(f"<tr style='background:#fef2f2'><td style='text-align:center'>{idx+1}</td><td>{fw['cat']} - {fw['label']}</td><td style='color:#dc2626;font-size:7pt'>{fw['desc']}</td></tr>")
            pages.append("</tbody></table>")
        elif any(it.get("foto","") if isinstance(it,dict) else "" for it in items):
            pages.append("<h3>⚠️ Peringatan Dokumentasi</h3><p style='color:#16a34a;font-size:7.5pt;'>✅ Semua dokumentasi foto sesuai dengan konteks pernyataan.</p>")

        # ════════════  HALAMAN 2: DETAIL PER KATEGORI  ════════════
        pages.append("<div class='page-break'></div>")
        pages.append("<h1 style='font-size:13pt'>Detail Pemeriksaan per Kategori</h1>")

        for ck in sorted(cat_data.keys()):
            cd = cat_data[ck]
            cpct = round(cd["baik"] / cd["total"] * 100, 1) if cd["total"] > 0 else 0
            pages.append(f"<h3>{cd['label']} - {cpct}%</h3>")
            pages.append("<table><thead><tr><th style='width:18px'>#</th><th>Pernyataan</th><th style='width:45px'>Status</th><th style='width:48px'>Foto</th><th style='width:80px'>Deskripsi</th><th style='width:45px'>Catatan</th></tr></thead><tbody>")
            for ci in cd["items"]:
                img_td = "<td style='text-align:center'>-</td>"
                if ci["foto_path"] and ci["foto_path"].startswith("/survey/uploads/"):
                    fname = ci["foto_path"].replace("/survey/uploads/", "")
                    fpath = os.path.join(PHOTO_DIR, fname)
                    if os.path.exists(fpath):
                        try:
                            with open(fpath, "rb") as fimg:
                                b64i = b64encode(fimg.read()).decode()
                            img_td = f"<td style='text-align:center'><img src='data:image/jpeg;base64,{b64i}' style='width:42px;height:42px;object-fit:cover;border-radius:3px;'></td>"
                        except: pass
                rel_tag = ""
                if ci["foto_desc"]:
                    if ci["foto_relevan"] == False:
                        rel_tag = "<br><span style='color:#dc2626;font-size:6pt;'>⚠️ Foto mungkin tdk sesuai</span>"
                    else:
                        rel_tag = "<br><span style='color:#16a34a;font-size:6pt;'>✅ Foto sesuai</span>"
                # Baris merah untuk foto tidak sesuai
                row_style = " style='background:#fef2f2;'" if ci.get("foto_desc") and ci["foto_relevan"] == False else ""
                desc_td = f"<td style='font-size:6.5pt;color:#555'>{ci['foto_desc'][:60] if ci['foto_desc'] else '-'}{rel_tag}</td>"
                pages.append(
                    f"<tr{row_style}><td style='text-align:center'>{ci['num']}</td><td>{ci['label'][:45]}</td>"
                    f"<td style='text-align:center;font-size:7pt'>{ci['status']}</td>"
                    f"{img_td}{desc_td}<td style='font-size:6.5pt;color:#888'>{ci['note'][:30] if ci['note'] else '-'}</td></tr>"
                )
            pages.append("</tbody></table>")

        # ════════════  HALAMAN 3: LAMPIRAN FOTO  ════════════
        if lampiran_foto:
            pages.append("<div class='page-break'></div>")
            pages.append("<h1>Lampiran Foto</h1>")
            pages.append("<div class='lamp-grid'>")
            for lf in lampiran_foto:
                geo_str = f"<div class='lamp-geo'>{lf['geo']}</div>" if lf["geo"] else ""
                rel_str = "<br><span style='color:#dc2626;font-size:6.5pt;'>⚠️ Foto mungkin tdk sesuai</span>" if lf["relevan"] == False else "<br><span style='color:#16a34a;font-size:6.5pt;'>✅ Foto sesuai</span>"
                desc_str = f"<div class='lamp-desc'>{lf['desc'][:80]}{'...' if len(lf['desc'])>80 else ''}</div>" if lf["desc"] else ""
                pages.append(f"""
<div class='lamp-item'>
  <img src='data:image/jpeg;base64,{lf['b64']}'>
  <div class='lamp-label'><strong>{lf['cat']}</strong> - {lf['item']}</div>
  {desc_str}
  {rel_str}
  {geo_str}
</div>""")
            pages.append("</div>")

        pages.append(f"<div class='footer'>Dicetak: {dtdt.now().strftime('%d-%m-%Y %H:%M')} WIB | Origo Survey System</div>")
        pages.append("</body></html>")
        html = "\n".join(pages)

        if dl:
            PDF_DIR = "/home/bhc0104/survey_app/pdfs"
            os.makedirs(PDF_DIR, exist_ok=True)
            pdf_fname = f"survei_{kode}_{nomor or 'unknown'}.pdf".replace("/","_").replace(" ","_")
            pdf_fpath = os.path.join(PDF_DIR, pdf_fname)

            from weasyprint import HTML as WPHTML
            try:
                WPHTML(string=html).write_pdf(pdf_fpath)
            except Exception as wp_e:
                import traceback
                traceback.print_exc()
                # Simpan HTML ke file untuk debug
                with open(os.path.join(PDF_DIR, f"debug_{kode}.html"), "w", encoding="utf-8") as fdbg:
                    fdbg.write(html)
                return HTMLResponse(f"<h2>PDF Error: {wp_e}</h2><pre>{traceback.format_exc()}</pre>", status_code=500)

            # Simpan path di media_data
            try:
                conn2 = get_db(); cur2 = conn2.cursor()
                md_new = {"pdf_path": f"/survey/pdfs/{pdf_fname}"}
                cur2.execute("UPDATE origo.kantor_checklist_data SET media_data = %s WHERE kantor_code = %s AND survey_seq = %s",
                             (json.dumps(md_new), kode, seq))
                conn2.commit()
                cur2.close(); conn2.close()
            except: pass

            from fastapi.responses import FileResponse
            return FileResponse(pdf_fpath, media_type="application/pdf",
                filename=pdf_fname,
                headers={"Content-Disposition": "inline"})

        return HTMLResponse(html)
    except Exception as e:
        import traceback; traceback.print_exc()
        return HTMLResponse(f"<h2>Error: {e}</h2>", status_code=500)
# ── Upload foto ──
import os
PHOTO_DIR = "/home/bhc0104/survey_app/uploads"
os.makedirs(PHOTO_DIR, exist_ok=True)

@router.post("/survey/api/kantor-checklist/upload-foto")
async def api_upload_foto(request: Request, session: Optional[str] = Cookie(None)):
    user = get_user_from_cookie(session)
    if not user:
        return JSONResponse({"ok": False, "error": "Not logged in"}, status_code=401)

    form = await request.form()
    kantor_code = form.get("kantor_code", "").strip()
    try:
        idx = int(form.get("idx", -1))
    except:
        idx = -1

    if not kantor_code or idx < 0:
        return JSONResponse({"ok": False, "error": "kantor_code & idx required"}, status_code=400)

    file = form.get("file")
    if not file:
        return JSONResponse({"ok": False, "error": "No file uploaded"}, status_code=400)

    try:
        from datetime import datetime
        from PIL import Image, ImageDraw, ImageFont
        import io
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("Asia/Jakarta")
        now = datetime.now(tz)
        ts = now.strftime("%Y%m%d_%H%M%S")
        ext = os.path.splitext(file.filename or ".jpg")[1] or ".jpg"
        safe_kode = kantor_code.replace("/", "_").replace("\\", "_")
        filename = f"{safe_kode}_{idx:02d}_{ts}{ext}"
        filepath = os.path.join(PHOTO_DIR, filename)

        # Baca file dan proses
        contents = await file.read()

        # Deteksi video dari form flag atau ekstensi
        is_video_from_form = form.get("is_video", "0")
        video_extensions = {".webm", ".mp4", ".mov", ".avi", ".mkv"}
        is_video = is_video_from_form in ("1", "true") or ext.lower() in video_extensions

        if is_video:
            # Video: simpan mentah dulu, lalu kompres via FFmpeg
            temp_path = filepath + ".raw"
            with open(temp_path, "wb") as f:
                f.write(contents)
            # Kompres ke MP4 H.264 + audio, max width 640, crf 28
            mp4_filename = f"{safe_kode}_{idx:02d}_{ts}.mp4"
            mp4_path = os.path.join(PHOTO_DIR, mp4_filename)
            try:
                import subprocess
                subprocess.run([
                    "nice", "-n", "19", "ffmpeg", "-i", temp_path,
                    "-vf", "scale=min(640\\,iw):-2",
                    "-c:v", "libx264", "-crf", "28", "-preset", "fast",
                    "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart",
                    "-y", mp4_path
                ], capture_output=True, timeout=60)
                # Hapus file mentah
                if os.path.exists(mp4_path) and os.path.getsize(mp4_path) > 0:
                    os.remove(temp_path)
                    filepath = mp4_path
                    filename = mp4_filename
                    ext = ".mp4"
                    relative_path = mp4_filename
                    video_url = f"/survey/uploads/{mp4_filename}"
            except Exception:
                # Fallback: pake file mentah kalo ffmpeg gagal
                os.rename(temp_path, filepath)
            # Simpan path ke DB sebagai video_path
            relative_path = f"{safe_kode}_{idx:02d}_{ts}{ext}"
            video_url = f"/survey/uploads/{relative_path}"
            try:
                conn2 = get_db()
                cur2 = conn2.cursor()
                cur2.execute(
                    "SELECT status_data FROM origo.kantor_checklist_data WHERE kantor_code = %s AND workflow_status = 'draft'",
                    (kantor_code,)
                )
                r2 = cur2.fetchone()
                if r2:
                    sd = r2[0] if r2[0] else [{"status":"", "note":"", "foto":""} for _ in range(ITEM_COUNT)]
                    while len(sd) <= idx:
                        sd.append({"status":"", "note":"", "foto":""})
                    if isinstance(sd[idx], dict):
                        sd[idx]["video_path"] = video_url
                        if geo_str:
                            sd[idx]["geo"] = geo_str
                        cur2.execute(
                            "UPDATE origo.kantor_checklist_data SET status_data = %s, updated_at = NOW() WHERE kantor_code = %s AND workflow_status = 'draft'",
                            (json.dumps(sd), kantor_code)
                        )
                        conn2.commit()
                cur2.close()
                conn2.close()
            except Exception:
                pass
            return JSONResponse({"ok": True, "foto_path": "", "video_path": video_url, "analisa": {"deskripsi": "[Dokumentasi video]", "relevan": True, "saran": "", "cost_idr": 0}})

        img = Image.open(io.BytesIO(contents))

        # ── Optimasi ukuran: resize max 1600px di sisi terpanjang ──
        max_dim = 1600
        if img.width > max_dim or img.height > max_dim:
            ratio = max_dim / max(img.width, img.height)
            new_w = int(img.width * ratio)
            new_h = int(img.height * ratio)
            img = img.resize((new_w, new_h), Image.LANCZOS)

        # ── Gemini: analisa foto ──
        # SKIP Gemini untuk video - simpan saja
        is_video_flag = form.get("is_video", "0")
        if is_video_flag in ("1", "true"):
            # Video: simpan tanpa analisa Gemini
            foto_desc = "[Dokumentasi video]"
            cost_idr = 0
            relevan = True
            saran = ""
        else:
            # Hanya analisa foto (bukan video)
            # Ambil item label & cat untuk konteks
            item_label = ""
            item_cat = ""
            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                """SELECT i.label, c.cat_code
                   FROM origo.survey_checklist_items i
                   JOIN origo.survey_categories c ON i.cat_id = c.id
                   WHERE i.item_idx = %s AND i.is_active = true""",
                (idx,)
            )
            row = cur.fetchone()
            if row:
                item_label = row[0] or ""
                item_cat = row[1] or ""
            cur.close()
            conn.close()

            # Simpan bytes sebelum resize untuk Gemini (pake versi original)
            # Tapi kita pake version yg udah diresize - cukup
            img_bytes_for_ai = io.BytesIO()
            img.save(img_bytes_for_ai, "JPEG", quality=85)
            img_bytes_for_ai = img_bytes_for_ai.getvalue()

            analisa = analisa_foto_gemini(img_bytes_for_ai, item_label, item_cat,
                                          kantor_code=kantor_code, item_idx=idx)
            foto_desc = analisa.get("deskripsi", "")
            cost_idr = analisa.get("cost_idr", 0)
            relevan = analisa.get("relevan", True)
            saran = analisa.get("saran", "")

        # ── Hardstamp: user, kode pernyataan, timestamp, geo, nama kantor ──
        draw = ImageDraw.Draw(img, "RGBA")
        user_name = user.get("fullname", "")

        # Ambil nama kantor
        kantor_label_foto = kantor_code
        try:
            conn_lbl = get_db(); cur_lbl = conn_lbl.cursor()
            cur_lbl.execute("SELECT display_name FROM origo.network_tree_node WHERE office_code=%s LIMIT 1", (kantor_code,))
            rl = cur_lbl.fetchone()
            if rl: kantor_label_foto = rl[0]
            cur_lbl.close(); conn_lbl.close()
        except: pass

        geo_str = form.get("geo", "")
        if geo_str:
            stamp_text = f"{now.strftime('%d %b %Y %H:%M')} WIB\n{kantor_code} - {kantor_label_foto[:30]}\n{item_cat}.{idx} | {user_name}\n{geo_str}"
        else:
            stamp_text = f"{now.strftime('%d %b %Y %H:%M')} WIB\n{kantor_code} - {kantor_label_foto[:30]}\n{item_cat}.{idx} | {user_name}"

        # Cari font - fallback ke default
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12)
        except Exception:
            font = ImageFont.load_default()

        # Background semi-transparan di pojok kiri bawah
        bbox = draw.textbbox((0, 0), stamp_text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        pad = 4
        bx, by = 6, img.height - th - pad * 2 - 6
        draw.rectangle(
            [bx, by, bx + tw + pad * 2, by + th + pad * 2],
            fill=(0, 0, 0, 140)
        )
        draw.text((bx + pad, by + pad), stamp_text, font=font, fill=(255, 255, 255, 230))

        # ── Simpan hasil ──
        if is_video_flag in ("1", "true"):
            # Video: simpan langsung tanpa hardstamp
            import shutil
            with open(filepath, "wb") as f:
                f.write(contents)
        else:
            img.save(filepath, "JPEG", quality=85, optimize=True)

        filesize = os.path.getsize(filepath)

        if is_video_flag in ("1", "true"):
            video_path = f"/survey/uploads/{filename}"
            foto_path = ""
        else:
            foto_path = f"/survey/uploads/{filename}"
            video_path = ""

        # ── Simpan deskripsi foto/video ke session data ──
        try:
            conn2 = get_db()
            cur2 = conn2.cursor()
            cur2.execute(
                "SELECT status_data FROM origo.kantor_checklist_data WHERE kantor_code = %s AND workflow_status = 'draft'",
                (kantor_code,)
            )
            r2 = cur2.fetchone()
            if r2:
                sd = r2[0] if r2[0] else [{"status":"", "note":"", "foto":""} for _ in range(ITEM_COUNT)]
                while len(sd) <= idx:
                    sd.append({"status":"", "note":"", "foto":""})
                if isinstance(sd[idx], dict):
                    if is_video_flag in ("1", "true"):
                        # Video: simpan video_path, jangan foto_desc
                        sd[idx]["video_path"] = video_path
                    else:
                        sd[idx]["foto"] = foto_path
                        sd[idx]["foto_desc"] = foto_desc
                        sd[idx]["foto_relevan"] = relevan
                        sd[idx]["foto_saran"] = saran
                        # Simpan geo juga di DB untuk analisa
                        if geo_str:
                            sd[idx]["geo"] = geo_str
                    cur2.execute(
                        "UPDATE origo.kantor_checklist_data SET status_data = %s, updated_at = NOW() WHERE kantor_code = %s AND workflow_status = 'draft'",
                        (json.dumps(sd), kantor_code)
                    )
                    conn2.commit()
            cur2.close()
            conn2.close()
        except Exception:
            pass  # Gagal simpan deskripsi - bukan fatal

        res = {
            "ok": True,
            "foto_path": foto_path or "",
            "filename": filename,
            "filesize": filesize,
            "foto_desc": foto_desc if not is_video_flag in ("1", "true") else "",
            "foto_relevan": relevan,
            "foto_saran": saran
        }
        if is_video_flag in ("1", "true"):
            res["video_path"] = video_path
        return res
    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# ── Hapus foto ──
@router.post("/survey/api/kantor-checklist/hapus-foto")
async def api_hapus_foto(request: Request, session: Optional[str] = Cookie(None)):
    user = get_user_from_cookie(session)
    if not user:
        return JSONResponse({"ok": False, "error": "Not logged in"}, status_code=401)

    form = await request.form()
    foto_path = form.get("foto_path", "").strip()

    if not foto_path:
        return JSONResponse({"ok": False, "error": "foto_path required"}, status_code=400)

    try:
        # Hanya hapus file di sistem - path di DB bakal ditimpa pas auto-save atau submit
        relative = foto_path.replace("/survey/uploads/", "")
        full = os.path.join(PHOTO_DIR, relative)
        if os.path.exists(full):
            os.remove(full)
            return {"ok": True, "deleted": foto_path}
        else:
            return {"ok": True, "deleted": foto_path, "note": "file already gone"}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# ── Serve uploads via endpoint (karena mount di sub-router gak bisa) ──
@router.get("/survey/uploads/{filename:path}")
async def serve_upload(filename: str):
    from fastapi.responses import FileResponse
    import os
    safe_path = os.path.normpath(os.path.join(PHOTO_DIR, filename))
    if not safe_path.startswith(PHOTO_DIR):
        return HTMLResponse("Forbidden", status_code=403)
    if not os.path.exists(safe_path):
        return HTMLResponse("Not Found", status_code=404)
    return FileResponse(safe_path)

@router.get("/survey/reports/{filename:path}")
async def serve_report(filename: str):
    from fastapi.responses import FileResponse
    import os
    REPORT_DIR = os.path.join(os.path.dirname(__file__), "static", "reports")
    safe_path = os.path.normpath(os.path.join(REPORT_DIR, filename))
    if not safe_path.startswith(REPORT_DIR):
        return HTMLResponse("Forbidden", status_code=403)
    if not os.path.exists(safe_path):
        return HTMLResponse("Not Found", status_code=404)
    return FileResponse(safe_path, headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"})

@router.get("/survey/api/refresh-reports")
async def api_refresh_reports(request: Request, session: Optional[str] = Cookie(None)):
    """Regenerate 3 status report images (submitted, ongoing, belum dibuat)."""
    user = get_user_from_cookie(session)
    if not user:
        return JSONResponse({"ok": False, "error": "Not logged in"}, status_code=401)

    try:
        conn = get_db()
        cur = conn.cursor()
        # Ambil semua branch dari tree + LEFT JOIN checklist utk tau status
        # Ini penting: report harus mencakup SEMUA branch dari tree, bukan cuma yg ada di checklist
        cur.execute("""
            SELECT kcd.kantor_code,
                   COALESCE(nbm.office_name, kcd.kantor_code) AS office_name,
                   COALESCE(n.branch_kind, 'cbg_kecil') AS branch_kind,
                   kcd.yes_count, kcd.total_items, kcd.pic,
                   kcd.workflow_status, kcd.submitted_at, kcd.updated_at,
                   kcd.weighted_score, kcd.status_data, kcd.nomor_survei,
                   COALESCE(fu."NAME_FULL", fe.name_full, kcd.pic) AS pic_name,
                   kcd.created_at
            FROM origo.kantor_checklist_data kcd
            LEFT JOIN (
                SELECT office_code, display_name, branch_kind FROM origo.network_tree_node
                WHERE version_id = (SELECT id FROM origo.network_tree_version WHERE is_published = TRUE LIMIT 1)
            ) n ON kcd.kantor_code = n.office_code
            LEFT JOIN origo.network_branch_monitoring_master nbm ON kcd.kantor_code = nbm.office_code AND nbm.branch_type IN ('cbg_besar','cbg_kecil','pos','kios')
            LEFT JOIN "i_fast"."FS_SEC_USERS" fu ON kcd.pic = fu."USER_ID"
            LEFT JOIN f_fifapps.fs_sec_users fe ON kcd.pic = fe.user_id
            WHERE kcd.yes_count IS NOT NULL AND kcd.total_items > 0
            ORDER BY kcd.submitted_at ASC NULLS LAST, kcd.kantor_code
        """)
        survey_rows = cur.fetchall()

        # Ambil network tree path (utk grouping area/wilayah)
        cur.execute("""
            WITH RECURSIVE tree AS (
                SELECT id, parent_id, node_code, display_name, branch_kind, office_code,
                       1 AS depth, CAST(node_code AS text) AS path_code, CAST(display_name AS text) AS path_name
                FROM origo.network_tree_node
                WHERE version_id = (SELECT id FROM origo.network_tree_version WHERE is_published = TRUE LIMIT 1)
                  AND parent_id IS NULL
                UNION ALL
                SELECT n.id, n.parent_id, n.node_code, n.display_name, n.branch_kind, n.office_code,
                       t.depth + 1,
                       t.path_code || '>' || n.node_code,
                       t.path_name || ' > ' || n.display_name
                FROM origo.network_tree_node n
                JOIN tree t ON n.parent_id = t.id
                WHERE n.version_id = (SELECT id FROM origo.network_tree_version WHERE is_published = TRUE LIMIT 1)
            )
            SELECT office_code, display_name, branch_kind, path_code, path_name
            FROM tree
            WHERE branch_kind NOT IN ('area','wilayah') AND office_code IS NOT NULL
        """)
        branch_info = {}
        for r in cur.fetchall():
            branch_info[r[0]] = {"display_name": r[1], "branch_kind": r[2], "path_code": r[3], "path_name": r[4]}

        cur.close(); conn.close()

        from PIL import Image, ImageDraw, ImageFont

        tz = __import__('zoneinfo').ZoneInfo("Asia/Jakarta")
        now = __import__('datetime').datetime.now(tz)
        ts_str = now.strftime("%d-%m-%Y %H:%M WIB")

        try:
            font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
            font_reg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
            font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 9)
        except:
            font_bold = font_reg = font_sm = ImageFont.load_default()

        REPORT_DIR = os.path.join(os.path.dirname(__file__), "static", "reports")
        os.makedirs(REPORT_DIR, exist_ok=True)

        # Helper
        def _bk_label(bk):
            return {"cbg_besar": "cbg", "cbg_kecil": "cbg", "pos": "POS", "kios": "KIO"}.get(bk, "")
        def _bk_color(bk):
            return {"cbg_besar": "#3b82f6", "cbg_kecil": "#3b82f6", "pos": "#f59e0b", "kios": "#8b5cf6"}.get(bk, "#6b7280")

        # Kolom index query baru:
        # r[0]=office_code, r[1]=office_name, r[2]=branch_kind
        # r[3]=yes_count, r[4]=total_items, r[5]=pic, r[6]=workflow_status
        # r[7]=submitted_at, r[8]=updated_at, r[9]=weighted_score
        # r[10]=status_data, r[11]=nomor_survei, r[12]=pic_name

        belum_list = []
        ongoing_list = []
        submitted_list = []
        for r in survey_rows:
            ws = str(r[6] or "")
            yc = r[3] or 0
            if ws in ("submitted", "final"):
                submitted_list.append(r)
            elif ws == "draft" and (yc or 0) > 0:
                ongoing_list.append(r)
            else:
                belum_list.append(r)

        # ─── REPORT: BELUM DIBUAT - query langsung dari tree ───
        def _build_belum():
            """Report BELUM DIBUAT - ambil branch dari tree yg belum ada di checklist."""
            conn2 = get_db()
            cur2 = conn2.cursor()
            cur2.execute("""
                SELECT nbm.office_code, nbm.office_name, nbm.branch_type
                FROM origo.network_branch_monitoring_master nbm
                WHERE nbm.branch_type IN ('cbg_besar','cbg_kecil','pos','kios')
                  AND nbm.office_code ~ '^[1-9][0-9]{4}$'
                  AND nbm.office_code IN (
                      SELECT n.office_code FROM origo.network_tree_node n
                      JOIN origo.network_tree_version v ON n.version_id = v.id
                      WHERE v.is_published = true AND n.office_code IS NOT NULL
                        AND n.display_name IS NOT NULL
                        AND n.branch_kind IN ('cbg_besar','cbg_kecil','pos','kios')
                  )
                  AND nbm.office_code NOT IN (
                      SELECT kantor_code FROM origo.kantor_checklist_data
                      WHERE yes_count IS NOT NULL AND total_items > 0
                  )
                ORDER BY nbm.office_code
            """)
            belum_rows = cur2.fetchall()
            cur2.close(); conn2.close()

            if not belum_rows:
                return None
            # Group by area > wilayah
            groups = {}
            for r in belum_rows:
                kc = r[0]
                bi = branch_info.get(kc)
                if not bi:
                    continue
                path_codes = bi["path_code"].split(">")
                path_names = bi["path_name"].split(" > ")
                a_code = path_codes[1] if len(path_codes) >= 2 else "??"
                a_name = path_names[1] if len(path_names) >= 2 else a_code
                w_code = path_codes[2] if len(path_codes) >= 3 else a_code
                w_name = path_names[2] if len(path_names) >= 3 else w_code
                if a_code not in groups:
                    groups[a_code] = {"area_name": a_name, "wilayah": {}}
                if w_code not in groups[a_code]["wilayah"]:
                    groups[a_code]["wilayah"][w_code] = {"wilayah_name": w_name, "branches": []}
                groups[a_code]["wilayah"][w_code]["branches"].append(r)

            orphans = [r for r in belum_rows if r[0] not in branch_info]

            section_h = 28
            badge_h = 22
            pad = 14
            total_w = 880
            y_est = 56
            for a_code, a_data in groups.items():
                y_est += section_h
                for w_code, w_data in a_data["wilayah"].items():
                    y_est += 24
                    y_est += len(w_data["branches"]) * badge_h
            y_est += len(orphans) * badge_h + 40
            y_est = max(300, min(6000, y_est))

            BG = (15, 15, 25)
            ROW_A = (20, 23, 20)
            ROW_B = (25, 28, 25)
            HDR_BG = (42, 51, 75)
            TXT_TITLE = (255, 255, 255)
            TXT_MAIN = (217, 217, 237)
            TXT_DIM = (149, 150, 165)
            BADGE_CBG = (76, 116, 168)
            BADGE_KIO = (169, 123, 76)
            BADGE_POS = (178, 143, 94)

            img = Image.new("RGB", (total_w, y_est), BG)
            draw = ImageDraw.Draw(img)

            draw.text((pad, 8), f"Belum Dibuat ({len(belum_rows)})", font=font_bold, fill=TXT_TITLE)
            draw.text((pad, 24), f"- {ts_str}", font=font_sm, fill=TXT_DIM)

            y = 46
            i_main = pad
            i_child = pad + 20

            for a_code, a_data in sorted(groups.items()):
                draw.rectangle([i_main, y, total_w - pad, y + section_h], fill=HDR_BG)
                draw.text((i_main + 8, y + 6), f"{a_code} {a_data['area_name']}", font=font_reg, fill=TXT_DIM)
                y += section_h
                for w_code, w_data in sorted(a_data["wilayah"].items()):
                    draw.text((i_child, y + 5), f"{w_data['wilayah_name']} ({len(w_data['branches'])})", font=font_reg, fill=TXT_MAIN)
                    y += 24
                    for ri, bn in enumerate(w_data["branches"]):
                        kc = bn[0]
                        bi2 = branch_info.get(kc, {})
                        bname = (bi2.get("display_name") or kc) if bi2 else kc
                        bk = bi2.get("branch_kind") if bi2 else ""
                        bg_row = ROW_A if ri % 2 == 0 else ROW_B
                        draw.rectangle([i_child + 20, y, total_w - pad, y + badge_h], fill=bg_row)
                        bl = {"cbg_besar": "cbg", "cbg_kecil": "cbg", "pos": "pos", "kios": "kio"}.get(bk, "")
                        bc = BADGE_CBG if bk in ("cbg_besar","cbg_kecil") else BADGE_KIO if bk == "kios" else BADGE_POS if bk == "pos" else None
                        if bl and bc:
                            draw.rectangle([i_child + 24, y + 1, i_child + 52, y + badge_h - 2], fill=bc)
                            draw.text((i_child + 26, y + 2), bl, font=font_sm, fill=(255, 255, 255))
                        draw.text((i_child + 56, y + 2), kc, font=font_sm, fill=TXT_DIM)
                        clean_name = bname[7:] if len(bname) > 7 and bname[:5] == kc else (bname or "")[:30]
                        draw.text((i_child + 114, y + 2), clean_name, font=font_sm, fill=TXT_MAIN)
                        y += badge_h

            for ri, r in enumerate(orphans):
                bg_row = ROW_A if ri % 2 == 0 else ROW_B
                draw.rectangle([i_child + 20, y, total_w - pad, y + badge_h], fill=bg_row)
                draw.text((i_child + 56, y + 2), r[0], font=font_sm, fill=TXT_DIM)
                draw.text((i_child + 114, y + 2), (r[1] or "")[:30], font=font_sm, fill=TXT_MAIN)
                y += badge_h

            img.save(os.path.join(REPORT_DIR, "belum_dibuat_report.png"))
        def _build_ongoing():
            """Report ON PROGRESS - grouping Area > Wilayah, 2 column."""
            if not ongoing_list:
                return None
            pad = 14
            row_h = 16
            total_w = 1610
            hdr_y = 40
            col_mulai = 80
            col_pic = 140
            col_isi = 35
            col_sisa = 35
            col_durasi = 50
            half_w = (total_w - pad - pad) // 2
            col_kantor = half_w - col_mulai - col_pic - col_isi - col_sisa - col_durasi

            BG = (15, 15, 25)
            HDR_BG = (35, 35, 50)
            SECTION_BG = (42, 51, 75)
            ROW_A = (20, 23, 20)
            ROW_B = (25, 28, 25)
            TXT_MAIN = (217, 217, 237)
            TXT_SEC = (180, 181, 196)
            TXT_DIM = (149, 150, 165)
            TXT_HDR = (200, 200, 215)
            TXT_WIL = (130, 130, 160)
            YELLOW = (255, 200, 90)
            GREEN = (100, 200, 150)
            TITLE_CLR = (255, 255, 255)

            def _group_branches(dlist):
                groups = {}
                for r in dlist:
                    kc = r[0]
                    bi = branch_info.get(kc, {})
                    if not bi:
                        continue
                    pc = (bi.get("path_code") or "").split(">")
                    pn = (bi.get("path_name") or "").split(" > ")
                    a_code = pc[1] if len(pc) >= 2 else "??"
                    a_name = pn[1] if len(pn) >= 2 else a_code
                    w_code = pc[2] if len(pc) >= 3 else a_code
                    w_name = pn[2] if len(pn) >= 3 else w_code
                    key = (a_code, a_name)
                    if key not in groups:
                        groups[key] = {}
                    wk = (w_code, w_name)
                    if wk not in groups[key]:
                        groups[key][wk] = []
                    groups[key][wk].append(r)
                return groups

            def _flatten_groups(groups):
                flat = []
                for (a_code, a_name), wilayahs in sorted(groups.items()):
                    flat.append(("area", f"{a_code} {a_name}", None, sum(len(v) for v in wilayahs.values())))
                    for (w_code, w_name), items in sorted(wilayahs.items()):
                        flat.append(("wilayah", f"{w_name} ({len(items)})", None, items))
                return flat

            groups = _group_branches(ongoing_list)
            flat = _flatten_groups(groups)

            def _calc_h(flat_subset):
                h = hdr_y + 16
                for item in flat_subset:
                    if item[0] == "area":
                        h += 26
                    elif item[0] == "wilayah":
                        h += 20 + len(item[3]) * row_h
                    else:
                        h += len(item[3]) * row_h
                return h + 24

            # Load balance into 2 columns
            total_items = len(ongoing_list)
            left_flat = []
            right_flat = []
            left_count = 0
            mid_count = total_items // 2
            for item in flat:
                if item[0] == "area":
                    if left_count < mid_count:
                        left_flat.append(item)
                    else:
                        right_flat.append(item)
                elif item[0] == "wilayah":
                    cnt = item[3] if isinstance(item[3], int) else len(item[3])
                    if left_count < mid_count:
                        left_flat.append(item)
                        left_count += cnt
                    else:
                        right_flat.append(item)
                else:
                    left_flat.append(item)
                    left_count += len(item[3])

            total_h = max(_calc_h(left_flat), _calc_h(right_flat)) + 40
            total_h = max(300, min(6000, total_h))

            img = Image.new("RGB", (total_w, total_h), BG)
            draw = ImageDraw.Draw(img)
            draw.text((pad, 10), f"On Progress ({len(ongoing_list)})", font=font_reg, fill=TITLE_CLR)

            def _draw_one_col(data_flat, x0, w):
                y = hdr_y
                # Header kolom
                draw.rectangle([x0, y, x0 + w, y + 17], fill=HDR_BG)
                # border bawah header
                draw.line([(x0, y + 17), (x0 + w, y + 17)], fill=(60, 60, 80), width=1)
                hx = x0
                for lbl, lw in [("Mulai", col_mulai), ("Kantor", col_kantor), ("PIC", col_pic), ("Isi", col_isi), ("Sisa", col_sisa), ("Durasi", col_durasi)]:
                    draw.text((hx + 3, y + 2), lbl, font=font_bold, fill=(230, 230, 245))
                    hx += lw
                y += 20

                for item in data_flat:
                    if item[0] == "area":
                        draw.rectangle([x0, y, x0 + w, y + 26], fill=SECTION_BG)
                        draw.text((x0 + 4, y + 6), item[1], font=font_reg, fill=TXT_DIM)
                        y += 26
                    elif item[0] == "wilayah":
                        draw.text((x0 + 4, y + 3), item[1], font=font_sm, fill=TXT_WIL)
                        y += 20
                        for r in item[3]:
                            kc = r[0]
                            yc = r[3] or 0
                            tc = r[4] or 1
                            pic = str(r[12] or r[5] or "")[:25]
                            bi = branch_info.get(kc, {})
                            bname = (bi.get("display_name") or kc) if bi else kc
                            sisa = max(0, tc - yc)
                            upd_ts = r[8]
                            jam_str = upd_ts.astimezone(tz).strftime("%d %b %H:%M") if upd_ts else "-"

                            # Durasi: updated_at - created_at
                            ca = r[13] if len(r) > 13 else None  # created_at index
                            dur_str = "-"
                            if upd_ts and ca:
                                delta = upd_ts - ca
                                secs = delta.total_seconds()
                                if secs >= 0:
                                    hrs = int(secs // 3600)
                                    mins = int((secs % 3600) // 60)
                                    if hrs >= 24:
                                        dur_str = f"{hrs//24}d {hrs%24}h"
                                    elif hrs > 0:
                                        dur_str = f"{hrs}h {mins}m"
                                    else:
                                        dur_str = f"{mins}m"

                            yy = y
                            bg = ROW_A if (yy // row_h) % 2 == 0 else ROW_B
                            draw.rectangle([x0, yy, x0 + w, yy + row_h], fill=bg)

                            xx = x0
                            draw.text((xx, yy), jam_str, font=font_sm, fill=TXT_DIM)
                            xx += col_mulai
                            clean = bname[7:] if len(bname) > 7 and bname[:5] == kc else (bname or "")[:30]
                            draw.text((xx, yy), f"{kc} \u2014 {clean}", font=font_sm, fill=TXT_MAIN)
                            xx += col_kantor
                            draw.text((xx, yy), pic, font=font_sm, fill=TXT_SEC)
                            xx += col_pic
                            draw.text((xx, yy), str(yc), font=font_sm, fill=YELLOW if yc > 1 else TXT_MAIN)
                            xx += col_isi
                            draw.text((xx, yy), str(sisa), font=font_sm, fill=GREEN if sisa == 0 else TXT_MAIN)
                            xx += col_sisa
                            draw.text((xx, yy), dur_str, font=font_sm, fill=TXT_DIM)
                            y += row_h

            _draw_one_col(left_flat, pad, half_w)
            _draw_one_col(right_flat, pad + half_w, half_w)
            footer_y = max(_calc_h(left_flat), _calc_h(right_flat)) + 10
            draw.text((pad, footer_y), f"Total: {len(ongoing_list)} draft", font=font_sm, fill=TXT_DIM)
            img.save(os.path.join(REPORT_DIR, "ongoing_report.png"))

        def _build_submitted():
            """Report SUBMITTED - grouping Area > Wilayah, 2 column."""
            if not submitted_list:
                return None
            pad = 14
            row_h = 15
            total_w = 1405
            hdr_y = 40
            col_jam = 80
            col_nilai = 50
            col_pic = 145
            half_w = (total_w - pad - pad) // 2
            col_kantor = half_w - col_jam - col_pic - col_nilai

            BG = (15, 15, 25)
            HDR_BG = (35, 35, 50)
            SECTION_BG = (42, 51, 75)
            ROW_A = (20, 23, 20)
            ROW_B = (25, 28, 25)
            TXT_MAIN = (217, 217, 237)
            TXT_SEC = (180, 181, 196)
            TXT_DIM = (149, 150, 165)
            TXT_HDR = (200, 200, 215)
            GREEN = (140, 210, 155)
            YELLOW = (255, 200, 90)
            RED = (248, 113, 113)
            TITLE_CLR = (255, 255, 255)

            # Group by area > wilayah, lalu bagi 2 utk 2 kolom
            def _group_branches(dlist):
                groups = {}
                for r in dlist:
                    kc = r[0]
                    bi = branch_info.get(kc, {})
                    if not bi:
                        continue
                    pc = (bi.get("path_code") or "").split(">")
                    pn = (bi.get("path_name") or "").split(" > ")
                    a_code = pc[1] if len(pc) >= 2 else "??"
                    a_name = pn[1] if len(pn) >= 2 else a_code
                    w_code = pc[2] if len(pc) >= 3 else a_code
                    w_name = pn[2] if len(pn) >= 3 else w_code
                    key = (a_code, a_name)
                    if key not in groups:
                        groups[key] = {}
                    wk = (w_code, w_name)
                    if wk not in groups[key]:
                        groups[key][wk] = []
                    groups[key][wk].append(r)
                return groups

            def _flatten_groups(groups):
                """Flatten into list of (is_section, area_label, wil_label, items)"""
                flat = []
                for (a_code, a_name), wilayahs in sorted(groups.items()):
                    area_label = f"{a_code} {a_name}"
                    total_a = sum(len(items) for items in wilayahs.values())
                    flat.append(("area", area_label, None, total_a))
                    for (w_code, w_name), items in sorted(wilayahs.items()):
                        wil_label = f"{w_name} ({len(items)})"
                        flat.append(("wilayah", wil_label, None, items))
                return flat

            groups = _group_branches(submitted_list)
            flat = _flatten_groups(groups)

            # Estimate height: split flat into 2 columns
            # Count rows per column
            def _calc_h(flat_subset):
                h = hdr_y + 16
                for item in flat_subset:
                    if item[0] == "area":
                        h += 26
                    elif item[0] == "wilayah":
                        h += 20 + len(item[3]) * row_h
                    else:
                        h += len(item[3]) * row_h
                return h + 24

            # Split: load balance by item count
            total_items = len(submitted_list)
            left_flat = []
            right_flat = []
            left_count = 0
            mid_count = total_items // 2
            for item in flat:
                if item[0] == "area":
                    if left_count < mid_count:
                        left_flat.append(item)
                    else:
                        right_flat.append(item)
                elif item[0] == "wilayah":
                    cnt = len(item[3])
                    if left_count < mid_count:
                        left_flat.append(item)
                        left_count += cnt
                    else:
                        right_flat.append(item)
                else:
                    left_flat.append(item)
                    left_count += len(item[3])

            total_h = max(_calc_h(left_flat), _calc_h(right_flat)) + 40
            total_h = max(300, min(6000, total_h))

            img = Image.new("RGB", (total_w, total_h), BG)
            draw = ImageDraw.Draw(img)
            draw.text((pad, 10), f"Submitted ({len(submitted_list)})", font=font_reg, fill=TITLE_CLR)

            def _draw_one_col(data_flat, x0, w):
                y = hdr_y
                # Header kolom
                draw.rectangle([x0, y, x0 + w, y + 17], fill=HDR_BG)
                # border bawah header
                draw.line([(x0, y + 17), (x0 + w, y + 17)], fill=(60, 60, 80), width=1)
                hx = x0
                for lbl, lw in [("Jam", col_jam), ("Kantor", col_kantor), ("PIC", col_pic), ("Nilai", col_nilai)]:
                    draw.text((hx + 3, y + 2), lbl, font=font_bold, fill=(230, 230, 245))
                    hx += lw
                y += 20

                for item in data_flat:
                    typ = item[0]
                    if typ == "area":
                        draw.rectangle([x0, y, x0 + w, y + 26], fill=SECTION_BG)
                        draw.text((x0 + 4, y + 6), item[1], font=font_reg, fill=TXT_DIM)
                        y += 26
                    elif typ == "wilayah":
                        draw.text((x0 + 4, y + 3), item[1], font=font_sm, fill=(130, 130, 160))
                        y += 20
                        for r in item[3]:
                            kc = r[0]
                            pic = str(r[12] or r[5] or "")[:25]
                            wscore = float(r[9]) if r[9] else 0
                            bi = branch_info.get(kc, {})
                            bname = (bi.get("display_name") or kc) if bi else kc
                            score_str = f"{wscore:.1f}"
                            sc = GREEN if wscore >= 80 else YELLOW if wscore >= 60 else RED
                            sub_ts = r[7]
                            jam_str = sub_ts.astimezone(tz).strftime("%d %b %H:%M") if sub_ts else "-"

                            yy = y
                            bg = ROW_A if (yy // row_h) % 2 == 0 else ROW_B
                            draw.rectangle([x0, yy, x0 + w, yy + row_h], fill=bg)

                            xx = x0
                            draw.text((xx, yy), jam_str, font=font_sm, fill=TXT_DIM)
                            xx += col_jam
                            clean = bname[7:] if len(bname) > 7 and bname[:5] == kc else (bname or "")[:35]
                            draw.text((xx, yy), f"{kc} \u2014 {clean}", font=font_sm, fill=TXT_MAIN)
                            xx += col_kantor
                            draw.text((xx, yy), pic, font=font_sm, fill=TXT_SEC)
                            xx += col_pic
                            draw.text((xx, yy), score_str, font=font_sm, fill=sc)
                            y += row_h

            _draw_one_col(left_flat, pad, half_w)
            _draw_one_col(right_flat, pad + half_w, half_w)
            footer_y = max(_calc_h(left_flat), _calc_h(right_flat)) + 10
            draw.text((pad, footer_y), f"Total: {len(submitted_list)} submitted", font=font_sm, fill=TXT_DIM)
            img.save(os.path.join(REPORT_DIR, "submitted_report.png"))

        _build_belum()
        _build_ongoing()
        _build_submitted()

        return JSONResponse({"ok": True, "message": "3 reports regenerated"})
    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)



async def pdf_public(kantor_code: str):
    """Endpoint publik - serve PDF tanpa login. Generate kalo belum ada."""
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute(
            """SELECT status_data, nomor_survei, survey_seq, updated_at
               FROM origo.kantor_checklist_data
               WHERE kantor_code = %s ORDER BY survey_seq DESC LIMIT 1""",
            (kantor_code,)
        )
        row = cur.fetchone()
        cur.close(); conn.close()
        if not row:
            return HTMLResponse("Data tidak ditemukan", status_code=404)

        import os, base64, json
        from collections import defaultdict
        from datetime import datetime as dtdt

        items = row[0]
        nomor = row[1]
        seq = row[2]
        updated_at = row[3]
        kode = kantor_code

        PDF_DIR = "/home/bhc0104/survey_app/pdfs"
        os.makedirs(PDF_DIR, exist_ok=True)
        pdf_fname = f"survei_{kode}_{nomor or 'unknown'}.pdf".replace("/","_").replace(" ","_")
        pdf_fpath = os.path.join(PDF_DIR, pdf_fname)

        # Kalo PDF udah ada, cek apakah data masih fresh
        if os.path.exists(pdf_fpath):
            mt = os.path.getmtime(pdf_fpath)
            db_ts = updated_at.timestamp() if updated_at else 0
            if mt >= db_ts:
                from fastapi.responses import FileResponse
                return FileResponse(pdf_fpath, media_type="application/pdf",
                    filename=pdf_fname,
                    headers={"Content-Disposition": "inline"})
            # else: data lebih baru dari PDF → regenerate

        # Generate HTML untuk PDF
        db_items = _get_items_from_db()

        PHOTO_DIR = "/home/bhc0104/survey_app/uploads"
        # ── Lookup label status dinamis dari options DB ──
        def _lookup_status_label(sv, options):
            if sv < 0: return "-"
            for opt in (options or []):
                if opt.get("score") == sv:
                    prefix = "✅" if sv == 0 else "⚠️" if sv == 1 else "❌"
                    return f"{prefix} {opt.get('label','?')}"
            return {0:"✅ Baik",1:"⚠️ Rusak",2:"❌ Tidak",3:"❌ Kurang",4:"❌ Tidak"}.get(sv, "-")

        cat_data = defaultdict(lambda: {"items":[], "baik":0, "rusak":0, "total":0, "label":""})
        lampiran_foto = []

        for i, it in enumerate(items):
            if i >= len(db_items): continue
            di = db_items[i]
            st = it.get("status","") if isinstance(it, dict) else ""
            note = it.get("note","") if isinstance(it, dict) else ""
            foto_path = it.get("foto","") if isinstance(it, dict) else ""
            foto_desc = it.get("foto_desc","") if isinstance(it, dict) else ""
            foto_relevan = it.get("foto_relevan", True) if isinstance(it, dict) else True
            geo = it.get("geo","") if isinstance(it, dict) else ""
            try: sv = int(st)
            except: sv = -1
            label = _lookup_status_label(sv, di.get("options",[]))
            cat_code = di.get('cat','?')
            cat_data[cat_code]["label"] = cat_code
            cat_data[cat_code]["total"] += 1
            if sv == 0: cat_data[cat_code]["baik"] += 1
            if sv > 0: cat_data[cat_code]["rusak"] += 1
            cat_data[cat_code]["items"].append({
                "num": len(cat_data[cat_code]["items"])+1,
                "label": di.get('label',''),
                "status": label,
                "note": note,
                "foto_path": foto_path,
                "foto_desc": foto_desc,
                "foto_relevan": foto_relevan
            })
            if foto_path and foto_path.startswith("/survey/uploads/"):
                fname = foto_path.replace("/survey/uploads/", "")
                fpath = os.path.join(PHOTO_DIR, fname)
                if os.path.exists(fpath):
                    try:
                        with open(fpath, "rb") as fimg:
                            b64 = base64.b64encode(fimg.read()).decode()
                        lampiran_foto.append({"cat": cat_code, "item": di['label'],
                            "b64": b64, "desc": foto_desc, "relevan": foto_relevan, "geo": geo})
                    except: pass

        total_items = sum(c["total"] for c in cat_data.values())
        total_baik = sum(c["baik"] for c in cat_data.values())
        # Gunakan weighted scoring sesuai form survey
        ws_pdf, _, _, _ = _hitung_weighted_score(items, db_items)
        skor = round(ws_pdf, 1) if ws_pdf else round(total_baik / total_items * 100, 1) if total_items > 0 else 0

        pages = []
        pages.append("""<!doctype html><html><head><meta charset="utf-8">
<style>
@page{size:A4;margin:10mm 8mm}
body{font-family:DejaVu Sans,sans-serif;font-size:9pt;color:#1e293b}
h1{font-size:14pt;text-align:center;margin:0 0 2px 0;color:#0f172a}
h2{font-size:11pt;text-align:center;margin:0 0 6px 0;color:#475569}
h3{font-size:10pt;margin:10px 0 4px 0;border-bottom:2px solid #e2e8f0;padding-bottom:3px;color:#1e293b}
table{width:100%;border-collapse:collapse;margin:4px 0}
th{background:#0f172a;color:white;padding:3px 5px;text-align:left;font-size:7pt;font-weight:bold}
td{border:1px solid #e2e8f0;padding:2px 5px;text-align:left;font-size:7pt;color:#334155}
tr:nth-child(even){background:#f8fafc}
tr:hover{background:#f1f5f9}
.page-break{page-break-before:always}
.footer{text-align:center;color:#94a3b8;font-size:7pt;margin-top:8mm}
.skor-box{text-align:center;padding:10px;background:linear-gradient(135deg,#f8fafc,#f1f5f9);border:1px solid #e2e8f0;border-radius:8px;margin:6px 0}
.skor-angka{font-size:22pt;font-weight:bold}
.stat-baik{color:#16a34a;font-weight:bold}
.stat-rusak{color:#dc2626;font-weight:bold}
.stat-sedang{color:#d97706;font-weight:bold}
.lamp-item{margin:4px 0;page-break-inside:avoid;background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;padding:4px 6px}
.lamp-item img{max-width:140mm;max-height:70mm;display:block;margin:2px auto}
.badge{display:inline-block;padding:1px 6px;border-radius:4px;font-size:6.5pt;font-weight:bold}
.badge-baik{background:#dcfce7;color:#166534}
.badge-rusak{background:#fef2f2;color:#991b1b}
.badge-sedang{background:#fef3c7;color:#92400e}
</style></head><body>""")
        pages.append("<h1>LAPORAN SURVEI KONDISI KANTOR</h1>")
        pages.append(f"<h2>Kantor: {kantor_code}</h2>")
        pages.append("<hr>")

        # Summary
        skor_color = "#16a34a" if skor >= 70 else "#d97706" if skor >= 40 else "#dc2626"
        pages.append(f"<div class='skor-box'>Skor Kategori: <span class='skor-angka' style='color:{skor_color}'>{skor}%</span><br><span style='font-size:8pt;color:#64748b'>Kategori Baik: {total_baik}/{total_items}</span></div>")

        # Top 5 Baik & Buruk
        baik_items = [(i,it) for i,it in enumerate(items) if i<len(db_items) and isinstance(it,dict) and str(it.get("status","")).isdigit() and int(it.get("status","99")) == 0]
        rusak_items = [(i,it) for i,it in enumerate(items) if i<len(db_items) and isinstance(it,dict) and str(it.get("status","")).isdigit() and int(it.get("status","99")) > 0]

        pages.append("<h3>🏆 5 Terbaik</h3><table><tr><th>#</th><th>Item</th><th>Status</th></tr>")
        for ii, it in baik_items[:5]:
            di = db_items[ii]
            pages.append(f"<tr><td style='text-align:center'>{ii+1}</td><td>{di['cat']} - {di['label'][:40]}</td><td style='text-align:center'>✅ Baik</td></tr>")
        pages.append("</table>")

        pages.append("<h3>🔻 5 Terburuk</h3><table><tr><th>#</th><th>Item</th><th>Status</th></tr>")
        for ii, it in rusak_items[:5]:
            di = db_items[ii]
            st = int(it.get("status","0"))
            pages.append(f"<tr><td style='text-align:center'>{ii+1}</td><td>{di['cat']} - {di['label'][:40]}</td><td style='text-align:center'>{_lookup_status_label(st, di.get('options',[]))}</td></tr>")
        pages.append("</table>")

        # ── Prioritas Perbaikan ──
        # Hitung: weight × (score_user/4). Semakin besar = prioritas semakin tinggi
        prioritas_list = []
        for i, it in enumerate(items):
            if i >= len(db_items): continue
            if not isinstance(it, dict): continue
            sv_str = it.get("status","")
            try: sv = int(sv_str)
            except: continue
            if sv == 0: continue  # skip yang udah baik
            di = db_items[i]
            weight = di.get("weight", 0) or 0
            prioritas = float(weight) * (sv / 4.0)
            prioritas_list.append((prioritas, i, sv, di))

        prioritas_list.sort(key=lambda x: x[0], reverse=True)
        if prioritas_list:
            pages.append("<h3>📊 Prioritas Perbaikan</h3>")
            pages.append("<table><tr><th>#</th><th>Item</th><th>Bobot</th><th>Status</th><th>Skor Prioritas</th><th>Saran</th></tr>")
            for rank, (prior, i, sv, di) in enumerate(prioritas_list[:10], 1):
                pct = round(prior * 100, 1)
                bobot_pct = round(float(di.get("weight",0) or 0) * 100, 1)
                pages.append(f"<tr><td style='text-align:center'>{rank}</td><td>{di['cat']} - {di['label'][:35]}</td><td style='text-align:center'>{bobot_pct}%</td><td style='text-align:center'>{_lookup_status_label(sv, di.get('options',[]))}</td><td style='text-align:center'>{pct}%</td><td style='font-size:6.5pt'>Prioritas perbaikan - item ini berbobot {bobot_pct}% tapi masih bermasalah</td></tr>")
            pages.append("</table>")

        # Detail per kategori
        pages.append("<div class='page-break'></div>")
        pages.append("<h1 style='font-size:13pt'>Detail per Kategori</h1>")
        for ck in sorted(cat_data.keys()):
            cd = cat_data[ck]
            cpct = round(cd["baik"] / cd["total"] * 100, 1) if cd["total"] > 0 else 0
            pages.append(f"<h3>{ck} - {cpct}%</h3>")
            pages.append("<table><tr><th>#</th><th>Pernyataan</th><th>Status</th><th>Foto</th><th>Deskripsi</th><th>Catatan</th></tr>")
            for ci in cd["items"]:
                img_td = "<td style='text-align:center'>-</td>"
                if ci["foto_path"] and ci["foto_path"].startswith("/survey/uploads/"):
                    fn = ci["foto_path"].replace("/survey/uploads/", "")
                    fp = os.path.join(PHOTO_DIR, fn)
                    if os.path.exists(fp):
                        try:
                            with open(fp, "rb") as fimg:
                                b64i = base64.b64encode(fimg.read()).decode()
                            img_td = f"<td style='text-align:center'><img src='data:image/jpeg;base64,{b64i}' style='width:42px;height:42px;object-fit:cover;'></td>"
                        except: pass
                rel_str = ""
                if ci["foto_desc"]:
                    rel_str = "<br><span style='color:#dc2626;font-size:6pt;'>⚠️ Foto mungkin tdk sesuai</span>" if ci.get("foto_relevan") == False else "<br><span style='color:#16a34a;font-size:6pt;'>✅ Foto sesuai</span>"
                # Badge warna berdasarkan status
                st_str = ci['status']
                if '✅' in st_str: badge_class = "badge-baik"
                elif '⚠' in st_str or '⚠️' in st_str: badge_class = "badge-sedang"
                else: badge_class = "badge-rusak"
                st_badge = f"<span class='badge {badge_class}'>{st_str}</span>"
                row_style = " style='background:#fef2f2;'" if ci.get("foto_desc") and ci["foto_relevan"] == False else ""
                desc_str = f"<td style='font-size:6.5pt;color:#555'>{ci.get('foto_desc','')[:60] if ci.get('foto_desc') else '-'}{rel_str}</td>"
                pages.append(f"<tr{row_style}><td style='text-align:center'>{ci['num']}</td><td>{ci['label'][:45]}</td><td style='text-align:center;font-size:7pt'>{st_badge}</td>{img_td}{desc_str}<td style='font-size:6.5pt;color:#888'>{ci['note'][:30] if ci.get('note') else '-'}</td></tr>")
            pages.append("</table>")

        # Lampiran foto
        if lampiran_foto:
            pages.append("<div class='page-break'></div>")
            pages.append("<h1 style='font-size:13pt'>Lampiran Foto</h1>")
            for lf in lampiran_foto:
                pages.append("<div class='lamp-item'>")
                pages.append(f"<strong>{lf['cat']} - {lf['item'][:45]}</strong><br>")
                pages.append(f"<img src='data:image/jpeg;base64,{lf['b64']}'>")
                if lf['desc']: pages.append(f"<div style='font-size:7pt;color:#555;'>{lf['desc'][:80]}</div>")
                if lf['geo']: pages.append(f"<span style='font-size:6pt;color:#888;'>{lf['geo']}</span>")
                pages.append("</div>")

        pages.append("<div class='footer'>Dicetak: " + dtdt.now().strftime('%d-%m-%Y %H:%M') + " WIB</div>")
        pages.append("</body></html>")
        html = "\n".join(pages)

        # Generate PDF
        from weasyprint import HTML as WPHTML
        WPHTML(string=html).write_pdf(pdf_fpath)

        # Simpan path di media_data
        try:
            conn2 = get_db(); cur2 = conn2.cursor()
            md_new = {"pdf_path": f"/survey/pdfs/{pdf_fname}"}
            cur2.execute("UPDATE origo.kantor_checklist_data SET media_data = %s WHERE kantor_code = %s AND survey_seq = %s",
                         (json.dumps(md_new), kode, seq))
            conn2.commit()
            cur2.close(); conn2.close()
        except: pass

        from fastapi.responses import FileResponse
        return FileResponse(pdf_fpath, media_type="application/pdf",
            filename=pdf_fname,
            headers={"Content-Disposition": "inline"})

    except Exception as e:
        import traceback; traceback.print_exc()
        return HTMLResponse(f"<h2>PDF Error: {e}</h2><pre>{traceback.format_exc()}</pre>", status_code=500)

@router.get("/survey/api/public/pdf/{kantor_code}")
async def pdf_public_route(kantor_code: str):
    return await pdf_public(kantor_code)


@router.get("/survey/api/kantor-checklist/area-summary")
async def area_summary_api(request: Request, session: Optional[str] = Cookie(None)):
    """Ringkasan per area/wilayah - submitted/draft count + avg score."""
    user = get_user_from_cookie(session)
    if not user:
        return JSONResponse({"ok": False, "error": "Not logged in"}, status_code=401)
    try:
        conn = get_db(); cur = conn.cursor()
        # Ambil tree path + kantor data
        cur.execute("""
            WITH RECURSIVE tree AS (
                SELECT id, parent_id, node_code, display_name, branch_kind, office_code,
                       1 AS depth, CAST(node_code AS text) AS path_code, CAST(display_name AS text) AS path_name
                FROM origo.network_tree_node
                WHERE version_id = (SELECT id FROM origo.network_tree_version WHERE is_published = TRUE LIMIT 1)
                  AND parent_id IS NULL
                UNION ALL
                SELECT n.id, n.parent_id, n.node_code, n.display_name, n.branch_kind, n.office_code,
                       t.depth + 1,
                       t.path_code || '>' || n.node_code,
                       t.path_name || ' > ' || n.display_name
                FROM origo.network_tree_node n
                JOIN tree t ON n.parent_id = t.id
                WHERE n.version_id = (SELECT id FROM origo.network_tree_version WHERE is_published = TRUE LIMIT 1)
            )
            SELECT office_code, display_name, branch_kind, path_code, path_name
            FROM tree
            WHERE branch_kind NOT IN ('area','wilayah') AND office_code IS NOT NULL
        """)
        branch_area = {}  # office_code -> {area_code, area_name, wilayah_code, wilayah_name}
        for r in cur.fetchall():
            kc = r[0]
            pc = (r[3] or "").split(">")
            pn = (r[4] or "").split(" > ")
            branch_area[kc] = {
                "area_code": pc[1] if len(pc) >= 2 else "?",
                "area_name": pn[1] if len(pn) >= 2 else "?",
                "wilayah_code": pc[2] if len(pc) >= 3 else pc[1] if len(pc) >= 2 else "?",
                "wilayah_name": pn[2] if len(pn) >= 3 else pn[1] if len(pn) >= 2 else "?",
            }

        # Ambil semua data checklist
        cur.execute("""
            SELECT kcd.kantor_code, kcd.workflow_status, kcd.weighted_score,
                   COALESCE(fu."NAME_FULL", fe.name_full, kcd.pic) AS pic_name
            FROM origo.kantor_checklist_data kcd
            LEFT JOIN "i_fast"."FS_SEC_USERS" fu ON kcd.pic = fu."USER_ID"
            LEFT JOIN f_fifapps.fs_sec_users fe ON kcd.pic = fe.user_id
            WHERE kcd.yes_count IS NOT NULL AND kcd.total_items > 0
        """)

        # Inisialisasi struktur per area
        areas = {}
        wilayahs = {}

        for r in cur.fetchall():
            kc = r[0]
            ws = str(r[1] or "")
            score = float(r[2]) if r[2] else None
            pic = str(r[3] or "?")
            ba = branch_area.get(kc, {})
            a_code = ba.get("area_code", "?")
            a_name = ba.get("area_name", "?")
            w_code = ba.get("wilayah_code", "?")
            w_name = ba.get("wilayah_name", "?")

            # Group by area
            if a_code not in areas:
                areas[a_code] = {"code": a_code, "name": a_name, "total": 0, "submitted": 0, "draft": 0, "scores": []}
            areas[a_code]["total"] += 1
            if ws in ("submitted", "final"):
                areas[a_code]["submitted"] += 1
                if score is not None:
                    areas[a_code]["scores"].append(score)
            elif ws == "draft" and r[2] is not None:
                areas[a_code]["draft"] += 1

            # Group by wilayah
            wk = f"{a_code}>{w_code}"
            if wk not in wilayahs:
                wilayahs[wk] = {"area_code": a_code, "area_name": a_name, "wilayah_code": w_code, "wilayah_name": w_name, "total": 0, "submitted": 0, "draft": 0, "scores": []}
            wilayahs[wk]["total"] += 1
            if ws in ("submitted", "final"):
                wilayahs[wk]["submitted"] += 1
                if score is not None:
                    wilayahs[wk]["scores"].append(score)
            elif ws == "draft":
                wilayahs[wk]["draft"] += 1

        cur.close(); conn.close()

        def _summarize(groups):
            result = []
            for k, v in groups.items():
                scores = v["scores"]
                avg_score = round(sum(scores) / len(scores), 1) if scores else None
                pct = round(v["submitted"] / v["total"] * 100, 1) if v["total"] > 0 else 0
                v["avg_score"] = avg_score
                v["pct_submitted"] = pct
                v.pop("scores", None)
                result.append(v)
            return sorted(result, key=lambda x: x.get("code", x.get("wilayah_code", "")) if "code" in x or "wilayah_code" in x else "")

        return JSONResponse({
            "ok": True,
            "areas": _summarize(areas),
            "wilayahs": _summarize(wilayahs),
            "area_branch_map": {k: ba for k, ba in sorted(branch_area.items())}
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/survey/api/kantor-checklist/branch-tree")
async def branch_tree_api(request: Request, session: Optional[str] = Cookie(None)):
    """Return all branches with area/wilayah info for filter dropdown."""
    user = get_user_from_cookie(session)
    if not user:
        return JSONResponse({"ok": False, "error": "Not logged in"}, status_code=401)
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("""
            WITH RECURSIVE tree AS (
                SELECT id, parent_id, node_code, display_name, branch_kind, office_code,
                       1 AS depth, CAST(node_code AS text) AS path_code, CAST(display_name AS text) AS path_name
                FROM origo.network_tree_node
                WHERE version_id = (SELECT id FROM origo.network_tree_version WHERE is_published = TRUE LIMIT 1)
                  AND parent_id IS NULL
                UNION ALL
                SELECT n.id, n.parent_id, n.node_code, n.display_name, n.branch_kind, n.office_code,
                       t.depth + 1,
                       t.path_code || '>' || n.node_code,
                       t.path_name || ' > ' || n.display_name
                FROM origo.network_tree_node n
                JOIN tree t ON n.parent_id = t.id
                WHERE n.version_id = (SELECT id FROM origo.network_tree_version WHERE is_published = TRUE LIMIT 1)
            )
            SELECT office_code, display_name, branch_kind, path_code, path_name
            FROM tree
            WHERE branch_kind NOT IN ('area','wilayah') AND office_code IS NOT NULL
        """)
        branches = []
        for r in cur.fetchall():
            oc = r[0]
            pc = (r[3] or "").split(">")
            pn = (r[4] or "").split(" > ")
            area_code = pc[1] if len(pc) >= 2 else "?"
            area_name = pn[1] if len(pn) >= 2 else "?"
            wilayah_code = pc[2] if len(pc) >= 3 else pc[1] if len(pc) >= 2 else "?"
            wilayah_name = pn[2] if len(pn) >= 3 else pn[1] if len(pn) >= 2 else "?"
            branches.append({
                "office_code": oc,
                "display_name": r[1],
                "area_code": area_code,
                "area_name": area_name,
                "wilayah_code": wilayah_code,
                "wilayah_name": wilayah_name,
            })
        cur.close(); conn.close()
        return JSONResponse({"ok": True, "branches": branches})
    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({"ok": False, "error": str(e)[:200]}, status_code=500)


@router.get("/survey/api/kantor-checklist/item-stats")
@router.post("/survey/api/log-share")
async def item_stats_api(request: Request, session: Optional[str] = Cookie(None),
                         area_code: str = Query(""), wilayah_code: str = Query("")):
    """Per-item + per-kategori stats dengan filter area/wilayah."""
    user = get_user_from_cookie(session)
    if not user:
        return JSONResponse({"ok": False, "error": "Not logged in"}, status_code=401)
    try:
        conn = get_db(); cur = conn.cursor()

        # Ambil semua branch + mapping area/wilayah
        cur.execute("""
            WITH RECURSIVE tree AS (
                SELECT id, parent_id, node_code, display_name, branch_kind, office_code,
                       1 AS depth, CAST(node_code AS text) AS path_code, CAST(display_name AS text) AS path_name
                FROM origo.network_tree_node
                WHERE version_id = (SELECT id FROM origo.network_tree_version WHERE is_published = TRUE LIMIT 1)
                  AND parent_id IS NULL
                UNION ALL
                SELECT n.id, n.parent_id, n.node_code, n.display_name, n.branch_kind, n.office_code,
                       t.depth + 1,
                       t.path_code || '>' || n.node_code,
                       t.path_name || ' > ' || n.display_name
                FROM origo.network_tree_node n
                JOIN tree t ON n.parent_id = t.id
                WHERE n.version_id = (SELECT id FROM origo.network_tree_version WHERE is_published = TRUE LIMIT 1)
            )
            SELECT office_code, path_code, path_name
            FROM tree
            WHERE branch_kind NOT IN ('area','wilayah') AND office_code IS NOT NULL
        """)
        branch_area = {}
        for r in cur.fetchall():
            oc = r[0]; pc = (r[1] or "").split(">"); pn = (r[2] or "").split(" > ")
            branch_area[oc] = {
                "area_code": pc[1] if len(pc) >= 2 else "?",
                "area_name": pn[1] if len(pn) >= 2 else "?",
                "wilayah_code": pc[2] if len(pc) >= 3 else pc[1] if len(pc) >= 2 else "?",
                "wilayah_name": pn[2] if len(pn) >= 3 else pn[1] if len(pn) >= 2 else "?",
            }

        # Ambil semua data checklist
        cur.execute("""
            SELECT kantor_code, status_data, yes_count, no_count, total_items, workflow_status
            FROM origo.kantor_checklist_data
            WHERE status_data IS NOT NULL AND jsonb_array_length(status_data) > 0
              AND workflow_status IN ('submitted', 'reviewed', 'approved')
        """)

        dbitems = _get_items_from_db()
        if not dbitems:
            return JSONResponse({"ok": False, "error": "No items"}, status_code=500)

        # Ambil kategori + bobot — pake cursor terpisah biar gak timpa data checklist
        cur2 = conn.cursor()
        cur2.execute("SELECT cat_code, cat_name, cat_weight::float FROM origo.survey_categories ORDER BY sort_order")
        cats_raw = {r[0]: {"name": r[1], "weight": r[2]} for r in cur2.fetchall()}
        cur2.close()

        # Ambil opsi
        cur2 = conn.cursor()
        cur2.execute("""
            SELECT t.type_code, o.opt_value::int, o.weight_mult, o.opt_label, COALESCE(o.is_no, false)
            FROM origo.survey_question_types t
            JOIN origo.survey_type_options o ON t.id = o.type_id
            ORDER BY t.type_code, o.sort_order
        """)
        opt_labels = {}
        for tc, ov, wm, lbl, inh in cur2.fetchall():
            opt_labels.setdefault(tc, {})[ov] = {"label": lbl, "is_no": inh, "weight_mult": float(wm)}
        cur2.close()

        # Kelompokkan items per kategori
        cat_items = {}
        for i, di in enumerate(dbitems):
            cc = di["cat"]
            cat_items.setdefault(cc, []).append({"idx": i, "weight": di["weight"]})

        # Kumpulin status per item — sambil filter area/wilayah
        ist = {i: {"total": 0, "score_sum": 0.0, "opts": {}} for i in range(len(dbitems))}
        cat_survey_scores = {cc: [] for cc in cats_raw}
        total_sessions = 0

        for r in cur.fetchall():
            kc = r[0]
            if area_code:
                ba = branch_area.get(kc, {})
                if ba.get("area_code") != area_code:
                    continue
            if wilayah_code:
                ba = branch_area.get(kc, {})
                if ba.get("wilayah_code", "") != wilayah_code:
                    code = ba.get("area_code", "") + ">" + (ba.get("wilayah_code", "") or "")
                    if code != wilayah_code:
                        continue

            sd = r[1]
            total_sessions += 1

            # Per-item accumulation — status_data index = item index
            if sd:
                status_data = sd if isinstance(sd, list) else []
                for idx, s in enumerate(status_data):
                    if idx >= len(dbitems):
                        break
                    try:
                        sv = int(s.get("status") if isinstance(s, dict) else s)
                    except (ValueError, AttributeError):
                        continue
                    tc = dbitems[idx]["type"]
                    wm = opt_labels.get(tc, {}).get(sv, {}).get("weight_mult", 0.0)
                    ist[idx]["total"] += 1
                    ist[idx]["opts"][sv] = ist[idx]["opts"].get(sv, 0) + 1
                    ist[idx]["score_sum"] += wm

            # Per-category score per survey (weighted by item_weight)
            if sd:
                status_data = sd if isinstance(sd, list) else []
                for cc, citems in cat_items.items():
                    cat_sum = 0.0
                    cat_max = 0.0
                    for ci in citems:
                        idx = ci["idx"]
                        iw = ci["weight"]
                        cat_max += iw
                        if idx < len(status_data):
                            s = status_data[idx] if isinstance(status_data[idx], dict) else {}
                            try:
                                sv = int(s.get("status", -1))
                            except (ValueError, TypeError):
                                sv = -1
                        else:
                            sv = -1
                        if sv >= 0:
                            tc = dbitems[idx]["type"]
                            actual_wm = opt_labels.get(tc, {}).get(sv, {}).get("weight_mult", 0.0)
                            cat_sum += iw * actual_wm
                    cat_pct = round(cat_sum / cat_max * 100, 1) if cat_max > 0 else 0
                    cat_survey_scores[cc].append(cat_pct)

        # Build items response
        items = []
        for i in range(len(dbitems)):
            s = ist[i]
            item_score = round(s["score_sum"] / s["total"] * 100, 1) if s["total"] > 0 else 0
            item_opts = []
            tc = dbitems[i]["type"]
            for ov in sorted(s["opts"].keys()):
                ol = opt_labels.get(tc, {}).get(ov, {})
                item_opts.append({
                    "val": ov, "count": s["opts"][ov],
                    "label": ol.get("label", f"Nilai {ov}"),
                    "is_no": ol.get("is_no", False),
                })
            items.append({
                "idx": i, "cat": dbitems[i]["cat"],
                "label": dbitems[i]["label"],
                "weight": dbitems[i]["weight"],
                "avg_score": item_score,
                "opts": item_opts,
                "total_dinilai": s["total"],
            })

        # Per-category summary
        cat_summary = {}
        overall_wsum = 0.0
        overall_wscores = 0.0
        for cc in sorted(cat_items.keys()):
            scores = cat_survey_scores.get(cc, [])
            cat_avg = round(sum(scores) / len(scores), 1) if scores else 0
            cw = cats_raw.get(cc, {}).get("weight", 10)
            cat_summary[cc] = {
                "code": cc,
                "name": cats_raw.get(cc, {}).get("name", cc),
                "weight": cw,
                "avg_score": cat_avg,
                "count": len(scores),
            }
            overall_wsum += cw
            overall_wscores += cat_avg * cw
        overall_cat_scored = round(overall_wscores / overall_wsum, 1) if overall_wsum > 0 else 0

        # Best/worst items
        items_sorted = sorted(items, key=lambda x: x["avg_score"])
        merah = sum(1 for x in items if x["avg_score"] < 60)
        kuning = sum(1 for x in items if 60 <= x["avg_score"] < 80)
        hijau = sum(1 for x in items if x["avg_score"] >= 80)
        rata_all = round(sum(x["avg_score"] for x in items) / len(items), 1) if items else 0

        best_items = [x for x in items_sorted if x["avg_score"] >= 80][-5:] if items_sorted else []
        best_items.reverse()
        worst_items = [x for x in items_sorted if x["avg_score"] < 60][:5] if items_sorted else []
        if len(worst_items) < 5:
            worst_items = [x for x in items_sorted if x["avg_score"] < 80][:5]

        # Best/worst per category
        best_per_cat = {}
        worst_per_cat = {}
        for cc in cat_items:
            cc_items = [x for x in items_sorted if x["cat"] == cc]
            if cc_items:
                best_per_cat[cc] = cc_items[-3:] if cc_items else []
                best_per_cat[cc].reverse()
                worst_per_cat[cc] = [x for x in cc_items if x["avg_score"] < 80][:3] or cc_items[:3]

        cur.close(); conn.close()

        return JSONResponse({
            "ok": True,
            "items": items,
            "merah": merah, "kuning": kuning, "hijau": hijau,
            "rata_all": rata_all,
            "best_items": best_items,
            "worst_items": worst_items,
            "total_sessions": total_sessions,
            "filter": {"area_code": area_code, "wilayah_code": wilayah_code},
            "cat_summary": cat_summary,
            "overall_cat_scored": overall_cat_scored,
            "best_per_cat": best_per_cat,
            "worst_per_cat": worst_per_cat,
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
async def log_share_api(request: Request, session: Optional[str] = Cookie(None)):
    """Catat log siapa yg share report (via Web Share API)."""
    user = get_user_from_cookie(session)
    if not user:
        return JSONResponse({"ok": False, "error": "login_dulu"}, status_code=401)
    user_id = user.get("user_id", "?")
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=400)
    report_type = body.get("type", "")
    if report_type not in ("submitted", "ongoing", "belum"):
        return JSONResponse({"ok": False, "error": "invalid_type"}, status_code=400)
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO origo.report_share_log (user_id, report_type, user_agent, created_at) VALUES (%s, %s, %s, NOW())",
            (user_id, report_type, request.headers.get("user-agent", "")[:200]),
        )
        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:100]}, status_code=500)
    return JSONResponse({"ok": True})


@router.get("/survey/api/kantor-checklist/kantor-trend/{kantor_code}")
async def kantor_trend(request: Request, kantor_code: str, session: Optional[str] = Cookie(None)):
    """Ambil trend score per survey untuk sebuah kantor (Feature #4)."""
    user = get_user_from_cookie(session)
    if not user:
        return JSONResponse({"ok": False, "error": "Not logged in"}, status_code=401)
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute(
            """SELECT survey_seq, weighted_score, created_at
               FROM origo.kantor_checklist_data
               WHERE kantor_code = %s AND yes_count IS NOT NULL AND total_items > 0
               ORDER BY survey_seq ASC""",
            (kantor_code,)
        )
        scores = []
        for r in cur.fetchall():
            seq, ws_raw, ca = r
            ws = float(ws_raw) if ws_raw is not None else 0
            scores.append({
                "survey_seq": seq,
                "score": round(ws, 1),
                "date": str(ca)[:10] if ca else "-"
            })
        cur.close(); conn.close()
        # Jika weighted_score NULL, hitung manual
        if not scores:
            conn = get_db(); cur = conn.cursor()
            cur.execute(
                """SELECT survey_seq, yes_count, total_items, created_at
                   FROM origo.kantor_checklist_data
                   WHERE kantor_code = %s AND yes_count IS NOT NULL AND total_items > 0
                   ORDER BY survey_seq ASC""",
                (kantor_code,)
            )
            for r in cur.fetchall():
                seq, yes, tot, ca = r
                sc = round(float(yes) / float(tot) * 100, 1) if float(tot) > 0 else 0
                scores.append({
                    "survey_seq": seq,
                    "score": sc,
                    "date": str(ca)[:10] if ca else "-"
                })
            cur.close(); conn.close()
        return {"ok": True, "kantor_code": kantor_code, "scores": scores}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/survey/api/kantor-checklist/findings")
async def findings_api(request: Request, session: Optional[str] = Cookie(None),
                       q: str = Query(""), category: str = Query("")):
    """Return all notes from submitted surveys, filterable by kantor/search + category."""
    user = get_user_from_cookie(session)
    if not user:
        return JSONResponse({"ok": False, "error": "Not logged in"}, status_code=401)
    try:
        conn = get_db(); cur = conn.cursor()
        # Get items for label mapping
        dbi = _get_items_from_db()
        # Fetch all submitted surveys with status_data containing notes
        cur.execute("""
            SELECT kd.kantor_code, kd.pic, kd.updated_at, kd.status_data::text
            FROM origo.kantor_checklist_data kd
            WHERE kd.status_data::text LIKE '%note%'
              AND kd.workflow_status = 'submitted'
            ORDER BY kd.updated_at DESC
        """)
        findings = []
        for r_find in cur.fetchall():
            kc_find = r_find[0]
            pic_find = r_find[1] or ""
            ts_find = r_find[2]
            sd_text = r_find[3]
            if not sd_text:
                continue
            try:
                sd_arr = json.loads(sd_text)
            except:
                continue
            for idx, item_data in enumerate(sd_arr):
                if isinstance(item_data, dict) and item_data.get('note'):
                    note_text = item_data['note'].strip()
                    if not note_text:
                        continue
                    if q and q.lower() not in kc_find.lower():
                        continue
                    item_label = ""
                    if idx < len(dbi):
                        item_label = f"{dbi[idx].get('cat','')} - {dbi[idx].get('label','')}"
                    if category and category not in item_label:
                        continue
                    findings.append({
                        "kantor_code": kc_find,
                        "pic": pic_find,
                        "item_label": item_label,
                        "note": note_text,
                        "updated_at": str(ts_find)[:19] if ts_find else ""
                    })
        cur.close(); conn.close()
        return JSONResponse({"ok": True, "findings": findings})
    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({"ok": False, "error": str(e)[:200]}, status_code=500)


@router.get("/survey/api/serve-pdf/{kantor_code}")
async def serve_pdf_redirect(kantor_code: str):
    """Redirect ke public PDF endpoint - ganti link di dashboard"""
    return HTMLResponse(f"<script>window.location.href='/survey/api/public/pdf/{kantor_code}?dl=1';</script>")


@router.get("/survey/api/kantor-checklist/item-evidence")
async def item_evidence_api(request: Request):
    """
    Return daftar kantor yang memilih opsi tertentu untuk item tertentu.
    Query params: item_idx (int), opt_status (int, default 0)
    
    Digunakan untuk: waktu klik opsi "Tidak" di distribusi jawaban,
    muncul daftar kantor lengkap dengan foto, video, catatan, AI analysis.
    """
    if not get_user_from_cookie(request.cookies.get("session","")):
        return JSONResponse({"ok": False, "error": "Sesi login diperlukan"}, status_code=401)
    
    item_idx = request.query_params.get("item_idx")
    opt_status = request.query_params.get("opt_status", "4")
    
    if not item_idx:
        return JSONResponse({"ok": False, "error": "Parameter item_idx diperlukan"}, status_code=400)
    
    try:
        item_idx = int(item_idx)
        opt_status = int(opt_status)
    except ValueError:
        return JSONResponse({"ok": False, "error": "item_idx dan opt_status harus integer"}, status_code=400)
    
    import psycopg2
    conn = psycopg2.connect(
        dbname=os.getenv("PG_DB", "db_gabungan"),
        user=os.getenv("PG_USER", "postgres"),
        password=os.getenv("PG_PASS", "postgres"),
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", "5432"))
    )
    cur = conn.cursor()
    
    try:
        # Query kantor yang status_data[item_idx].status = opt_status
        query = """
            SELECT kd.kantor_code, ik.nama as kantor_nama,
                   kd.status_data, kd.tgl_cek, kd.pic, kd.nomor_survei, kd.submitted_at
            FROM origo.kantor_checklist_data kd
            LEFT JOIN i_kantor ik ON kd.kantor_code::int = ik.id
            WHERE kd.status_data IS NOT NULL
              AND kd.workflow_status IN ('submitted', 'reviewed', 'approved')
              AND kd.status_data::jsonb->>%s = %s
              AND kd.status_data::jsonb->%s IS NOT NULL
            ORDER BY kd.tgl_cek DESC
        """
        # Pendekatan: cari jsonb array element dengan item_idx tertentu
        # status_data is array, kita cari item yang statusnya = opt_status
        # Lebih aman: filter via Python
        cur.execute("""
            SELECT kd.id, kd.kantor_code, ntn.display_name as kantor_nama,
                   kd.status_data, kd.tgl_cek, kd.pic, kd.nomor_survei,
                   kd.submitted_at
            FROM origo.kantor_checklist_data kd
            LEFT JOIN (
                SELECT DISTINCT ON (node_code) node_code, display_name
                FROM origo.network_tree_node
                ORDER BY node_code, id
            ) ntn ON kd.kantor_code = ntn.node_code
            WHERE kd.status_data IS NOT NULL
              AND kd.workflow_status IN ('submitted', 'reviewed', 'approved')
            ORDER BY kd.tgl_cek DESC
        """)
        
        import json
        results = []
        for r in cur.fetchall():
            row_id, kantor_code, kantor_nama, sd_raw, tgl_cek, pic, nomor_survei, submitted_at = r
            
            if isinstance(sd_raw, str):
                sd = json.loads(sd_raw)
            else:
                sd = sd_raw
            
            if not isinstance(sd, (list, tuple)):
                continue
            
            if item_idx >= len(sd):
                continue
            
            item_data = sd[item_idx]
            if not isinstance(item_data, dict):
                continue
            
            item_status = item_data.get("status")
            # status bisa int atau string
            try:
                item_status = int(item_status) if item_status not in (None, "") else None
            except (ValueError, TypeError):
                item_status = None
            
            if item_status != opt_status:
                continue
            
            # Get AI analysis
            cur2 = conn.cursor()
            cur2.execute(
                """SELECT saran, relevan, model, created_at FROM origo.survey_ai_usage
                   WHERE kantor_code = %s AND item_idx = %s
                   ORDER BY created_at DESC LIMIT 1""",
                (kantor_code, item_idx)
            )
            ai_row = cur2.fetchone()
            cur2.close()
            
            ai_info = {}
            if ai_row:
                ai_info = {
                    "saran": ai_row[0] or "",
                    "relevan": ai_row[1] if ai_row[1] is not None else True,
                    "model": ai_row[2] or ""
                }
            
            results.append({
                "kantor_code": str(kantor_code),
                "kantor_nama": kantor_nama or "",
                "foto": item_data.get("foto", ""),
                "video_path": item_data.get("video_path", ""),
                "note": item_data.get("note", ""),
                "pic": str(pic or ""),
                "tgl_cek": str(tgl_cek or ""),
                "nomor_survei": nomor_survei or "",
                "ai": ai_info
            })
        
        return JSONResponse({
            "ok": True,
            "item_idx": item_idx,
            "opt_status": opt_status,
            "total": len(results),
            "evidence": results
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
    finally:
        cur.close()
        conn.close()
