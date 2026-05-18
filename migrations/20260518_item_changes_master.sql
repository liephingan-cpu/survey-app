-- ============================================================
-- MIGRATION: 20260518 — Item Changes Master
-- ============================================================
-- Berisi:
--   1. Update pilihan status per item (type_id diganti jika perlu)
--   2. Update label / nama item
--   3. Penghapusan item (soft delete is_active=false)
--   4. Penambahan item baru
--   5. Update wajib_foto_policy dinamis
--   6. Update helper_foto (jsonb)
--
-- Jenis-jenis (type_id):
--   1 = yesno  (✅ Ya — ⚠️ Rusak — ❌ Tidak)
--   2 = binary (✅ Ada — ❌ Tidak)
--   3 = condition (✅ Layak — ⚠️ Rusak — ❌ Tidak Ada)
--   8 = ada_tidak (✅ Tersedia — ❌ Tidak tersedia)
--
-- Policy:
--   'buktikan' = wajib foto untuk SEMUA
--   'bermasalah' = wajib foto jika score>0 (Rusak/Tidak)
--   'tanpa' = tidak perlu foto
--   'ada_berfungsi' = wajib foto jika score=0 (Ada/Berfungsi)
-- ============================================================

BEGIN;

-- ===========================
-- B.3 Jam operasional terpampang (ID=59)
-- Kalau 'Tidak Terpampang' → tanpa dokumentasi
-- Sekarang policy='bermasalah' → ganti jadi 'tanpa' saja karena tidak relevan difoto
-- ===========================
UPDATE origo.survey_checklist_items
SET wajib_foto_policy = 'tanpa'
WHERE id = 59;

-- ===========================
-- B.4 Umbul-umbul/banner (ID=60)
-- Kalau 'Tidak Ada' → tanpa dokumentasi
-- ===========================
UPDATE origo.survey_checklist_items
SET wajib_foto_policy = 'tanpa'
WHERE id = 60;

-- ===========================
-- C.1 Air bersih (ID=61)
-- Kalau 'Tidak Ada' → tanpa dokumentasi
-- ===========================
UPDATE origo.survey_checklist_items
SET wajib_foto_policy = 'tanpa'
WHERE id = 61;

-- ===========================
-- C.2 Toilet (ID=62)
-- Kalau 'Tidak Ada' → tanpa dokumentasi
-- ===========================
UPDATE origo.survey_checklist_items
SET wajib_foto_policy = 'tanpa'
WHERE id = 62;

-- ===========================
-- C.3 AC/kipas angin (ID=63)
-- Kalau 'Tidak - Tidak Tersedia' → tanpa dokumentasi
-- ===========================
UPDATE origo.survey_checklist_items
SET wajib_foto_policy = 'tanpa'
WHERE id = 63;

-- ===========================
-- C.6 Meja kerja kasir (ID=66)
-- Kalau 'Tidak Ada' → tanpa dokumentasi
-- ===========================
UPDATE origo.survey_checklist_items
SET wajib_foto_policy = 'tanpa'
WHERE id = 66;

-- ===========================
-- C.7 Meja kerja marketing (ID=67)
-- Kalau 'Tidak Ada' → tanpa dokumentasi
-- ===========================
UPDATE origo.survey_checklist_items
SET wajib_foto_policy = 'tanpa'
WHERE id = 67;

-- ===========================
-- C.11 Dispenser air minum (ID=71)
-- Kalau 'Tidak - Tidak Tersedia' → tanpa dokumentasi
-- ===========================
UPDATE origo.survey_checklist_items
SET wajib_foto_policy = 'tanpa'
WHERE id = 71;

-- ===========================
-- D.1 Internet 10 Mbps (ID=74)
-- Kalau 'Tidak Punya' → tanpa dokumentasi
-- ===========================
UPDATE origo.survey_checklist_items
SET wajib_foto_policy = 'tanpa'
WHERE id = 74;

-- ===========================
-- D.2 Meja & kursi ergonomis (ID=75)
-- Kalau 'Tidak Punya' → tanpa dokumentasi
-- ===========================
UPDATE origo.survey_checklist_items
SET wajib_foto_policy = 'tanpa'
WHERE id = 75;

-- ===========================
-- D.3 Pantry + alat makan (ID=76)
-- Kalau 'Tidak - Tidak Tersedia' → tanpa dokumentasi
-- ===========================
UPDATE origo.survey_checklist_items
SET wajib_foto_policy = 'tanpa'
WHERE id = 76;

