-- ============================================================
-- Migration: Policy + Item Changes (2026-05-18) v2
-- HATI-HATI: Semua perubahan dalam satu transaksi
-- ============================================================
BEGIN;

-- ============================================================
-- 1. Tambah question type: toilet_karyawan (3 opsi)
-- ============================================================
INSERT INTO origo.survey_question_types (type_code, type_name, description, score_weights)
VALUES ('toilet_karyawan', 'Toilet Karyawan (3 opsi)', 'Ada terpisah / Ada tidak terpisah / Tidak ada', '{"0": 1.00, "1": 0.70, "2": 0.00}')
ON CONFLICT (type_code) DO NOTHING;

-- Option: Terpisah
INSERT INTO origo.survey_type_options (type_id, opt_value, opt_label, weight_mult, is_no, sort_order, label_short, css_class)
SELECT t.id, '0', '✅ Ada — Terpisah toilet karyawan dengan toilet nasabah', 1.00, false, 1, '✅ Terpisah', 'badge-green'
FROM origo.survey_question_types t WHERE t.type_code = 'toilet_karyawan'
AND NOT EXISTS (SELECT 1 FROM origo.survey_type_options o WHERE o.type_id = t.id AND o.opt_value = '0');

-- Option: Tidak terpisah
INSERT INTO origo.survey_type_options (type_id, opt_value, opt_label, weight_mult, is_no, sort_order, label_short, css_class)
SELECT t.id, '1', '⚠️ Ada — Tidak terpisah toilet karyawan dengan toilet nasabah', 0.70, false, 2, '⚠️ ½', 'badge-yellow'
FROM origo.survey_question_types t WHERE t.type_code = 'toilet_karyawan'
AND NOT EXISTS (SELECT 1 FROM origo.survey_type_options o WHERE o.type_id = t.id AND o.opt_value = '1');

-- Option: Tidak ada
INSERT INTO origo.survey_type_options (type_id, opt_value, opt_label, weight_mult, is_no, sort_order, label_short, css_class)
SELECT t.id, '2', '❌ Tidak ada toilet untuk karyawan maupun anggota', 0.00, true, 3, '❌ Tidak', 'badge-red'
FROM origo.survey_question_types t WHERE t.type_code = 'toilet_karyawan'
AND NOT EXISTS (SELECT 1 FROM origo.survey_type_options o WHERE o.type_id = t.id AND o.opt_value = '2');

-- ============================================================
-- 2. Tambah question type: komputer_kasir (3 opsi)
-- ============================================================
INSERT INTO origo.survey_question_types (type_code, type_name, description, score_weights)
VALUES ('komputer_kasir', 'Komputer Kasir (3 opsi)', 'Ada baik / Ada lambat / Tidak ada', '{"0": 1.00, "1": 0.40, "2": 0.00}')
ON CONFLICT (type_code) DO NOTHING;

INSERT INTO origo.survey_type_options (type_id, opt_value, opt_label, weight_mult, is_no, sort_order, label_short, css_class)
SELECT t.id, '0', '✅ Ada — Berfungsi baik', 1.00, false, 1, '✅ Baik', 'badge-green'
FROM origo.survey_question_types t WHERE t.type_code = 'komputer_kasir'
AND NOT EXISTS (SELECT 1 FROM origo.survey_type_options o WHERE o.type_id = t.id AND o.opt_value = '0');

INSERT INTO origo.survey_type_options (type_id, opt_value, opt_label, weight_mult, is_no, sort_order, label_short, css_class)
SELECT t.id, '1', '⚠️ Ada — Sudah lambat/tidak layak', 0.40, false, 2, '⚠️ ½', 'badge-yellow'
FROM origo.survey_question_types t WHERE t.type_code = 'komputer_kasir'
AND NOT EXISTS (SELECT 1 FROM origo.survey_type_options o WHERE o.type_id = t.id AND o.opt_value = '1');

INSERT INTO origo.survey_type_options (type_id, opt_value, opt_label, weight_mult, is_no, sort_order, label_short, css_class)
SELECT t.id, '2', '❌ Tidak ada', 0.00, true, 3, '❌ Tidak', 'badge-red'
FROM origo.survey_question_types t WHERE t.type_code = 'komputer_kasir'
AND NOT EXISTS (SELECT 1 FROM origo.survey_type_options o WHERE o.type_id = t.id AND o.opt_value = '2');

-- ============================================================
-- 3. Update item D.4 (ID=77): ganti type ke toilet_karyawan
-- ============================================================
UPDATE origo.survey_checklist_items 
SET type_id = (SELECT id FROM origo.survey_question_types WHERE type_code = 'toilet_karyawan'),
    options_json = NULL,
    label = '🚻 Toilet karyawan (terpisah)',
    tip = 'Apakah toilet karyawan terpisah dari toilet nasabah?',
    wajib_foto_policy = 'bermasalah',
    policy_if_no = true
WHERE id = 77;

-- ============================================================
-- 4. Update E.1 (ID=78): Label Genset saja
-- ============================================================
UPDATE origo.survey_checklist_items 
SET label = '⚡ Genset / backup daya tersedia',
    tip = 'Apakah kantor memiliki genset sebagai backup daya listrik? (UPS tidak diperlukan)',
    wajib_foto_policy = 'bermasalah',
    policy_if_no = true
WHERE id = 78;

