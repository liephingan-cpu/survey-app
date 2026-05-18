# Survey Kondisi Kantor — Origo

App survey kondisi fisik kantor cabang. Server-side render FastAPI + Jinja2 + PostgreSQL.

## Stack
- **Framework:** FastAPI (Jinja2 templates)
- **Auth:** JWT cookie-based
- **DB:** PostgreSQL (db_gabungan, schema: origo)
- **PDF:** WeasyPrint
- **AI:** Gemini 2.5 Flash (analisa foto)
- **Foto:** Upload server → resize 1600px → hardstamp → simpan di `/uploads/`

## Features
- 46 item checklist per kategori (A-G)
- Scoring 0-4 (weighted)
- Auto-save per action
- Foto dokumentasi + analisa Gemini (relevansi)
- Video dokumentasi (kompresi FFmpeg)
- Geotagging
- PDF laporan 3 halaman (Summary, Detail, Lampiran)
- Dashboard per item & per cabang
- Best/worst top 5

## Struktur
```
survey_app/
├── checklist.py        # Main router + semua endpoint
├── auth.py             # JWT auth helper
├── main.py             # FastAPI app entry
├── templates/          # Jinja2 templates
├── uploads/            # Foto/video uploads
├── pdfs/               # Generated PDF files
├── migrations/         # SQL migration files
├── docs/               # Dokumentasi perubahan
└── venv/               # Python virtual env
```

## Service
```bash
sudo systemctl restart survey-origo.service
```
Port 5000 → Cloudflare Tunnel → `survey.origo.my.id`
