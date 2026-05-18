-- ============================================================
-- Migration 001: Align pernyataan ↔ pilihan status di survey form
-- Tanggal: 2026-05-18
-- Tujuan: Setiap question_type punya option yang nyambung dengan
--         pernyataan, bukan cuma Ya/Tidak/Rusak generik
-- ============================================================
BEGIN;

-- 1. Tambah kolom deskripsi ke question_types
ALTER TABLE origo.survey_question_types
  ADD COLUMN IF NOT EXISTS description text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS score_weights jsonb NOT NULL DEFAULT '{}';

-- 2. Update deskripsi dan score weights per type
UPDATE origo.survey_question_types SET
  description = 'Ya/Rusak/Tidak — untuk pernyataan kondisi umum (ada, rusak, tidak ada)',
  score_weights = '{"0": 1.00, "1": 0.50, "2": 0.00}'
WHERE type_code = 'yesno';

UPDATE origo.survey_question_types SET
  description = 'Ada/Tidak — untuk pernyataan ketersediaan sederhana',
  score_weights = '{"0": 1.00, "2": 0.00}'
WHERE type_code = 'binary';

UPDATE origo.survey_question_types SET
  description = 'Layak/Rusak/Tidak — untuk pernyataan kondisi kualitatif',
  score_weights = '{"0": 1.00, "1": 0.50, "2": 0.00}'
WHERE type_code = 'condition';

UPDATE origo.survey_question_types SET
  description = 'Tingkatan parkir 1-5 — untuk pernyataan ketersediaan kuantitatif',
  score_weights = '{"0": 1.00, "1": 0.75, "2": 0.50, "3": 0.25, "4": 0.00}'
WHERE type_code = 'parkir';

UPDATE origo.survey_question_types SET
  description = 'Posisi lantai terhadap jalan — untuk pernyataan elevasi',
  score_weights = '{"0": 1.00, "1": 0.60, "2": 0.20}'
WHERE type_code = 'tinggi_jalan';

UPDATE origo.survey_question_types SET
  description = '≥ / < ukuran standar — untuk pernyataan kecukupan luas',
  score_weights = '{"0": 1.00, "1": 0.50, "2": 0.00}'
WHERE type_code = 'ukuran_ruang';

UPDATE origo.survey_question_types SET
  description = 'Level daya listrik — untuk pernyataan kapasitas listrik',
  score_weights = '{"0": 1.00, "1": 0.50, "2": 0.00}'
WHERE type_code = 'listrik_daya';

UPDATE origo.survey_question_types SET
  description = 'Ada/Tidak polos — untuk pernyataan ketersediaan tipe biner',
  score_weights = '{"0": 1.00, "2": 0.00}'
WHERE type_code = 'ada_tidak';

-- 3. Update option labels jadi lebih deskriptif (nyambung sama pernyataan)
-- type 1: yesno
UPDATE origo.survey_type_options SET opt_label = '✅ Ya — Tersedia & Berfungsi' WHERE id = 1;
UPDATE origo.survey_type_options SET opt_label = '⚠️ Rusak — Ada tapi Rusak' WHERE id = 2;
UPDATE origo.survey_type_options SET opt_label = '❌ Tidak — Tidak Tersedia' WHERE id = 3;

-- type 2: binary
UPDATE origo.survey_type_options SET opt_label = '✅ Ada — Tersedia' WHERE id = 4;
UPDATE origo.survey_type_options SET opt_label = '❌ Tidak — Tidak Tersedia' WHERE id = 5;

-- type 3: condition
UPDATE origo.survey_type_options SET opt_label = '✅ Layak — Kondisi Baik' WHERE id = 6;
UPDATE origo.survey_type_options SET opt_label = '⚠️ Rusak — Kondisi Kurang' WHERE id = 7;
UPDATE origo.survey_type_options SET opt_label = '❌ Tidak — Tidak Ada' WHERE id = 8;

-- type 4: parkir — already fairly descriptive but make them relate to parking specifically
UPDATE origo.survey_type_options SET opt_label = '✅ Tersedia — > 1 mobil + >3 motor' WHERE id = 9;
UPDATE origo.survey_type_options SET opt_label = '✅ Tersedia — 1 mobil + 3 motor' WHERE id = 10;
UPDATE origo.survey_type_options SET opt_label = '⚠️ Tersedia — hanya 1 mobil atau 3 motor' WHERE id = 11;
UPDATE origo.survey_type_options SET opt_label = '❌ Kurang — hanya < 3 motor' WHERE id = 12;
UPDATE origo.survey_type_options SET opt_label = '❌ Tidak — tidak ada parkir sama sekali' WHERE id = 13;

-- type 5: tinggi_jalan
UPDATE origo.survey_type_options SET opt_label = '✅ Aman — lantai > jalan (anti banjir)' WHERE id = 14;
UPDATE origo.survey_type_options SET opt_label = '⚠️ Se level — risiko banjir rendah' WHERE id = 15;
UPDATE origo.survey_type_options SET opt_label = '❌ Risiko — lantai < jalan (rawan banjir)' WHERE id = 16;

-- type 6: ukuran_ruang
UPDATE origo.survey_type_options SET opt_label = '✅ Luas — ≥ 3×4 meter (cukup)' WHERE id = 17;
UPDATE origo.survey_type_options SET opt_label = '⚠️ Sempit — < 3×4 meter (minim)' WHERE id = 18;
UPDATE origo.survey_type_options SET opt_label = '❌ Tidak — tidak ada ruangan' WHERE id = 19;

-- type 7: listrik_daya
UPDATE origo.survey_type_options SET opt_label = '✅ Besar — > 2200W (sangat cukup)' WHERE id = 20;
UPDATE origo.survey_type_options SET opt_label = '⚡ Cukup — 1300–2200W (minimal)' WHERE id = 21;
UPDATE origo.survey_type_options SET opt_label = '❌ Kurang — < 1300W (tidak cukup)' WHERE id = 22;

-- type 8: ada_tidak
UPDATE origo.survey_type_options SET opt_label = '✅ Tersedia' WHERE id = 23;
UPDATE origo.survey_type_options SET opt_label = '❌ Tidak tersedia' WHERE id = 24;

-- 4. Tambah kolom untuk template rendering pattern di type_options
ALTER TABLE origo.survey_type_options
  ADD COLUMN IF NOT EXISTS label_short varchar(20) NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS css_class varchar(30) NOT NULL DEFAULT '';

-- Isi label_short (buat badge kecil / compact view)
UPDATE origo.survey_type_options SET label_short = '✅ Ya'   , css_class = 'badge-green'  WHERE id IN (1,4,6,9,10,14,17,20,23);
UPDATE origo.survey_type_options SET label_short = '✅ Ada 2', css_class = 'badge-green'  WHERE id = 10;
UPDATE origo.survey_type_options SET label_short = '⚠️ ½'   , css_class = 'badge-yellow' WHERE id IN (2,7,11,15,18,21);
UPDATE origo.survey_type_options SET label_short = '⚠️ Risiko', css_class = 'badge-yellow' WHERE id = 16;
UPDATE origo.survey_type_options SET label_short = '❌ ¼'   , css_class = 'badge-red'    WHERE id = 12;
UPDATE origo.survey_type_options SET label_short = '❌ Tidak', css_class = 'badge-red'    WHERE id IN (3,5,8,13,19,22,24);

COMMIT;