-- ===========================
-- D.4 Toilet karyawan (ID=77) — perubahan besar
-- Ganti type dari 'binary' ke 'ada_tidak' dengan 3 opsi
-- Kalau 'Tidak ada toilet...' → tanpa dokumentasi
-- ===========================
UPDATE origo.survey_checklist_items
SET type_id = 8,  -- ada_tidak
    wajib_foto_policy = 'tanpa',
    label = '🚻 Toilet karyawan (terpisah dari konsumen)',
    tip = 'Ketersediaan toilet terpisah antara karyawan dan konsumen',
    helper = 'Toilet terpisah untuk karyawan dan konsumen',
    helper_foto = '{}'::jsonb
WHERE id = 77;

-- ===========================
-- E.1 Listrik + backup daya (ID=78)
-- Cukup Genset saja, tidak perlu UPS
-- label update, helper update
-- Kalau 'Tidak - Tidak Tersedia' → tanpa dokumentasi
-- ===========================
UPDATE origo.survey_checklist_items
SET wajib_foto_policy = 'tanpa',
    label = '⚡ Genset / backup daya tersedia',
    helper = 'Genset atau backup daya tersedia untuk operasional',
    tip = 'Genset/backup daya tersedia untuk operasional. Tidak perlu UPS, cukup Genset'
WHERE id = 78;

-- ===========================
-- E.2 Komputer/PC 1 unit per staf (ID=79)
-- Ganti jadi 'Komputer/PC 1 unit untuk Admin/Kasir'
-- Pilihan: Ada berfungsi, Ada lambat/tdk layak, Tidak ada
-- ===========================
-- type_id=1 (yesno) sudah sesuai (Ya/Rusak/Tidak)
UPDATE origo.survey_checklist_items
SET wajib_foto_policy = 'tanpa',
    label = '💻 Komputer/PC 1 unit untuk Admin/Kasir',
    helper = 'Komputer PC untuk Admin/Kasir, berfungsi baik',
    tip = 'Komputer PC minimal 1 unit untuk Admin/Kasir, berfungsi baik'
WHERE id = 79;

-- ===========================
-- E.3 Printer multifungsi (ID=80)
-- Kalau 'Tidak - Tidak Tersedia' → tanpa dokumentasi
-- ===========================
UPDATE origo.survey_checklist_items
SET wajib_foto_policy = 'tanpa'
WHERE id = 80;

-- ===========================
-- E.4 Alat tulis kantor (ID=81) — diganti jadi Printer dot-matrix
-- Ganti type ke 1 (yesno) karena pilihan: Ya—Rusak—Tidak
-- ===========================
UPDATE origo.survey_checklist_items
SET type_id = 1,  -- yesno
    wajib_foto_policy = 'tanpa',
    label = '🖨️ Printer dot-matrix (print RV/kertas rangkap)',
    helper = 'Printer dot-matrix untuk print kertas rangkap/RV',
    tip = 'Printer dot-matrix tersedia dan berfungsi untuk print dokumen rangkap/RV',
    helper_foto = '{"1": "📸 Foto printer dot-matrix yang rusak/macet"}'::jsonb
WHERE id = 81;

-- ===========================
-- E.7 Printer dot matrix / LX (ID=84) — HAPUS (pindah ke E.4)
-- ===========================
UPDATE origo.survey_checklist_items
SET is_active = false
WHERE id = 84;

-- ===========================
-- F.1 APAR (ID=85)
-- Kalau 'Tidak Ada' → tanpa dokumentasi
-- ===========================
UPDATE origo.survey_checklist_items
SET wajib_foto_policy = 'tanpa'
WHERE id = 85;

-- ===========================
-- F.2 Cashbox / laci uang (ID=86)
-- Kalau 'Tidak - Tidak Tersedia' → tanpa dokumentasi
-- ===========================
UPDATE origo.survey_checklist_items
SET wajib_foto_policy = 'tanpa'
WHERE id = 86;

-- ===========================
-- F.3 Brankas (ID=87)
-- Kalau 'Ada — Tersedia' → WAJIB ada foto (policy='ada_berfungsi')
-- ===========================
UPDATE origo.survey_checklist_items
SET wajib_foto_policy = 'ada_berfungsi',
    helper_foto = '{"0": "📸 Foto brankas — buktikan tersedia"}'::jsonb
WHERE id = 87;

-- ===========================
-- F.4 CCTV (ID=88)
-- Kalau 'Tidak Ada' → tanpa dokumentasi
-- ===========================
UPDATE origo.survey_checklist_items
SET wajib_foto_policy = 'tanpa'
WHERE id = 88;

