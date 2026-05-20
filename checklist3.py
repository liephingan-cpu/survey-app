"""
checklist.py — Kantor Checklist routes. FastAPI.
Form 100% server-side render — NO JS dependency buat nampilin form.
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

# ── Gemini Analisa Gambar ──
import base64
import httpx

_ANALISA_GEMINI_MODEL = "gemini-2.5-flash"
_ANALISA_GEMINI_KEY = os.getenv("GEMINI_ANALISA_KEY", "")

def analisa_foto_gemini(img_bytes: bytes, item_label: str, item_cat: str) -> dict:
    """
    Panggil Gemini API untuk analisa apakah foto relevan dengan item survey.
    Return {"deskripsi": str, "relevan": bool, "saran": str}
    """
    if not _ANALISA_GEMINI_KEY:
        return {"deskripsi": "(API key tidak tersedia)", "relevan": True, "saran": ""}
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{_ANALISA_GEMINI_MODEL}:generateContent?key={_ANALISA_GEMINI_KEY}"
    img_b64 = base64.b64encode(img_bytes).decode()
    
    prompt = f"""\
Foto ini adalah dokumentasi survey kantor untuk item: [{item_cat}] {item_label}

Analisa apakah foto ini relevan dengan item tersebut.
Jawab dalam JSON (hanya JSON, tanpa markdown):
{{
  "deskripsi": "deskripsi singkat apa yang terlihat (1 kalimat, Bahasa Indonesia)",
  "relevan": true,
  "saran": ""
}}
"""
    
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
            ]
        }]
    }
    
    try:
        r = httpx.post(url, json=payload, timeout=20)
        if r.status_code == 200:
            raw = r.json()['candidates'][0]['content']['parts'][0]['text']
            # Bersihkan markdown code fence kalo ada
            raw = raw.strip()
            if raw.startswith('```'):
                raw = raw.split('\n', 1)[-1]
                raw = raw.rsplit('\n```', 1)[0] if '\n```' in raw else raw.replace('```json','').replace('```','').strip()
            result = json.loads(raw)
            return {
                "deskripsi": result.get("deskripsi", "(deskripsi tidak tersedia)"),
                "relevan": bool(result.get("relevan", True)),
                "saran": result.get("saran", "")
            }
        else:
            return {"deskripsi": f"(error API: {r.status_code})", "relevan": True, "saran": ""}
    except Exception as e:
        return {"deskripsi": f"(error: {str(e)[:50]})", "relevan": True, "saran": ""}


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
    """Semua data master dalam 1 response — kategori, item, options."""
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
        # Ambil lock timestamp juga — SEBELUM cur.close()
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
                lock_age = now - lock["updated_at"].replace(tzinfo=timezone.utc) if lock["updated_at"].tzinfo else now - lock["updated_at"]
                if lock_age > lock_timeout:
                    # Lock expired — treat sebagai available, bukan conflict
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

    # Lock timeout — draft expired setelah 30 menit inactivity
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
        if items_raw is not None and status_data == '[]':
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
                    status_data.append({"status": sv, "note": val.get('note', ''), "foto": val.get('foto', '')})
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
            policy = dbitems[i].get("wajib_foto_policy", "rusak_only")
            try: sv = int(s.get("status", "99"))
            except: sv = 99
            needs_photo = False
            if policy == "ada_rusak" and sv <= 1:
                needs_photo = True
            elif policy == "rusak_only" and sv > 0:
                needs_photo = True
            if needs_photo:
                key = str(i)
                if key not in photo_data or not photo_data[key]:
                    return JSONResponse(
                        {"ok": False, "error": f"Item #{i} ('{dbitems[i].get('label','')}') — butuh foto!"},
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
                   updated_at=NOW(),
                   submitted_at=(CASE WHEN %s='submitted' THEN NOW() ELSE NULL END)
                   WHERE id=%s RETURNING id""",
                (pic, tgl_cek, json.dumps(status_data), workflow_status,
                 yes_count, no_count, total_items,
                 workflow_status, draft_row[0])
            )
        else:
            # Insert baru
            cur.execute(
                """INSERT INTO origo.kantor_checklist_data
                   (kantor_code, pic, tgl_cek, status_data, workflow_status,
                    yes_count, no_count, total_items, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s, NOW())
                   RETURNING id""",
                (kantor_code, pic, tgl_cek, json.dumps(status_data), workflow_status,
                 yes_count, no_count, total_items),
            )
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return {"ok": True, "id": row[0] if row else None}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

