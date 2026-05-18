-- ============================================================
-- Migration: Policy + Item Changes (2026-05-18)
-- Author: OrigoClaw
-- HATI-HATI: Baca komentar di setiap blok sebelum jalankan
-- ============================================================
BEGIN;

-- ============================================================
-- 1. Tambah question type baru untuk D.4 (3 opsi toilet)
-- ============================================================
INSERT INTO origo.survey_question_types (type_code, type_name, description, default_options_json)
VALUES ('toilet_karyawan', 'Toilet Karyawan (3 opsi)', 'Ada terpisah / Ada tidak terpisah / Tidak ada', NULL)
ON CONFLICT (type_code) DO NOTHING;

-- Tambah option untuk type baru
INSERT INTO origo.survey_type_options (type_id, opt_value, opt_label, weight_mult, sort_order, is_no)
SELECT t.id, 0, '✅ Ada — Terpisah toilet karyawan dengan toilet nasabah', 0.0, 1, false
FROM origo.survey_question_types t WHERE t.type_code = 'toilet_karyawan'
ON CONFLICT DO NOTHING;

INSERT INTO origo.survey_type_options (type_id, opt_value, opt_label, weight_mult, sort_order, is_no)
SELECT t.id, 1, '⚠️ Ada — Tidak terpisah toilet karyawan dengan toilet nasabah', 0.3, 2, false
FROM origo.survey_question_types t WHERE t.type_code = 'toilet_karyawan'
ON CONFLICT DO NOTHING;

INSERT INTO origo.survey_type_options (type_id, opt_value, opt_label, weight_mult, sort_order, is_no)
SELECT t.id, 2, '❌ Tidak ada toilet untuk karyawan maupun anggota', 1.0, 3, true
FROM origo.survey_question_types t WHERE t.type_code = 'toilet_karyawan'
ON CONFLICT DO NOTHING;

-- ============================================================
-- 2. Tambah type baru untuk E.2 (Komputer Admin/Kasir — 3 opsi)
-- ============================================================
INSERT INTO origo.survey_question_types (type_code, type_name, description, default_options_json)
VALUES ('komputer_kasir', 'Komputer Kasir (3 opsi)', 'Ada baik / Ada lambat / Tidak ada', NULL)
ON CONFLICT (type_code) DO NOTHING;

INSERT INTO origo.survey_type_options (type_id, opt_value, opt_label, weight_mult, sort_order, is_no)
SELECT t.id, 0, '✅ Ada — Berfungsi baik', 0.0, 1, false
FROM origo.survey_question_types t WHERE t.type_code = 'komputer_kasir'
ON CONFLICT DO NOTHING;

INSERT INTO origo.survey_type_options (type_id, opt_value, opt_label, weight_mult, sort_order, is_no)
SELECT t.id, 1, '⚠️ Ada — Sudah lambat/tidak layak', 0.6, 2, false
FROM origo.survey_question_types t WHERE t.type_code = 'komputer_kasir'
ON CONFLICT DO NOTHING;

INSERT INTO origo.survey_type_options (type_id, opt_value, opt_label, weight_mult, sort_order, is_no)
SELECT t.id, 2, '❌ Tidak ada', 1.0, 3, true
FROM origo.survey_question_types t WHERE t.type_code = 'komputer_kasir'
ON CONFLICT DO NOTHING;

-- ============================================================
-- 3. Tambah type baru untuk E.4 (Printer dot-matrix — 3 opsi yesno)
-- ============================================================
-- Gunakan type "yesno" yang sudah ada — cukup per-item options_json

-- ============================================================
-- 4. Buat type "printer_dot" untuk E.4 yang proper
-- ============================================================
INSERT INTO origo.survey_question_types (type_code, type_name, description, default_options_json)
VALUES ('ada_tidak_rusak', 'Ada / Tidak / Rusak (3 opsi)', 'Ada berfungsi / Ada rusak / Tidak ada', NULL)
ON CONFLICT (type_code) DO NOTHING;