-- ===========================
-- F.6 Garasi/area parkir sitaan (ID=90) — HAPUS
-- ===========================
UPDATE origo.survey_checklist_items
SET is_active = false
WHERE id = 90;

-- ===========================
-- F.8 Kunci pintu utama (ID=92)
-- Kalau 'Ada — Tersedia' → WAJIB ada foto
-- ===========================
UPDATE origo.survey_checklist_items
SET wajib_foto_policy = 'ada_berfungsi',
    helper_foto = '{"0": "📸 Foto kunci pintu utama — buktikan tersedia"}'::jsonb
WHERE id = 92;

-- ===========================
-- F.9 Pencatatan kendaraan sitaan (ID=93) — HAPUS
-- ===========================
UPDATE origo.survey_checklist_items
SET is_active = false
WHERE id = 93;

-- ===========================
-- G.1 Buku tamu (ID=95)
-- Kalau 'Tidak Ada' → tanpa dokumentasi
-- ===========================
UPDATE origo.survey_checklist_items
SET wajib_foto_policy = 'tanpa'
WHERE id = 95;

-- ===========================
-- G.2 Jadwal piket kebersihan (ID=96)
-- Kalau 'Tidak Ada' → tanpa dokumentasi
-- ===========================
UPDATE origo.survey_checklist_items
SET wajib_foto_policy = 'tanpa'
WHERE id = 96;

-- ===========================
-- G.3 SIUP/Izin usaha (ID=97)
-- Kalau 'Tidak Ada' → tanpa dokumentasi
-- ===========================
UPDATE origo.survey_checklist_items
SET wajib_foto_policy = 'tanpa'
WHERE id = 97;

-- ===========================
-- G.4 Tabel suku bunga (ID=98)
-- Kalau 'Tidak Terpampang' → tanpa dokumentasi
-- ===========================
UPDATE origo.survey_checklist_items
SET wajib_foto_policy = 'tanpa'
WHERE id = 98;

-- ===========================
-- G.5 Nomor pengaduan/hotline (ID=99)
-- Kalau 'Tidak - Tidak Tersedia' → tanpa dokumentasi
-- ===========================
UPDATE origo.survey_checklist_items
SET wajib_foto_policy = 'tanpa'
WHERE id = 99;

-- ===========================
-- G.6 SOP pelayanan nasabah (ID=100) — HAPUS
-- ===========================
UPDATE origo.survey_checklist_items
SET is_active = false
WHERE id = 100;

-- ====================================================================
-- TAMBAH ITEM BARU: Tidak ada permintaan item baru — hanya perubahan
-- ====================================================================

-- ====================================================================
-- UPDATE item_idx untuk item yang masih aktif — re-index per kategori
-- ====================================================================
-- Karena ada yang dihapus (is_active=false), item_idx perlu di-re-index
-- TAPI: item_idx adalah urutan display. Kita akan update agar konsisten
-- dengan urutan sort_order di catatan.
-- Untuk sekarang, item_idx akan digunakan sebagai urutan display.
-- Kita re-index manual:

-- Cat 1 (A) — ID 51-56: idx tetap 0-5
UPDATE origo.survey_checklist_items SET item_idx = 0 WHERE id = 51;
UPDATE origo.survey_checklist_items SET item_idx = 1 WHERE id = 52;
UPDATE origo.survey_checklist_items SET item_idx = 2 WHERE id = 53;
UPDATE origo.survey_checklist_items SET item_idx = 3 WHERE id = 54;
UPDATE origo.survey_checklist_items SET item_idx = 4 WHERE id = 55;
UPDATE origo.survey_checklist_items SET item_idx = 5 WHERE id = 56;

-- Cat 2 (B) — ID 57-60: idx 6-9
UPDATE origo.survey_checklist_items SET item_idx = 6 WHERE id = 57;
UPDATE origo.survey_checklist_items SET item_idx = 7 WHERE id = 58;
UPDATE origo.survey_checklist_items SET item_idx = 8 WHERE id = 59;
UPDATE origo.survey_checklist_items SET item_idx = 9 WHERE id = 60;

