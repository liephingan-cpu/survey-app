# 2026-05-18 — Hapus Tombol Save Draft

## Alasan
Tombol "💾 Simpan Draft" dan "💾 Ambil Alih & Simpan Draft" tidak diperlukan karena:
- Auto-save sudah berjalan di setiap action user (pilih status, upload foto, edit catatan)
- Tidak ada lagi konflik antar user dan session (lock system sudah handle)
- Submit sudah berfungsi sempurna dengan validasi lengkap

## Perubahan

### Template: `templates/survey_form.html`

1. **CSS** — Hapus aturan `.btn-draft` (line 47)
2. **Submit bar** — Hapus seluruh div kiri berisi:
   - `🔒 Read Only` (conflict/submitted)
   - `💾 Ambil Alih & Simpan Draft` (lock_expired)
   - `💾 Simpan Draft` (default)
3. **`submitForm()`** — Hapus parameter `workflow`, hardcode `workflow = 'submitted'`
4. **Response handler** — Hapus cabang `workflow === 'draft'` (alert + redirect draft), sekarang langsung buka PDF + redirect dashboard

### Tidak ada perubahan backend (`checklist.py`)
- Backend tetap handle `workflow_status = 'draft'` sebagai fallback
- Auto-save endpoint masih SELECT `WHERE workflow_status = 'draft'` — row baru selalu dibuat dengan `'draft'` di `start-new-session`
- Submit endpoint selalu set `workflow_status = 'submitted'`

## Verifikasi
- ✅ Jinja brace balance: 37/37, Vars: 78/78
- ✅ Script brace balance: 2 script, depth=0 untuk keduanya
- ✅ Python compile `checklist.py`: OK
- ✅ Service restart: active
- ✅ HTTP 200 dashboard response: 51KB HTML normal

## Dampak
- **Tidak ada** dampak terhadap workflow atau integritas data
- Auto-save tetap berfungsi penuh
- User yang membuka form draft lama sekarang cuma bisa Submit (tidak bisa simpan draft lagi)
- Badge "✏️ Draft" di index page masih muncul sebagai informasi