# ── Dashboard ──
# Fungsi helper — ambil items dari DB


def _get_cat_names():
    """Ambil kategori dari DB"""
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT code, label FROM origo.survey_categories WHERE is_active = true ORDER BY sort_order")
        d = dict(cur.fetchall())
        cur.close(); conn.close()
        return d
    except:
        return {"A":"Lokasi & Akses","B":"Identitas & Visibilitas","C":"Ruang Konsumen","D":"Fasilitas Karyawan","E":"Alat Kerja","F":"Keamanan & Barang Sitaan","G":"Dokumen & Regulasi"}


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
            SELECT i.item_idx, c.cat_code, i.label, i.tip, t.type_code, i.weight, i.wajib_foto_policy, i.helper, i.options_json
            FROM origo.survey_checklist_items i
            JOIN origo.survey_categories c ON i.cat_id = c.id
            JOIN origo.survey_question_types t ON i.type_id = t.id
            WHERE i.is_active = true
            ORDER BY i.item_idx
        """)
        items = []
        for r in cur.fetchall():
            type_code = r[4]
            per_item_opts = r[8] if r[8] else None  # options_json — custom per-item labels
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
                    # Find matching base for weight_mult
                    wm = 1.0
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
                "options_json": r[8], "options": item_opts
            })
        cur.close(); conn.close()
        return items
    except Exception as e:
        import traceback; traceback.print_exc()
        return []

_ITEMS = _get_items_from_db()

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
        cur.execute("SELECT office_code, office_name FROM origo.network_branch_monitoring_master WHERE branch_type NOT IN ('area','wilayah') AND office_code ~ '^[1-9][0-9]{4}$' ORDER BY office_name")
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
        done_main = len(main_scores)
        cur.close(); conn.close()

        for k, n in branches.items():
            m = main_scores.get(k)
            merged.append({"kode": k, "label": n, "main": m["score"] if m else None, "main_pic": m["pic"] if m else None, "main_durasi": m["diu"] if m else None, "main_tgl": m["tgl"] if m else None, "main_workflow": m["workflow"] if m else None})

        scored = [x for x in merged if x["main"] is not None]
        ss = sorted(scored, key=lambda x: x["main"], reverse=True)
        top5 = ss[:5]; worst5 = list(reversed(ss))[:5]

        # Problem items
        dbitems_ic = _get_items_from_db()
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT status_data FROM origo.kantor_checklist_data")
        ic = {}; twd = 0
        for (sd,) in cur.fetchall():
            if not sd: continue
            twd += 1
            for i, s in enumerate(sd):
                if i >= len(dbitems_ic): break
                st = s.get("status","") if isinstance(s,dict) else s
                try:
                    sv = int(st)
                    if sv >= 1: ic[i] = ic.get(i,0)+1
                except: pass
        cur.close(); conn.close()
        problem_items = [{"cat": dbitems_ic[i]["cat"], "label": dbitems_ic[i]["label"], "no_count": c, "total": twd} for i,c in sorted(ic.items(), key=lambda x:-x[1]) if i < len(dbitems_ic)]

        # Best/worst by yes ratio
        conn = get_db(); cur = conn.cursor()
        cur.execute("""SELECT status_data
            FROM origo.kantor_checklist_data 
            WHERE status_data IS NOT NULL AND jsonb_array_length(status_data) > 0""")
        dbw = _get_items_from_db()
        istat = {i: {"y":0,"t":0} for i in range(len(dbw))}
        for (sd,) in cur.fetchall():
            if not sd: continue
            for i, s in enumerate(sd):
                if i >= len(dbw): break
                st = s.get("status","") if isinstance(s,dict) else s
                istat[i]["t"] += 1
                if isinstance(st,int): sv=int(st)
                else:
                    try: sv = int(st)
                    except: sv=-1
                if sv == 0: istat[i]["y"] += 1
        cur.close(); conn.close()
        # Threshold dinamis = max_score / 2
        ir_all = [{"idx":i,"cat":dbw[i]["cat"],"label":dbw[i]["label"],"yes_pct":round(istat[i]["y"]/istat[i]["t"]*100,1) if istat[i]["t"]>0 else 0} for i in range(len(dbw))]
        max_pct = max(x["yes_pct"] for x in ir_all) if ir_all else 0
        threshold = max_pct / 2
        ir_best = sorted([x for x in ir_all if x["yes_pct"] >= threshold], key=lambda x:-x["yes_pct"])
        ir_worst = sorted([x for x in ir_all if x["yes_pct"] < threshold], key=lambda x:x["yes_pct"])
        best_items = ir_best[:5]
        worst_items = ir_worst[:5]

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

    # Semua session — termasuk yang kantornya bukan cabang (area, wilayah, dll)
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

    ctl = _get_cat_names()

    return TemplateResponse("survey_dashboard.html", {"request": request, "user_id": user["user_id"], "user_name": user["fullname"], "fullname": user["fullname"], "fullname": user["fullname"], "user_role": user.get("role",""), "current_path": "/survey/kantor-checklist/dashboard", "total_branches": total_branches, "done_main": done_main, "done_mt": done_mt, "merged": merged, "top5": top5, "worst5": worst5, "problem_items": problem_items, "best_items": best_items, "worst_items": worst_items, "terbaru": latest, "merged_with_score": mws, "scores_list": sl, "draft_list": dr, "avg_dur": avg_dur, "avg_main": avg_main, "k": ctl, "v": ctl, "cat_names": ctl, "all_sessions": all_sessions, "menu_items": _get_menu()})

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
            for di_idx in range(50):
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
            
        # Ambil weight_mult per option dari DB
        cur2 = conn.cursor()
        cur2.execute("""
            SELECT t.type_code, o.opt_value::int, o.weight_mult
            FROM origo.survey_question_types t
            JOIN origo.survey_type_options o ON t.id = o.type_id
        """)
        wm_map = {}
        for tc, ov, wm in cur2.fetchall():
            wm_map.setdefault(tc, {})[ov] = float(wm)
        cur2.close()

        # Ambil categories + bobot
        cur2 = conn.cursor()
        cur2.execute("SELECT cat_code, cat_name, cat_weight FROM origo.survey_categories")
        cats_data = {r[0]: {"name": r[1], "weight": float(r[2])} for r in cur2.fetchall()}
        cur2.close()

        ist = {i: {"yes":0,"no":0,"rusak":0,"total":0, "score_sum": 0.0} for i in range(len(dbitems))}
        for st in all_status:
            try: sv = int(st)
            except: continue
            for i in range(len(dbitems)):
                tc = dbitems[i]["type"]
                wm = wm_map.get(tc, {}).get(sv, 0.0)
                ist[i]["total"] += 1
                if sv == 0:
                    ist[i]["yes"] += 1
                elif sv == 1:
                    ist[i]["rusak"] += 1
                else:
                    ist[i]["no"] += 1
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

            if ist[i]["total"] > 0:
                avg_raw = s["score_sum"] / ist[i]["total"]
                weighted = avg_raw * item_w * cat_w * 100
            else:
                avg_raw = 0
                weighted = 0

            detail.append({
                "idx": i, "cat": cat_c,
                "label": dbitems[i]["label"],
                "weight": item_w,
                "avg_score": round(weighted, 1),
                "layak": s["yes"],
                "tidak_ada": s["no"],
                "rusak": s["rusak"],
                "total_dinilai": ist[i]["total"]
            })
            cat_scores[cat_c]["score"] += weighted
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
        cur.execute("SELECT kantor_code, pic, tgl_cek, yes_count, total_items, no_count, created_at, updated_at, workflow_status, submitted_at, updated_by FROM origo.kantor_checklist_data ORDER BY updated_at DESC LIMIT %s", (limit,))
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
            # Ada draft — redirect ke form yang udah ada
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
        
        blank_items = [{"status":"", "note":"", "foto":""} for _ in range(50)]
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
            blank_items = [{"status":"", "note":"", "foto":""} for _ in range(50)]
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
            status_data = sd if sd else [{"status":"", "note":"", "foto":""} for _ in range(50)]
        
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
        skor = round(yes / tot * 100, 1) if tot and tot > 0 else 0

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

            cat_code = di['cat_code']
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

        # ── Halaman 1: SUMMARY ──
        cat_rows_summary = []
        for ck in sorted(cat_data.keys()):
            cd = cat_data[ck]
            cpct = round(cd["baik"] / cd["total"] * 100, 1) if cd["total"] > 0 else 0
            ccol = "#16a34a" if cpct >= 70 else "#d97706" if cpct >= 40 else "#dc2626"
            cat_rows_summary.append(
                f"<tr><td>{cd['label']}</td><td style='text-align:center'>{cd['total']}</td>"
                f"<td style='text-align:center;color:#16a34a'>{cd['baik']}/{cd['total']}</td>"
                f"<td style='text-align:center;color:#dc2626'>{cd['rusak']}/{cd['total']}</td>"
                f"<td style='text-align:center'><span style='display:inline-block;padding:1px 6px;border-radius:3px;font-weight:bold;color:white;background:{ccol};font-size:8pt;'>{cpct}%</span></td></tr>"
            )

        html_parts = [f'''<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Hasil Survei {kode}</title>
<style>
  @page {{ size:A4; margin:14mm 10mm; }}
  body {{ font-family:'DejaVu Sans',sans-serif; font-size:9pt; color:#111; }}
  h1 {{ font-size:14pt; text-align:center; margin:0 0 4px 0; }}
  h2 {{ font-size:10pt; text-align:center; margin:0 0 8px 0; color:#666; }}
  h3 {{ font-size:10pt; margin:12px 0 6px 0; border-bottom:1px solid #ccc; padding-bottom:3px; }}
  table {{ width:100%; border-collapse:collapse; margin:6px 0; }}
  th, td {{ border:1px solid #555; padding:3px 5px; text-align:left; font-size:7.5pt; }}
  th {{ background:#e5e7eb; font-weight:bold; text-align:center; font-size:7pt; }}
  .meta {{ margin:4px 0; font-size:8pt; line-height:1.6; }}
  .meta span {{ margin-right:14px; }}
  .skor-main {{ text-align:center; padding:14px 0; }}
  .skor-circle {{ display:inline-block; width:70px; height:70px; line-height:70px; border-radius:50%; font-size:20pt; font-weight:bold; color:white; text-align:center; background:{skor_color}; }}
  .footer {{ margin-top:10px; font-size:6.5pt; color:#999; text-align:center; }}
  .page-break {{ page-break-before:always; }}
  .img-full {{ max-width:160px; max-height:160px; object-fit:contain; border:1px solid #ccc; border-radius:4px; margin:3px; }}
  .lamp-grid {{ display:flex; flex-wrap:wrap; gap:6px; }}
  .lamp-item {{ width:175px; border:1px solid #ddd; border-radius:5px; padding:6px; margin:3px; display:inline-block; vertical-align:top; }}
  .lamp-item img {{ width:100%; height:130px; object-fit:cover; border-radius:3px; }}
  .lamp-item .lamp-label {{ font-size:7pt; color:#333; }}
  .lamp-item .lamp-desc {{ font-size:6.5pt; color:#666; }}
  .lamp-item .lamp-geo {{ font-size:6pt; color:#888; }}
</style></head><body>

''']

        # ══════════════  PAGE 1 : SUMMARY  ══════════════
        html_parts.append(f'''
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

<h3>Skor per Kategori</h3>
<table>
<thead><tr><th>Kategori</th><th style="width:40px">Total</th><th style="width:50px">Baik</th><th style="width:50px">Rusak</th><th style="width:45px">Skor</th></tr></thead>
<tbody>
{"" . join(cat_rows_summary)}
</tbody>
</table>
''')

        # Best / Worst
        baik_items = [(i,it) for i,it in enumerate(items) if i < len(db_items) and isinstance(it,dict) and str(it.get("status","")).isdigit() and int(it.get("status","99")) == 0]
        rusak_items = [(i,it) for i,it in enumerate(items) if i < len(db_items) and isinstance(it,dict) and str(it.get("status","")).isdigit() and int(it.get("status","99")) > 0]
        baik_items = baik_items[:5]
        rusak_items = rusak_items[:5]

        html_parts.append('<h3>Top 5 Terbaik</h3><table><thead><tr><th style="width:22px">#</th><th>Item</th><th style="width:35px">Status</th></tr></thead><tbody>')
        for ii, it in baik_items:
            di = db_items[ii]
            st = int(it.get("status","0"))
            html_parts.append(f'<tr><td style="text-align:center">{ii+1}</td><td>{di["cat"]} — {di["label"]}</td><td style="text-align:center">{vlbl.get(st,"-")}</td></tr>')
        if not baik_items:
            html_parts.append('<tr><td colspan="3" style="text-align:center;color:#999">Tidak ada item dengan status baik</td></tr>')
        html_parts.append('</tbody></table>')

        html_parts.append('<h3>Top 5 Terburuk</h3><table><thead><tr><th style="width:22px">#</th><th>Item</th><th style="width:35px">Status</th></tr></thead><tbody>')
        for ii, it in rusak_items[:5]:
            di = db_items[ii]
            st = int(it.get("status","0"))
            html_parts.append(f'<tr><td style="text-align:center">{ii+1}</td><td>{di["cat"]} — {di["label"]}</td><td style="text-align:center">{vlbl.get(st,"-")}</td></tr>')
        if not rusak_items:
            html_parts.append('<tr><td colspan="3" style="text-align:center;color:#999">Semua item baik</td></tr>')
        html_parts.append('</tbody></table>')

        # ══════════════  PAGE 2 : DETAIL PER KATEGORI  ══════════════
        html_parts.append('<div class="page-break"></div>')
        html_parts.append('<h1 style="font-size:13pt">Detail Pemeriksaan per Kategori</h1>')

        for ck in sorted(cat_data.keys()):
            cd = cat_data[ck]
            cpct = round(cd["baik"] / cd["total"] * 100, 1) if cd["total"] > 0 else 0
            html_parts.append(f'<h3>{cd["label"]} — {cpct}%</h3>')
            html_parts.append('<table><thead><tr><th style="width:18px">#</th><th>Pernyataan</th><th style="width:45px">Status</th><th style="width:48px">Foto</th><th style="width:80px">Deskripsi</th><th style="width:45px">Catatan</th></tr></thead><tbody>')
            for ci in cd["items"]:
                img_td = '<td style="text-align:center">-</td>'
                if ci["foto_path"] and ci["foto_path"].startswith("/survey/uploads/"):
                    fname = ci["foto_path"].replace("/survey/uploads/", "")
                    fpath = os.path.join(PHOTO_DIR, fname)
                    if os.path.exists(fpath):
                        try:
                            with open(fpath, "rb") as fimg:
                                b64i = b64encode(fimg.read()).decode()
                            img_td = f'<td style="text-align:center"><img src="data:image/jpeg;base64,{b64i}" style="width:42px;height:42px;object-fit:cover;border-radius:3px;"></td>'
                        except: pass
                rel_tag = ""
                if ci["foto_desc"]:
                    rel_tag = '<br><span style="color:#dc2626;font-size:6pt;">Foto mungkin tdk sesuai</span>' if ci["foto_relevan"] == False else '<br><span style="color:#16a34a;font-size:6pt;">Foto sesuai</span>'
                desc_td = f'<td style="font-size:6.5pt;color:#555">{ci["foto_desc"][:60] if ci["foto_desc"] else "-"}{rel_tag}</td>'
                html_parts.append(
                    f'<tr><td style="text-align:center">{ci["num"]}</td><td>{ci["label"][:45]}</td>'
                    f'<td style="text-align:center;font-size:7pt">{ci["status"]}</td>'
                    f'{img_td}{desc_td}<td style="font-size:6.5pt;color:#888">{ci["note"][:30] if ci["note"] else "-"}</td></tr>'
                )
            html_parts.append('</tbody></table>')

        # ══════════════  PAGE 3 : LAMPIRAN FOTO  ══════════════
        if lampiran_foto:
            html_parts.append('<div class="page-break"></div>')
            html_parts.append('<h1>Lampiran Foto</h1>')
            html_parts.append('<div class="lamp-grid">')
            for lf in lampiran_foto:
                geo_str = f'<div class="lamp-geo">{lf["geo"]}</div>' if lf["geo"] else ""
                rel_str = '<span style="color:#dc2626;font-size:6.5pt;">Foto mungkin tdk sesuai</span>' if lf["relevan"] == False else '<span style="color:#16a34a;font-size:6.5pt;">Foto sesuai</span>'
                rel_str = f'<br>{rel_str}' if lf["desc"] else rel_str
                desc_str = f'<div class="lamp-desc">{lf["desc"][:80]}{"..." if len(lf["desc"])>80 else ""}</div>' if lf["desc"] else ""
                html_parts.append(f'''
<div class="lamp-item">
  <img src="data:image/jpeg;base64,{lf["b64"]}">
  <div class="lamp-label"><strong>{lf["cat"]}</strong> — {lf["item"]}</div>
  {desc_str}
  <div>{rel_str}</div>
  {geo_str}
</div>''')
            html_parts.append('</div>')

        html_parts.append(f'''
<div class="footer">Dicetak: {dtdt.now().strftime("%d-%m-%Y %H:%M")} WIB | Origo Survey System</div>
</body></html>''')

        html = "\n".join(html_parts)

        if dl:
            PDF_DIR = "/home/bhc0104/survey_app/pdfs"
            os.makedirs(PDF_DIR, exist_ok=True)
            pdf_fname = f"survei_{kode}_{nomor or 'unknown'}.pdf".replace("/","_").replace(" ","_")
            pdf_fpath = os.path.join(PDF_DIR, pdf_fname)

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
                headers={"Content-Disposition": f'attachment; filename="{pdf_fname}"'})

        return HTMLResponse(html)        import traceback; traceback.print_exc()
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
        img = Image.open(io.BytesIO(contents))

        # ── Optimasi ukuran: resize max 1600px di sisi terpanjang ──
        max_dim = 1600
        if img.width > max_dim or img.height > max_dim:
            ratio = max_dim / max(img.width, img.height)
            new_w = int(img.width * ratio)
            new_h = int(img.height * ratio)
            img = img.resize((new_w, new_h), Image.LANCZOS)

        # ── Gemini: analisa foto ──
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
        # Tapi kita pake version yg udah diresize — cukup
        img_bytes_for_ai = io.BytesIO()
        img.save(img_bytes_for_ai, "JPEG", quality=85)
        img_bytes_for_ai = img_bytes_for_ai.getvalue()

        analisa = analisa_foto_gemini(img_bytes_for_ai, item_label, item_cat)
        foto_desc = analisa.get("deskripsi", "")
        relevan = analisa.get("relevan", True)
        saran = analisa.get("saran", "")

        # ── Hardstamp: user, kode pernyataan, timestamp, geo ──
        draw = ImageDraw.Draw(img, "RGBA")
        user_name = user.get("fullname", "")
        geo_str = form.get("geo", "")
        if geo_str:
            stamp_text = f"{now.strftime('%d %b %Y %H:%M')} WIB\n{item_cat}.{idx} | {user_name}\n{geo_str}"
        else:
            stamp_text = f"{now.strftime('%d %b %Y %H:%M')} WIB\n{item_cat}.{idx} | {user_name}"

        # Cari font — fallback ke default
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
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
        img.save(filepath, "JPEG", quality=85, optimize=True)

        filesize = os.path.getsize(filepath)
        foto_path = f"/survey/uploads/{filename}"

        # ── Simpan deskripsi foto ke session data ──
        try:
            conn2 = get_db()
            cur2 = conn2.cursor()
            cur2.execute(
                "SELECT status_data FROM origo.kantor_checklist_data WHERE kantor_code = %s AND workflow_status = 'draft'",
                (kantor_code,)
            )
            r2 = cur2.fetchone()
            if r2:
                sd = r2[0] if r2[0] else [{"status":"", "note":"", "foto":""} for _ in range(50)]
                while len(sd) <= idx:
                    sd.append({"status":"", "note":"", "foto":""})
                if isinstance(sd[idx], dict):
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
            pass  # Gagal simpan deskripsi — bukan fatal

        return {
            "ok": True,
            "foto_path": foto_path,
            "filename": filename,
            "filesize": filesize,
            "foto_desc": foto_desc,
            "foto_relevan": relevan,
            "foto_saran": saran
        }
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
        # Hanya hapus file di sistem — path di DB bakal ditimpa pas auto-save atau submit
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