-- ============================================================
-- 5. Update E.2 (ID=79): Ganti type ke komputer_kasir
-- ============================================================
UPDATE origo.survey_checklist_items 
SET type_id = (SELECT id FROM origo.survey_question_types WHERE type_code = 'komputer_kasir'),
    options_json = NULL,
    label = '💻 Komputer/PC 1 unit untuk Admin/Kasir',
    tip = 'Apakah tersedia komputer/PC yang berfungsi untuk admin atau kasir?',
    wajib_foto_policy = 'bermasalah',
    policy_if_no = true
WHERE id = 79;

-- ============================================================
-- 6. Update E.3 (ID=80): policy_if_no
-- ============================================================
UPDATE origo.survey_checklist_items 
SET label = '🖨️ Printer multifungsi (scan, copy, print)',
    wajib_foto_policy = 'bermasalah',
    policy_if_no = true
WHERE id = 80;

-- ============================================================
-- 7. Update E.4 (ID=81): Ganti jadi Printer dot-matrix, type=ada_tidak_rusak
-- ============================================================
-- Gunakan type 'ada_tidak' (type_code='ada_tidak') yang ada — options_json override
UPDATE origo.survey_checklist_items 
SET type_id = (SELECT id FROM origo.survey_question_types WHERE type_code = 'yesno'),
    options_json = '[{"v":0,"l":"✅ Ya — Tersedia & Berfungsi"},{"v":1,"l":"⚠️ Rusak — Ada tapi Rusak"},{"v":2,"l":"❌ Tidak — Tidak Tersedia"}]',
    label = '🖨️ Printer dot-matrix (print RV/kertas rangkap)',
    tip = 'Apakah tersedia printer dot-matrix untuk mencetak RV atau kertas rangkap?',
    wajib_foto_policy = 'bermasalah',
    policy_if_no = true
WHERE id = 81;

-- ============================================================
-- 8. Hapus E.7 — Printer dot matrix / LX (sudah pindah ke E.4)
-- ============================================================
UPDATE origo.survey_checklist_items 
SET is_active = false, wajib_foto_policy = 'tanpa', policy_if_no = false
WHERE id IN (SELECT id FROM origo.survey_checklist_items 
             WHERE label LIKE '%Printer dot matrix%LX%' AND is_active = true);

-- ============================================================
-- 9. F.1-F.8: Update policy untuk item keamanan
-- ============================================================
-- F.1 (ID=85): APAR
UPDATE origo.survey_checklist_items SET wajib_foto_policy = 'bermasalah', policy_if_no = true WHERE id = 85;
-- F.2 (ID=86): Cashbox
UPDATE origo.survey_checklist_items SET wajib_foto_policy = 'bermasalah', policy_if_no = true WHERE id = 86;
-- F.3 (ID=87): Brankas — foto kalo ADA (score=0)
UPDATE origo.survey_checklist_items SET wajib_foto_policy = 'ada_berfungsi', policy_if_no = false WHERE id = 87;
-- F.4 (ID=88): CCTV
UPDATE origo.survey_checklist_items SET wajib_foto_policy = 'bermasalah', policy_if_no = true WHERE id = 88;
-- F.6 — Hapus
UPDATE origo.survey_checklist_items SET is_active = false, wajib_foto_policy = 'tanpa', policy_if_no = false
WHERE id IN (SELECT id FROM origo.survey_checklist_items WHERE label LIKE '%Garasi%parkir%' AND is_active = true);
-- F.8 (ID=92): Kunci pintu — foto kalo ADA
UPDATE origo.survey_checklist_items SET wajib_foto_policy = 'ada_berfungsi', policy_if_no = false WHERE id = 92;
-- F.9 — Hapus
UPDATE origo.survey_checklist_items SET is_active = false, wajib_foto_policy = 'tanpa', policy_if_no = false
WHERE id IN (SELECT id FROM origo.survey_checklist_items WHERE label LIKE '%kendaraan sitaan%' AND is_active = true);

-- ============================================================
-- 10. G.1-G.5: Update policy
-- ============================================================
UPDATE origo.survey_checklist_items SET wajib_foto_policy = 'bermasalah', policy_if_no = true WHERE id = 95;
UPDATE origo.survey_checklist_items SET wajib_foto_policy = 'bermasalah', policy_if_no = true WHERE id = 96;
UPDATE origo.survey_checklist_items SET wajib_foto_policy = 'bermasalah', policy_if_no = true WHERE id = 97;
UPDATE origo.survey_checklist_items SET wajib_foto_policy = 'bermasalah', policy_if_no = true WHERE id = 98;
UPDATE origo.survey_checklist_items SET wajib_foto_policy = 'bermasalah', policy_if_no = true WHERE id = 99;
-- G.6 — Hapus
UPDATE origo.survey_checklist_items SET is_active = false, wajib_foto_policy = 'tanpa', policy_if_no = false
WHERE id IN (SELECT id FROM origo.survey_checklist_items WHERE label LIKE '%SOP pelayanan%' AND is_active = true);

-- ============================================================
-- 11. Kustomisasi F.3 dan F.8 options_json untuk label konsisten
-- ============================================================
UPDATE origo.survey_checklist_items 
SET options_json = '[{"v":0,"l":"✅ Ada — Tersedia"},{"v":2,"l":"❌ Tidak — Tidak Tersedia"}]'
WHERE id IN (87, 92);

COMMIT;