-- Cat 3 (C) — ID 61-73: 14 items (air-C.11)
-- D.hapus: C.3 (AC), C.6 (meja kasir), C.7 (meja marketing), C.11 (dispenser)
-- Tapi kita gak hapus — kita ubah policy-nya jadi 'tanpa'
-- Jadi semua tetap aktif.
UPDATE origo.survey_checklist_items SET item_idx = 10 WHERE id = 61;
UPDATE origo.survey_checklist_items SET item_idx = 11 WHERE id = 62;
UPDATE origo.survey_checklist_items SET item_idx = 12 WHERE id = 63;
UPDATE origo.survey_checklist_items SET item_idx = 13 WHERE id = 64;
UPDATE origo.survey_checklist_items SET item_idx = 14 WHERE id = 65;
UPDATE origo.survey_checklist_items SET item_idx = 15 WHERE id = 66;
UPDATE origo.survey_checklist_items SET item_idx = 16 WHERE id = 67;
UPDATE origo.survey_checklist_items SET item_idx = 17 WHERE id = 68;
UPDATE origo.survey_checklist_items SET item_idx = 18 WHERE id = 69;
UPDATE origo.survey_checklist_items SET item_idx = 19 WHERE id = 70;
UPDATE origo.survey_checklist_items SET item_idx = 20 WHERE id = 71;
UPDATE origo.survey_checklist_items SET item_idx = 21 WHERE id = 72;
UPDATE origo.survey_checklist_items SET item_idx = 22 WHERE id = 73;

-- Cat 4 (D) — ID 74-77: 4 items
UPDATE origo.survey_checklist_items SET item_idx = 23 WHERE id = 74;
UPDATE origo.survey_checklist_items SET item_idx = 24 WHERE id = 75;
UPDATE origo.survey_checklist_items SET item_idx = 25 WHERE id = 76;
UPDATE origo.survey_checklist_items SET item_idx = 26 WHERE id = 77;

-- Cat 5 (E) — ID 78-83: 6 items (E.1-E.6)
-- E.7 (ID=84) dihapus
UPDATE origo.survey_checklist_items SET item_idx = 27 WHERE id = 78;
UPDATE origo.survey_checklist_items SET item_idx = 28 WHERE id = 79;
UPDATE origo.survey_checklist_items SET item_idx = 29 WHERE id = 80;
UPDATE origo.survey_checklist_items SET item_idx = 30 WHERE id = 81;
UPDATE origo.survey_checklist_items SET item_idx = 31 WHERE id = 82;
UPDATE origo.survey_checklist_items SET item_idx = 32 WHERE id = 83;

-- Cat 6 (F) — ID 85-92, 94: 9 items (F.1-F.5, F.7, F.8, F.10)
-- F.6 (ID=90) dan F.9 (ID=93) dihapus
UPDATE origo.survey_checklist_items SET item_idx = 33 WHERE id = 85;  -- F.1 APAR
UPDATE origo.survey_checklist_items SET item_idx = 34 WHERE id = 86;  -- F.2 Cashbox
UPDATE origo.survey_checklist_items SET item_idx = 35 WHERE id = 87;  -- F.3 Brankas
UPDATE origo.survey_checklist_items SET item_idx = 36 WHERE id = 88;  -- F.4 CCTV
UPDATE origo.survey_checklist_items SET item_idx = 37 WHERE id = 89;  -- F.5 Duplikat kunci
-- F.6 ID=90 hapus
UPDATE origo.survey_checklist_items SET item_idx = 38 WHERE id = 91;  -- F.7 Kunci brankas
UPDATE origo.survey_checklist_items SET item_idx = 39 WHERE id = 92;  -- F.8 Kunci pintu utama
-- F.9 ID=93 hapus
UPDATE origo.survey_checklist_items SET item_idx = 40 WHERE id = 94;  -- F.10 Pintu besi

-- Cat 7 (G) — ID 95-99: 5 items
-- G.6 (ID=100) dihapus
UPDATE origo.survey_checklist_items SET item_idx = 41 WHERE id = 95;  -- G.1
UPDATE origo.survey_checklist_items SET item_idx = 42 WHERE id = 96;  -- G.2
UPDATE origo.survey_checklist_items SET item_idx = 43 WHERE id = 97;  -- G.3
UPDATE origo.survey_checklist_items SET item_idx = 44 WHERE id = 98;  -- G.4
UPDATE origo.survey_checklist_items SET item_idx = 45 WHERE id = 99;  -- G.5

-- ====================================================================
-- TAMBAH TYPE BARU untuk D.4 Toilet karyawan (type_id=8 'ada_tidak')
-- sudah ada di DB: "Ada/Tidak polos" dengan opsi ✅ Ada / ❌ Tidak
-- TAPI D.4 butuh 3 opsi: 'ada terpisah', 'ada tidak terpisah', 'tidak ada'
-- 
-- Solusi: gunakan type_id=8 (ada_tidak) dengan label yang diedit manual
-- atau buat type baru. Untuk sekarang type=8 cukup karena helper_foto
-- dan label pilihan tetap jelas.
-- ====================================================================

COMMIT;