INSERT INTO origo.survey_type_options (type_id, opt_value, opt_label, weight_mult, sort_order, is_no)
SELECT t.id, 0, '✅ Ya — Tersedia & Berfungsi', 0.0, 1, false
FROM origo.survey_question_types t WHERE t.type_code = 'ada_tidak_rusak'
ON CONFLICT DO NOTHING;

INSERT INTO origo.survey_type_options (type_id, opt_value, opt_label, weight_mult, sort_order, is_no)
SELECT t.id, 1, '⚠️ Rusak — Ada tapi Rusak', 0.7, 2, false
FROM origo.survey_question_types t WHERE t.type_code = 'ada_tidak_rusak'
ON CONFLICT DO NOTHING;

INSERT INTO origo.survey_type_options (type_id, opt_value, opt_label, weight_mult, sort_order, is_no)
SELECT t.id, 2, '❌ Tidak — Tidak Tersedia', 1.0, 3, true
FROM origo.survey_question_types t WHERE t.type_code = 'ada_tidak_rusak'
ON CONFLICT DO NOTHING;

-- ============================================================
-- 5. Update per-item changes
-- ============================================================

-- D.4 (ID=77): Ganti type ke toilet_karyawan, hapus options_json
UPDATE origo.survey_checklist_items 
SET type_id = (SELECT id FROM origo.survey_question_types WHERE type_code = 'toilet_karyawan'),
    options_json = NULL,
    label = '🚻 Toilet karyawan (terpisah)',
    tip = 'Apakah toilet karyawan terpisah dari toilet nasabah?',
    wajib_foto_policy = 'bermasalah',
    policy_if_no = true
WHERE id = 77;

-- E.1 (ID=78): Label update — Genset saja (UPS ga perlu)
UPDATE origo.survey_checklist_items 
SET label = '⚡ Genset / backup daya tersedia',
    tip = 'Apakah kantor memiliki genset sebagai backup daya listrik? (UPS tidak diperlukan)',
    wajib_foto_policy = 'bermasalah',
    policy_if_no = true
WHERE id = 78;

-- E.2 (ID=79): Ganti type ke komputer_kasir, label baru
UPDATE origo.survey_checklist_items 
SET type_id = (SELECT id FROM origo.survey_question_types WHERE type_code = 'komputer_kasir'),
    options_json = NULL,
    label = '💻 Komputer/PC 1 unit untuk Admin/Kasir',
    tip = 'Apakah tersedia komputer/PC yang berfungsi untuk admin atau kasir?',
    wajib_foto_policy = 'bermasalah',
    policy_if_no = true
WHERE id = 79;

-- E.3 (ID=80): policy_if_no = true
UPDATE origo.survey_checklist_items 
SET label = '🖨️ Printer multifungsi (scan, copy, print)',
    wajib_foto_policy = 'bermasalah',
    policy_if_no = true
WHERE id = 80;

-- E.4 (ID=81): Ganti label + type ke ada_tidak_rusak
UPDATE origo.survey_checklist_items 
SET type_id = (SELECT id FROM origo.survey_question_types WHERE type_code = 'ada_tidak_rusak'),
    options_json = NULL,
    label = '🖨️ Printer dot-matrix (print RV/kertas rangkap)',
    tip = 'Apakah tersedia printer dot-matrix untuk mencetak RV atau kertas rangkap?',
    wajib_foto_policy = 'bermasalah',
    policy_if_no = true
WHERE id = 81;

-- E.7 — Hapus (ID yang perlu dicari dulu)
-- Cari: E.7 lama — Printer dot matrix
UPDATE origo.survey_checklist_items 
SET is_active = false, wajib_foto_policy = 'tanpa', policy_if_no = false
WHERE id = (SELECT id FROM origo.survey_checklist_items 
            WHERE label LIKE '%Printer dot matrix / LX%' AND is_active = true
            LIMIT 1);

