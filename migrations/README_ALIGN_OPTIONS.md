# Migration 001: Align Pernyataan ↔ Pilihan Status

**Tanggal:** 2026-05-18
**File:** `migrations/001_align_options_20260518.sql`

## Masalah
Setiap pernyataan di form survey cuma punya pilihan status generik:
✅ Ya / ❌ Tidak / 🔧 Rusak / ⚠️ G1 / ➖ N/A

Pilihan ini tidak nyambung dengan pernyataan spesifik. Contoh:
- Pernyataan parkir: "Tersedia area parkir untuk 1 mobil dan 3 motor"
- Pilihan: ❌ Tidak — tidak nyambung dengan konteks parkir
- Harusnya: ✅ Tersedia — > 1 mobil + >3 motor / ✅ Tersedia — 1 mobil + 3 motor / dll

## Yang Diubah

### 1. DB Migration (`001_align_options_20260518.sql`)
- **Tambah kolom** `description` dan `score_weights` ke `origo.survey_question_types`
- **Update option labels** di `origo.survey_type_options` jadi deskriptif (nyambung pernyataan)
- **Tambah kolom** `label_short` dan `css_class` ke `origo.survey_type_options` untuk compact view

### 2. Python (`checklist.py`)
- **`_get_items_from_db()`** — sekarang return `options` per item (termasuk per-item custom dari `options_json`)
- **Tambah fungsi baru** `_get_type_options_map()` — return mapping type_code → list option dicts
- **`form()` route** — pass `type_options` ke template
- **`api_submit()`** — support JSON body (selain form-encoded)
- **Fix master-data API** — index out of range bug pada kolom `wajib_catatan`

### 3. Template (`survey_form.html`)
- **Hapus hardcoded** `status_opts` (✅ Ya / ❌ Tidak / 🔧 Rusak / ⚠️ G1 / ➖ N/A)
- **Render per-item options** dari `it.options` (data dari DB)
- **CSS class** berdasarkan score: `score-0` hijau, `score-1` kuning, `score-2` oranye, `score-3` merah, `score-4` abu
- **Hapus `renderOptions()` JS** — tidak perlu lagi karena options sudah server-side render
- **Hapus `typeOptions` variable JS** — data tidak perlu hardcoded di client
- **Auto-save** — panggil autoSave saat status di-toggle

## Scoring System
```
Score | Makna           | Warna   | Weight Mult
0     | Terbaik (penuh) | Hijau   | 1.00
1     | Minor deviation | Kuning  | 0.75/0.60/0.50
2     | Mayor deviation | Oranye  | 0.50/0.20/0.00
3     | Kritis          | Merah   | 0.25
4     | Tidak ada       | Abu     | 0.00
```

## Question Types & Options
| Type Code     | Options Count | Contoh Item                          |
|---------------|---------------|--------------------------------------|
| yesno         | 3             | Internet, Printer, AC                |
| binary        | 2             | Toilet karyawan, Brankas             |
| condition     | 3             | Penerangan, Fasade, Air bersih       |
| parkir        | 5             | Parkir (1 mobil + 3 motor)           |
| tinggi_jalan  | 3             | Posisi lantai vs jalan               |
| ukuran_ruang  | 3             | Ukuran ruangan min 3x4m              |
| listrik_daya  | 3             | Daya listrik terpasang               |
| ada_tidak     | 2             | Ada/Tidak polos                      |

## Backup
Semua data di-backup ke: `backup_before_migration_20260518.sql`