-- F.1 (ID=85): policy_if_no = true (already)
UPDATE origo.survey_checklist_items 
SET wajib_foto_policy = 'bermasalah', policy_if_no = true
WHERE id = 85;

-- F.2 (ID=86): policy_if_no = true (already)
UPDATE origo.survey_checklist_items 
SET wajib_foto_policy = 'bermasalah', policy_if_no = true
WHERE id = 86;

-- F.3 (ID=87): Brankas — policy khusus: ada_berfungsi (foto kalo ADA/Tersedia)
UPDATE origo.survey_checklist_items 
SET wajib_foto_policy = 'ada_berfungsi', policy_if_no = false
WHERE id = 87;

-- F.4 (ID=88): policy_if_no = true (already)
UPDATE origo.survey_checklist_items 
SET wajib_foto_policy = 'bermasalah', policy_if_no = true
WHERE id = 88;

-- F.6 — Hapus
UPDATE origo.survey_checklist_items 
SET is_active = false, wajib_foto_policy = 'tanpa', policy_if_no = false
WHERE label LIKE '%Garasi%area parkir%' AND is_active = true;

-- F.8 (ID=92): Kunci pintu utama — policy ada_berfungsi (foto kalo ADA)
UPDATE origo.survey_checklist_items 
SET wajib_foto_policy = 'ada_berfungsi', policy_if_no = false
WHERE id = 92;

-- F.9 — Hapus
UPDATE origo.survey_checklist_items 
SET is_active = false, wajib_foto_policy = 'tanpa', policy_if_no = false
WHERE label LIKE '%kendaraan sitaan%' AND is_active = true;

-- G.1 (ID=95): policy_if_no = true (already)
UPDATE origo.survey_checklist_items 
SET wajib_foto_policy = 'bermasalah', policy_if_no = true
WHERE id = 95;

-- G.2 (ID=96): policy_if_no = true (already)
UPDATE origo.survey_checklist_items 
SET wajib_foto_policy = 'bermasalah', policy_if_no = true
WHERE id = 96;

-- G.3 (ID=97): policy_if_no = true (already)
UPDATE origo.survey_checklist_items 
SET wajib_foto_policy = 'bermasalah', policy_if_no = true
WHERE id = 97;

-- G.4 (ID=98): policy_if_no = true
UPDATE origo.survey_checklist_items 
SET wajib_foto_policy = 'bermasalah', policy_if_no = true
WHERE id = 98;

-- G.5 (ID=99): policy_if_no = true
UPDATE origo.survey_checklist_items 
SET wajib_foto_policy = 'bermasalah', policy_if_no = true
WHERE id = 99;

-- G.6 — Hapus
UPDATE origo.survey_checklist_items 
SET is_active = false, wajib_foto_policy = 'tanpa', policy_if_no = false
WHERE label LIKE '%SOP pelayanan%' AND is_active = true;

-- ============================================================
-- 6. Yang awalnya 'tanpa' + policy_if_no=true — update policy jadi 'bermasalah'
--    (karena policy_if_no=true + weight_mult=0.0 = effective 'tanpa')
--    TAPI tetap simpan di 'bermasalah' agar item lain (non-no) tetap perlu foto
-- ============================================================
-- Ini sudah diperbaiki oleh system baru: validasi submit cek weight_mult==0.0
-- untuk override policy jadi 'tanpa'
-- Tidak perlu update kolom wajib_foto_policy — logic di checklist.py handle

-- ============================================================
-- 7. Untuk F.3 dan F.8 — pastikan type_id sesuai
-- ============================================================
-- F.3 Brankas — binary (0=Ada, 2=Tidak), type_id harus binary
-- F.8 Kunci pintu — binary
-- Binary options: 0=Ada (score=0), 2=Tidak (score=2, is_no=true)
UPDATE origo.survey_checklist_items 
SET options_json = '[{"v":0,"l":"✅ Ada — Tersedia"},{"v":2,"l":"❌ Tidak — Tidak Tersedia"}]'
WHERE id = 87 OR id = 92;

COMMIT;
