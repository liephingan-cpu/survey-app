--
-- PostgreSQL database dump
--

\restrict qBmojo8KN5JQ8oWNEvaUDaIIUSc4iUIjA8Igy5sjhFZ2NaTstyx5bU9oYFwZ8Wb

-- Dumped from database version 16.13 (Ubuntu 16.13-0ubuntu0.24.04.1)
-- Dumped by pg_dump version 16.13 (Ubuntu 16.13-0ubuntu0.24.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: kantor_checklist_data; Type: TABLE; Schema: origo; Owner: postgres
--

CREATE TABLE origo.kantor_checklist_data (
    kantor_code text NOT NULL,
    kantor_label text DEFAULT ''::text,
    pic text DEFAULT ''::text,
    tgl_cek date DEFAULT CURRENT_DATE,
    total_items integer DEFAULT 0,
    yes_count numeric DEFAULT 0,
    no_count integer DEFAULT 0,
    status_data jsonb DEFAULT '[]'::jsonb,
    media_data jsonb DEFAULT '{}'::jsonb,
    workflow_status text DEFAULT 'draft'::text,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    submitted_at timestamp without time zone,
    updated_by text DEFAULT ''::text,
    document_number text,
    nomor_survei text,
    survey_seq integer DEFAULT 1,
    id integer NOT NULL
);


ALTER TABLE origo.kantor_checklist_data OWNER TO postgres;

--
-- Name: kantor_checklist_data_id_seq; Type: SEQUENCE; Schema: origo; Owner: postgres
--

CREATE SEQUENCE origo.kantor_checklist_data_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE origo.kantor_checklist_data_id_seq OWNER TO postgres;

--
-- Name: kantor_checklist_data_id_seq; Type: SEQUENCE OWNED BY; Schema: origo; Owner: postgres
--

ALTER SEQUENCE origo.kantor_checklist_data_id_seq OWNED BY origo.kantor_checklist_data.id;


--
-- Name: survey_categories; Type: TABLE; Schema: origo; Owner: postgres
--

CREATE TABLE origo.survey_categories (
    id integer NOT NULL,
    cat_code character varying(2) NOT NULL,
    cat_name character varying(100) NOT NULL,
    color_hex character varying(7) DEFAULT '#2563eb'::character varying NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    cat_weight numeric(5,2) DEFAULT 1.00
);


ALTER TABLE origo.survey_categories OWNER TO postgres;

--
-- Name: COLUMN survey_categories.cat_weight; Type: COMMENT; Schema: origo; Owner: postgres
--

COMMENT ON COLUMN origo.survey_categories.cat_weight IS 'Bobot kategori untuk weighted scoring';


--
-- Name: survey_categories_id_seq; Type: SEQUENCE; Schema: origo; Owner: postgres
--

CREATE SEQUENCE origo.survey_categories_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE origo.survey_categories_id_seq OWNER TO postgres;

--
-- Name: survey_categories_id_seq; Type: SEQUENCE OWNED BY; Schema: origo; Owner: postgres
--

ALTER SEQUENCE origo.survey_categories_id_seq OWNED BY origo.survey_categories.id;


--
-- Name: survey_checklist_items; Type: TABLE; Schema: origo; Owner: postgres
--

CREATE TABLE origo.survey_checklist_items (
    id integer NOT NULL,
    cat_id integer NOT NULL,
    item_idx integer NOT NULL,
    label text NOT NULL,
    tip text DEFAULT ''::text,
    type_id integer NOT NULL,
    weight numeric(5,4) DEFAULT 0.01 NOT NULL,
    wajib_foto boolean DEFAULT false NOT NULL,
    wajib_catatan boolean DEFAULT false NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    options_json jsonb,
    wajib_foto_policy text DEFAULT 'negative_only'::text NOT NULL,
    helper text DEFAULT ''::text NOT NULL,
    helper_foto jsonb DEFAULT '{}'::jsonb
);


ALTER TABLE origo.survey_checklist_items OWNER TO postgres;

--
-- Name: COLUMN survey_checklist_items.options_json; Type: COMMENT; Schema: origo; Owner: postgres
--

COMMENT ON COLUMN origo.survey_checklist_items.options_json IS 'Override label opsi per item: [{v, l, c}] — null berarti pake default dari type_options';


--
-- Name: survey_checklist_items_id_seq; Type: SEQUENCE; Schema: origo; Owner: postgres
--

CREATE SEQUENCE origo.survey_checklist_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE origo.survey_checklist_items_id_seq OWNER TO postgres;

--
-- Name: survey_checklist_items_id_seq; Type: SEQUENCE OWNED BY; Schema: origo; Owner: postgres
--

ALTER SEQUENCE origo.survey_checklist_items_id_seq OWNED BY origo.survey_checklist_items.id;


--
-- Name: survey_question_types; Type: TABLE; Schema: origo; Owner: postgres
--

CREATE TABLE origo.survey_question_types (
    id integer NOT NULL,
    type_code character varying(30) NOT NULL,
    type_name character varying(100) NOT NULL
);


ALTER TABLE origo.survey_question_types OWNER TO postgres;

--
-- Name: survey_question_types_id_seq; Type: SEQUENCE; Schema: origo; Owner: postgres
--

CREATE SEQUENCE origo.survey_question_types_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE origo.survey_question_types_id_seq OWNER TO postgres;

--
-- Name: survey_question_types_id_seq; Type: SEQUENCE OWNED BY; Schema: origo; Owner: postgres
--

ALTER SEQUENCE origo.survey_question_types_id_seq OWNED BY origo.survey_question_types.id;


--
-- Name: survey_type_options; Type: TABLE; Schema: origo; Owner: postgres
--

CREATE TABLE origo.survey_type_options (
    id integer NOT NULL,
    type_id integer NOT NULL,
    opt_value character varying(10) NOT NULL,
    opt_label character varying(100) NOT NULL,
    weight_mult numeric(3,2) DEFAULT 1.00 NOT NULL,
    is_no boolean DEFAULT false NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL
);


ALTER TABLE origo.survey_type_options OWNER TO postgres;

--
-- Name: survey_type_options_id_seq; Type: SEQUENCE; Schema: origo; Owner: postgres
--

CREATE SEQUENCE origo.survey_type_options_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE origo.survey_type_options_id_seq OWNER TO postgres;

--
-- Name: survey_type_options_id_seq; Type: SEQUENCE OWNED BY; Schema: origo; Owner: postgres
--

ALTER SEQUENCE origo.survey_type_options_id_seq OWNED BY origo.survey_type_options.id;


--
-- Name: kantor_checklist_data id; Type: DEFAULT; Schema: origo; Owner: postgres
--

ALTER TABLE ONLY origo.kantor_checklist_data ALTER COLUMN id SET DEFAULT nextval('origo.kantor_checklist_data_id_seq'::regclass);


--
-- Name: survey_categories id; Type: DEFAULT; Schema: origo; Owner: postgres
--

ALTER TABLE ONLY origo.survey_categories ALTER COLUMN id SET DEFAULT nextval('origo.survey_categories_id_seq'::regclass);


--
-- Name: survey_checklist_items id; Type: DEFAULT; Schema: origo; Owner: postgres
--

ALTER TABLE ONLY origo.survey_checklist_items ALTER COLUMN id SET DEFAULT nextval('origo.survey_checklist_items_id_seq'::regclass);


--
-- Name: survey_question_types id; Type: DEFAULT; Schema: origo; Owner: postgres
--

ALTER TABLE ONLY origo.survey_question_types ALTER COLUMN id SET DEFAULT nextval('origo.survey_question_types_id_seq'::regclass);


--
-- Name: survey_type_options id; Type: DEFAULT; Schema: origo; Owner: postgres
--

ALTER TABLE ONLY origo.survey_type_options ALTER COLUMN id SET DEFAULT nextval('origo.survey_type_options_id_seq'::regclass);


--
-- Data for Name: kantor_checklist_data; Type: TABLE DATA; Schema: origo; Owner: postgres
--

COPY origo.kantor_checklist_data (kantor_code, kantor_label, pic, tgl_cek, total_items, yes_count, no_count, status_data, media_data, workflow_status, created_at, updated_at, submitted_at, updated_by, document_number, nomor_survei, survey_seq, id) FROM stdin;
\.


--
-- Data for Name: survey_categories; Type: TABLE DATA; Schema: origo; Owner: postgres
--

COPY origo.survey_categories (id, cat_code, cat_name, color_hex, sort_order, is_active, cat_weight) FROM stdin;
1	A	LOKASI & AKSES	#2563eb	1	t	15.00
2	B	IDENTITAS & VISIBILITAS	#059669	2	t	10.00
3	C	RUANG KONSUMEN	#d97706	3	t	15.00
4	D	FASILITAS KARYAWAN	#db2777	4	t	10.00
5	E	ALAT KERJA	#7c3aed	5	t	15.00
6	F	KEAMANAN	#ea580c	6	t	25.00
7	G	DOKUMEN	#dc2626	7	t	10.00
\.


--
-- Data for Name: survey_checklist_items; Type: TABLE DATA; Schema: origo; Owner: postgres
--

COPY origo.survey_checklist_items (id, cat_id, item_idx, label, tip, type_id, weight, wajib_foto, wajib_catatan, is_active, options_json, wajib_foto_policy, helper, helper_foto) FROM stdin;
57	2	6	🏪 Papan nama / Sign Board / Spanduk Koperasi	Papan nama/Sign Board terlihat jelas dari jalan utama dan dalam kondisi baik	1	0.0230	t	f	t	\N	rusak_only	Papan nama atau Sign Board terlihat jelas dari jalan utama, kondisi baik. Foto jika rusak.	{"1": "📸 Foto papan nama / Sign Board yang rusak", "2": ""}
75	4	24	🪑 Meja & kursi kerja ergonomis	Meja dan kursi kerja ergonomis untuk kenyamanan staf saat bekerja	1	0.0230	t	f	t	[{"c": "#16a34a", "l": "Ada & berfungsi", "v": 0}, {"c": "#d97706", "l": "Ada tapi rusak", "v": 1}, {"c": "#dc2626", "l": "Tidak punya", "v": 2}]	rusak_only	Meja dan kursi kerja untuk kenyamanan staf. Foto jika rusak.	{"1": "📸 Foto meja / kursi yang rusak", "2": ""}
98	7	47	📊 Tabel suku bunga & biaya admin terpampang	Tabel suku bunga dan biaya administrasi terpampang untuk transparansi	1	0.0120	t	f	t	[{"c": "#16a34a", "l": "Terpampang", "v": 0}, {"c": "#d97706", "l": "Rusak", "v": 1}, {"c": "#dc2626", "l": "Tidak terpampang", "v": 2}]	rusak_only	Tabel suku bunga dan biaya admin terpampang untuk transparansi. Foto jika rusak.	{"1": "📸 Foto tabel suku bunga yang rusak", "2": ""}
64	3	13	🧼 Toilet bersih + sabun + tisu	Toilet dalam keadaan bersih, dilengkapi sabun cuci tangan dan tisu	3	0.0220	t	f	t	[{"c": "#16a34a", "l": "Lengkap", "v": 0}, {"c": "#d97706", "l": "Kurang lengkap", "v": 1}, {"c": "#dc2626", "l": "Tidak bersih", "v": 2}]	rusak_only	Toilet bersih, ada sabun cuci tangan dan tisu. Foto jika kurang.	{"1": "📸 Foto kondisi toilet — kurang bersih / kurang perlengkapan", "2": ""}
66	3	15	🪑 Meja kerja kasir	Tersedia meja kerja khusus untuk kasir yang rapi dan fungsional	1	0.0120	t	f	t	[{"c": "#16a34a", "l": "Ada & rapi", "v": 0}, {"c": "#d97706", "l": "Ada tapi rusak", "v": 1}, {"c": "#dc2626", "l": "Tidak ada", "v": 2}]	rusak_only	Meja kerja kasir yang rapi dan fungsional. Foto jika rusak.	{"1": "📸 Foto meja kasir yang rusak", "2": ""}
67	3	16	🪑 Meja kerja marketing	Tersedia meja kerja khusus untuk marketing yang rapi dan fungsional	1	0.0120	t	f	t	[{"c": "#16a34a", "l": "Ada & rapi", "v": 0}, {"c": "#d97706", "l": "Ada tapi rusak", "v": 1}, {"c": "#dc2626", "l": "Tidak ada", "v": 2}]	rusak_only	Meja kerja marketing yang rapi dan fungsional. Foto jika rusak.	{"1": "📸 Foto meja marketing yang rusak", "2": ""}
72	3	21	🗑️ Tempat sampah tertutup	Tempat sampah tertutup tersedia dan diletakkan di area yang mudah dijangkau	1	0.0120	f	f	t	[{"c": "#16a34a", "l": "Tertutup", "v": 0}, {"c": "#d97706", "l": "Rusak", "v": 1}, {"c": "#dc2626", "l": "Tidak tertutup", "v": 2}]	rusak_only	Tempat sampah tertutup, diletakkan di area mudah dijangkau. Foto jika rusak.	{"1": "📸 Foto tempat sampah yang rusak", "2": "📸 Foto tempat sampah terbuka / tidak tertutup"}
100	7	49	📋 SOP pelayanan nasabah terpampang	SOP pelayanan nasabah terpampang di ruang tunggu sebagai panduan pelayanan	1	0.0070	t	f	t	[{"c": "#16a34a", "l": "Terpampang", "v": 0}, {"c": "#d97706", "l": "Rusak", "v": 1}, {"c": "#dc2626", "l": "Tidak terpampang", "v": 2}]	rusak_only	SOP pelayanan nasabah terpampang di ruang tunggu. Foto jika rusak.	{"1": "📸 Foto SOP yang rusak", "2": ""}
58	2	7	🏠 Fasade kantor bersih dan terawat	Fasade/tampak depan kantor bersih, terawat, dan memberikan kesan profesional	3	0.0180	t	f	t	[{"c": "#16a34a", "l": "Bersih & terawat", "v": 0}, {"c": "#d97706", "l": "Kurang terawat", "v": 1}, {"c": "#dc2626", "l": "Kotor", "v": 2}]	rusak_only	Fasade tampak depan kantor bersih, terawat, dan profesional. Foto jika kotor.	{"1": "📸 Foto fasade kantor yang kotor", "2": ""}
59	2	8	🕐 Jam operasional terpampang	Jam operasional terpampang di depan kantor sehingga mudah diketahui konsumen	1	0.0130	t	f	t	[{"c": "#16a34a", "l": "Terpampang", "v": 0}, {"c": "#d97706", "l": "Rusak", "v": 1}, {"c": "#dc2626", "l": "Tidak terpampang", "v": 2}]	rusak_only	Jam operasional terpampang di depan kantor. Foto jika rusak.	{"1": "📸 Foto jam operasional yang rusak", "2": ""}
60	2	9	🌀 Umbul-umbul / banner tambahan	Tersedia umbul-umbul/banner/spanduk tambahan untuk meningkatkan visibilitas koperasi	1	0.0100	t	f	t	[{"c": "#16a34a", "l": "Terpampang", "v": 0}, {"c": "#d97706", "l": "Rusak", "v": 1}, {"c": "#dc2626", "l": "Tidak ada", "v": 2}]	rusak_only	Umbul-umbul, banner, atau spanduk tambahan untuk visibilitas. Foto jika rusak.	{"1": "📸 Foto umbul-umbul / banner yang rusak", "2": ""}
61	3	10	💧 Ketersediaan air bersih (sumur/PDAM/tandon)	Ketersediaan air bersih dari sumur, PDAM, atau tandon untuk operasional kantor	3	0.0340	t	f	t	[{"c": "#16a34a", "l": "Tersedia", "v": 0}, {"c": "#d97706", "l": "Rusak", "v": 1}, {"c": "#dc2626", "l": "Tidak ada", "v": 2}]	rusak_only	Air bersih dari sumur, PDAM, atau tandon. Foto jika rusak.	{"1": "📸 Foto sumber air / instalasi yang rusak", "2": ""}
69	3	18	🧹 Lantai dan dinding bersih	Lantai dan dinding kantor bersih, tidak kotor, dan terawat	3	0.0180	t	f	t	[{"c": "#16a34a", "l": "Bersih", "v": 0}, {"c": "#d97706", "l": "Kotor", "v": 1}, {"c": "#dc2626", "l": "Rusak parah", "v": 2}]	rusak_only	Lantai dan dinding kantor bersih, tidak kotor, terawat. Foto jika kotor.	{"1": "📸 Foto lantai / dinding yang kotor", "2": "📸 Foto lantai / dinding rusak parah"}
77	4	26	🚻 Toilet karyawan (terpisah)	Toilet karyawan terpisah dari toilet konsumen untuk privasi dan kebersihan	2	0.0180	f	f	t	\N	never	Toilet karyawan terpisah dari toilet konsumen.	{}
87	6	36	🗄️ Brankas tersedia	Brankas tersedia untuk penyimpanan uang dan barang berharga	2	0.0300	f	f	t	\N	never	Brankas untuk penyimpanan uang dan barang berharga.	{}
51	1	0	🅿️ Parkir (1 mobil + 3 motor)	Tersedia area parkir untuk 1 mobil dan minimal 3 motor, aman dan mudah diakses	4	0.0270	t	f	t	\N	rusak_only	Tersedia area parkir untuk 1 mobil dan minimal 3 motor, aman dan mudah diakses. Foto jika jumlah kurang.	{"1": "📸 Foto jumlah parkir yang tersedia", "2": "📸 Foto jumlah parkir yang tersedia", "3": "📸 Foto area parkir", "4": ""}
54	1	3	🧹 Depan kantor kering & rapi (bukan kubangan)	Area depan kantor kering, tidak becek, dan rapi (bukan genangan/kubangan air)	1	0.0180	t	f	t	[{"c": "#16a34a", "l": "Kering & rapi", "v": 0}, {"c": "#d97706", "l": "Becek", "v": 1}, {"c": "#dc2626", "l": "Kubangan", "v": 2}]	never	Area depan kantor kering dan rapi, bukan genangan atau kubangan air.	{"1": "📸 Foto genangan air di depan kantor", "2": "📸 Foto kubangan / genangan besar"}
89	6	38	📝 Duplikat kunci brankas tercatat	Ada catatan/pencatatan duplikat kunci brankas untuk pengendalian internal	2	0.0260	f	f	t	\N	never	Catatan duplikat kunci brankas untuk pengendalian internal.	{}
62	3	11	🚻 Toilet (tersedia dan berfungsi)	Toilet tersedia dalam kondisi berfungsi baik, bisa digunakan oleh konsumen dan karyawan	1	0.0340	t	f	t	[{"c": "#16a34a", "l": "Ada & berfungsi", "v": 0}, {"c": "#d97706", "l": "Rusak/mampet", "v": 1}, {"c": "#dc2626", "l": "Tidak ada", "v": 2}]	rusak_only	Toilet tersedia, berfungsi baik, bisa dipakai konsumen dan karyawan. Foto jika mampet.	{"1": "📸 Foto toilet mampet / rusak", "2": ""}
92	6	41	🔑 Kunci pintu utama kantor (ada/tidak)	Kunci pintu utama kantor dalam kondisi baik dan berfungsi dengan benar	2	0.0200	f	f	t	\N	never	Kunci pintu utama kantor berfungsi baik.	{}
93	6	42	📷 Pencatatan kendaraan sitaan (foto+kunci+STNK)	Sistem pencatatan kendaraan sitaan terdokumentasi (foto, kunci, STNK)	2	0.0190	f	f	t	\N	never	Pencatatan kendaraan sitaan terdokumentasi foto kunci STNK.	{}
63	3	12	❄️ AC / kipas angin berfungsi baik	AC atau kipas angin berfungsi baik untuk kenyamanan suhu ruangan	1	0.0220	t	f	t	\N	rusak_only	AC atau kipas angin berfungsi baik untuk kenyamanan suhu. Foto jika rusak.	{"1": "📸 Foto AC / kipas yang rusak", "2": ""}
65	3	14	🪟 Partisi pemisah konsumen ↔ internal	Terdapat partisi/pembatas antara area konsumen dan area internal kantor	1	0.0150	t	f	t	[{"c": "#16a34a", "l": "Ada partisi", "v": 0}, {"c": "#d97706", "l": "Rusak", "v": 1}, {"c": "#dc2626", "l": "Tidak ada", "v": 2}]	rusak_only	Ada partisi pembatas antara area konsumen dan internal. Foto jika rusak.	{"1": "📸 Foto partisi yang rusak", "2": ""}
52	1	1	🚧 Posisi lantai kantor terhadap ketinggian jalan (anti banjir)	Posisi lantai kantor tidak lebih rendah dari permukaan jalan untuk menghindari banjir	5	0.0230	t	f	t	\N	never	Posisi lantai kantor tidak lebih rendah dari permukaan jalan untuk menghindari banjir.	{"0": "", "1": "", "2": ""}
56	1	5	📐 Ukuran ruangan memadai (min 3x4m)	Ukuran ruang kantor minimal 3x4 meter untuk mendukung operasional yang nyaman	6	0.0180	t	f	t	[{"c": "#16a34a", "l": "≥ 3x4m", "v": 0}, {"c": "#f59e0b", "l": "< 3x4m", "v": 1}]	never	Ukuran ruang kantor minimal 3x4 meter untuk operasional yang nyaman.	{"1": ""}
81	5	30	📎 Alat tulis kantor lengkap	ATK (alat tulis kantor) lengkap untuk mendukung operasional harian	3	0.0190	t	f	t	[{"c": "#16a34a", "l": "Lengkap", "v": 0}, {"c": "#d97706", "l": "Kurang lengkap", "v": 1}, {"c": "#dc2626", "l": "Tidak ada", "v": 2}]	never	ATK alat tulis kantor lengkap untuk operasional harian.	{"1": "", "2": ""}
85	6	34	🔥 APAR (Alat Pemadam Api)	APAR tersedia, masih berlaku, dan diletakkan di area yang mudah dijangkau	1	0.0340	t	f	t	[{"c": "#16a34a", "l": "Ada & berlaku", "v": 0}, {"c": "#d97706", "l": "Rusak/kadaluarsa", "v": 1}, {"c": "#dc2626", "l": "Tidak ada", "v": 2}]	ada_rusak	APAR tersedia, masih berlaku, mudah dijangkau. Foto wajib.	{"0": "📸 Foto APAR — buktikan lokasi dan masa berlaku", "1": "📸 Foto APAR kadaluarsa / rusak"}
88	6	37	📹 CCTV minimal 4 titik	CCTV terpasang minimal 4 titik yang berfungsi merekam 24 jam	1	0.0270	t	f	t	[{"c": "#16a34a", "l": "Berfungsi", "v": 0}, {"c": "#d97706", "l": "Rusak", "v": 1}, {"c": "#dc2626", "l": "Tidak ada", "v": 2}]	ada_rusak	CCTV minimal 4 titik, merekam 24 jam. Foto wajib.	{"0": "📸 Foto CCTV — buktikan 4 titik", "1": "📸 Foto CCTV yang rusak"}
90	6	39	🏪 Garasi/area parkir terkunci utk sitaan	Garasi/area parkir terkunci untuk penyimpanan kendaraan sitaan yang aman	1	0.0240	t	f	t	[{"c": "#16a34a", "l": "Terkunci", "v": 0}, {"c": "#d97706", "l": "Rusak", "v": 1}, {"c": "#dc2626", "l": "Tidak terkunci", "v": 2}]	rusak_only	Garasi area parkir terkunci untuk penyimpanan sitaan. Foto jika rusak.	{"1": "📸 Foto garasi / area parkir yang tidak terkunci", "2": "📸 Foto garasi / area parkir tidak terkunci"}
97	7	46	📜 SIUP / Izin usaha terpajang	SIUP/izin usaha terpajang di dinding sebagai legalitas operasional	1	0.0200	t	f	t	[{"c": "#16a34a", "l": "Terpajang", "v": 0}, {"c": "#d97706", "l": "Rusak", "v": 1}, {"c": "#dc2626", "l": "Tidak terpajang", "v": 2}]	rusak_only	SIUP izin usaha terpajang sebagai legalitas operasional. Foto jika rusak.	{"1": "📸 Foto SIUP / izin usaha yang rusak", "2": ""}
99	7	48	📞 Nomor pengaduan / hotline tersedia	Nomor pengaduan/hotline tersedia dan terpampang untuk layanan pengaduan	2	0.0080	f	f	t	\N	never	Nomor pengaduan hotline tersedia dan terpampang.	{}
95	7	44	📋 Buku tamu / log kunjungan	Buku tamu/log kunjungan tersedia untuk mencatat tamu yang datang	1	0.0310	t	f	t	[{"c": "#16a34a", "l": "Tersedia", "v": 0}, {"c": "#d97706", "l": "Rusak", "v": 1}, {"c": "#dc2626", "l": "Tidak ada", "v": 2}]	rusak_only	Buku tamu atau log kunjungan untuk mencatat tamu. Foto jika rusak.	{"1": "📸 Foto buku tamu yang rusak", "2": ""}
96	7	45	🗓️ Jadwal piket kebersihan	Jadwal piket kebersihan terpampang dan dilaksanakan secara konsisten	1	0.0240	t	f	t	[{"c": "#16a34a", "l": "Terpampang", "v": 0}, {"c": "#d97706", "l": "Rusak", "v": 1}, {"c": "#dc2626", "l": "Tidak ada", "v": 2}]	rusak_only	Jadwal piket kebersihan terpampang dan dilaksanakan. Foto jika rusak.	{"1": "📸 Foto jadwal piket yang rusak", "2": ""}
53	1	2	🏠 Kanopi / atap depan pelindung hujan	Tersedia kanopi/atap di depan kantor sebagai pelindung dari hujan dan panas	1	0.0180	t	f	t	[{"c": "#16a34a", "l": "Ada & berfungsi", "v": 0}, {"c": "#d97706", "l": "Rusak", "v": 1}, {"c": "#dc2626", "l": "Tidak ada", "v": 2}]	rusak_only	Tersedia kanopi/atap di depan kantor sebagai pelindung dari hujan dan panas. Foto jika rusak.	{"1": "📸 Foto kondisi kanopi / atap depan", "2": ""}
73	3	22	🪴 Tanaman hias / interior kantor	Tanaman hias atau dekorasi interior untuk estetika dan kenyamanan ruangan	3	0.0120	t	f	t	[{"c": "#16a34a", "l": "Segar & rapi", "v": 0}, {"c": "#d97706", "l": "Layu / kering", "v": 1}, {"c": "#dc2626", "l": "Tidak ada", "v": 2}]	never	Tanaman hias atau dekorasi interior untuk estetika ruangan.	{"1": "", "2": ""}
91	6	40	🔑 Kunci brankas (kombinasi/ganda)	Kunci brankas menggunakan sistem kombinasi/ganda untuk keamanan berlapis	1	0.0200	t	f	t	[{"c": "#16a34a", "l": "Kombinasi/ganda", "v": 0}, {"c": "#d97706", "l": "Rusak", "v": 1}, {"c": "#dc2626", "l": "Kunci biasa", "v": 2}]	ada_rusak	Kunci brankas kombinasi atau ganda untuk keamanan berlapis. Foto wajib.	{"0": "📸 Foto kunci brankas — buktikan kombinasi/ganda", "1": "📸 Foto kunci brankas yang rusak"}
55	1	4	🔦 Penerangan luar memadai	Penerangan di area luar kantor memadai untuk keamanan dan visibilitas malam hari	3	0.0170	t	f	t	[{"c": "#16a34a", "l": "Memadai", "v": 0}, {"c": "#d97706", "l": "Kurang", "v": 1}, {"c": "#dc2626", "l": "Tidak ada", "v": 2}]	never	Penerangan area luar kantor untuk keamanan dan visibilitas malam hari.	{"1": "", "2": ""}
68	3	17	💺 Kursi tunggu nyaman minimal 4 orang	Kursi tunggu untuk konsumen minimal 4 orang, nyaman dan dalam kondisi baik	1	0.0180	t	f	t	[{"c": "#16a34a", "l": "Nyaman ≥4", "v": 0}, {"c": "#d97706", "l": "Kurang nyaman", "v": 1}, {"c": "#dc2626", "l": "Tidak ada", "v": 2}]	never	Kursi tunggu konsumen minimal 4 orang, nyaman dan kondisi baik.	{"1": "", "2": ""}
70	3	19	🚪 Pintu utama / akses masuk (kaca/kayu/besi — atau tanpa pemisah)	Pintu utama/akses masuk dalam kondisi baik — kaca, kayu, atau tanpa pemisah fisik	1	0.0140	t	f	t	\N	rusak_only	Pintu utama akses masuk kondisi baik. Foto jika rusak.	{"1": "📸 Foto pintu utama yang rusak", "2": ""}
94	6	43	🚪 Pintu besi / teralis jendela	Terdapat pintu besi/teralis jendela sebagai lapisan keamanan tambahan	1	0.0140	t	f	t	[{"c": "#16a34a", "l": "Terpasang", "v": 0}, {"c": "#d97706", "l": "Rusak", "v": 1}, {"c": "#dc2626", "l": "Tidak ada", "v": 2}]	ada_rusak	Pintu besi atau teralis jendela sebagai keamanan tambahan. Foto wajib.	{"0": "📸 Foto pintu besi / teralis — buktikan terpasang", "1": "📸 Foto pintu besi / teralis yang rusak"}
71	3	20	🚰 Dispenser air minum	Tersedia dispenser air minum untuk konsumen dan karyawan	1	0.0120	t	f	t	\N	rusak_only	Dispenser air minum untuk konsumen dan karyawan. Foto jika rusak.	{"1": "📸 Foto dispenser yang rusak", "2": ""}
74	4	23	🌐 Internet stabil minimal 10 Mbps	Koneksi internet stabil dengan kecepatan minimal 10 Mbps untuk operasional	1	0.0300	t	f	t	\N	rusak_only	Internet stabil minimal 10 Mbps untuk operasional. Foto jika rusak.	{"1": "📸 Foto kondisi internet / router", "2": ""}
76	4	25	🧑‍🍳 Pantry + alat makan	Tersedia pantry dan peralatan makan/minum untuk kebutuhan karyawan	1	0.0230	t	f	t	\N	rusak_only	Pantry dan alat makan minum untuk karyawan. Foto jika rusak.	{"1": "📸 Foto pantry / alat makan yang rusak", "2": ""}
78	5	27	⚡ Listrik stabil + backup daya (UPS/genset)	Listrik stabil dan tersedia backup daya (UPS atau genset) untuk operasional kritis	1	0.0280	t	f	t	\N	rusak_only	Listrik stabil dengan backup daya (UPS atau genset). Foto wajib.	{"1": "📸 Foto kondisi UPS / genset", "2": ""}
79	5	28	💻 Komputer/PC 1 unit per staf	Komputer/PC tersedia minimal 1 unit per staf yang berfungsi baik	1	0.0270	t	f	t	\N	rusak_only	Komputer PC minimal 1 unit per staf, berfungsi baik. Foto jika rusak.	{"1": "📸 Foto komputer yang rusak", "2": ""}
80	5	29	🖨️ Printer multifungsi (scan, copy, print)	Printer multifungsi (scan, copy, print) tersedia dan berfungsi dengan baik	1	0.0230	t	f	t	\N	rusak_only	Printer multifungsi scan copy print berfungsi baik. Foto jika rusak.	{"1": "📸 Foto printer yang rusak", "2": ""}
82	5	31	⚡ Daya listrik terpasang	Daya listrik terpasang sesuai kebutuhan minimal 1300 VA	7	0.0160	t	f	t	\N	rusak_only	Daya listrik terpasang minimal 1300 VA.	{}
83	5	32	🗂️ Lemari arsip / filing cabinet	Lemari arsip/filing cabinet tersedia untuk penyimpanan dokumen secara rapi	1	0.0140	t	f	t	\N	rusak_only	Lemari arsip filing cabinet untuk penyimpanan dokumen. Foto jika rusak.	{"1": "📸 Foto lemari arsip yang rusak", "2": ""}
84	5	33	📠 Printer dot matrix / LX (kertas rangkap)	Printer dot matrix/LX tersedia untuk cetak dokumen rangkap (kertas continous form)	1	0.0100	t	f	t	\N	rusak_only	Printer dot matrix LX untuk cetak dokumen rangkap continous form. Foto jika rusak.	{"1": "📸 Foto printer dot matrix yang rusak", "2": ""}
86	6	35	📦 Cashbox / laci uang	Cashbox/laci uang tersedia untuk penyimpanan uang tunai sementara yang aman	1	0.0310	t	f	t	\N	ada_rusak	Cashbox laci uang untuk penyimpanan tunai sementara. Foto wajib.	{"0": "📸 Foto cashbox — buktikan kondisi", "1": "📸 Foto cashbox yang rusak"}
\.


--
-- Data for Name: survey_question_types; Type: TABLE DATA; Schema: origo; Owner: postgres
--

COPY origo.survey_question_types (id, type_code, type_name) FROM stdin;
1	yesno	Yes/No dengan Rusak
2	binary	Ada/Tidak
3	condition	Layak/Rusak/Tidak
4	parkir	Level Parkir
5	tinggi_jalan	Tinggi Jalan
6	ukuran_ruang	Ukuran Ruang
7	listrik_daya	Daya Listrik
8	ada_tidak	Ada/Tidak polos
\.


--
-- Data for Name: survey_type_options; Type: TABLE DATA; Schema: origo; Owner: postgres
--

COPY origo.survey_type_options (id, type_id, opt_value, opt_label, weight_mult, is_no, sort_order) FROM stdin;
1	1	0	Ya ✅	1.00	f	1
4	2	0	Ada ✅	1.00	f	1
6	3	0	Layak ✅	1.00	f	1
14	5	0	Lebih tinggi 🔺	1.00	f	1
17	6	0	≥ 3x4m ✅	1.00	f	1
20	7	0	> 2200W ⚡	1.00	f	1
23	8	0	Ada ✅	1.00	f	1
2	1	1	Rusak ⚠️	0.50	t	2
7	3	1	Rusak ⚠️	0.50	t	2
3	1	2	Tidak ❌	0.00	t	3
5	2	2	Tidak ❌	0.00	t	2
8	3	2	Tidak ❌	0.00	t	3
19	6	2	Tidak ❌	0.00	t	3
24	8	2	Tidak ❌	0.00	t	2
9	4	0	5 (1+3)	1.00	f	1
10	4	1	4	0.75	f	2
11	4	2	3	0.50	f	3
12	4	3	2	0.25	f	4
13	4	4	1 (tdk ada)	0.00	t	5
15	5	1	Se level	0.60	f	2
16	5	2	Lebih rendah 🔻	0.20	t	3
21	7	1	1300-2200W	0.50	f	2
22	7	2	< 1300W	0.00	t	3
18	6	1	< 3x4m	0.50	f	2
\.


--
-- Name: kantor_checklist_data_id_seq; Type: SEQUENCE SET; Schema: origo; Owner: postgres
--

SELECT pg_catalog.setval('origo.kantor_checklist_data_id_seq', 8, true);


--
-- Name: survey_categories_id_seq; Type: SEQUENCE SET; Schema: origo; Owner: postgres
--

SELECT pg_catalog.setval('origo.survey_categories_id_seq', 7, true);


--
-- Name: survey_checklist_items_id_seq; Type: SEQUENCE SET; Schema: origo; Owner: postgres
--

SELECT pg_catalog.setval('origo.survey_checklist_items_id_seq', 100, true);


--
-- Name: survey_question_types_id_seq; Type: SEQUENCE SET; Schema: origo; Owner: postgres
--

SELECT pg_catalog.setval('origo.survey_question_types_id_seq', 8, true);


--
-- Name: survey_type_options_id_seq; Type: SEQUENCE SET; Schema: origo; Owner: postgres
--

SELECT pg_catalog.setval('origo.survey_type_options_id_seq', 24, true);


--
-- Name: kantor_checklist_data kantor_checklist_data_pkey; Type: CONSTRAINT; Schema: origo; Owner: postgres
--

ALTER TABLE ONLY origo.kantor_checklist_data
    ADD CONSTRAINT kantor_checklist_data_pkey PRIMARY KEY (id);


--
-- Name: survey_categories survey_categories_cat_code_key; Type: CONSTRAINT; Schema: origo; Owner: postgres
--

ALTER TABLE ONLY origo.survey_categories
    ADD CONSTRAINT survey_categories_cat_code_key UNIQUE (cat_code);


--
-- Name: survey_categories survey_categories_pkey; Type: CONSTRAINT; Schema: origo; Owner: postgres
--

ALTER TABLE ONLY origo.survey_categories
    ADD CONSTRAINT survey_categories_pkey PRIMARY KEY (id);


--
-- Name: survey_checklist_items survey_checklist_items_pkey; Type: CONSTRAINT; Schema: origo; Owner: postgres
--

ALTER TABLE ONLY origo.survey_checklist_items
    ADD CONSTRAINT survey_checklist_items_pkey PRIMARY KEY (id);


--
-- Name: survey_question_types survey_question_types_pkey; Type: CONSTRAINT; Schema: origo; Owner: postgres
--

ALTER TABLE ONLY origo.survey_question_types
    ADD CONSTRAINT survey_question_types_pkey PRIMARY KEY (id);


--
-- Name: survey_question_types survey_question_types_type_code_key; Type: CONSTRAINT; Schema: origo; Owner: postgres
--

ALTER TABLE ONLY origo.survey_question_types
    ADD CONSTRAINT survey_question_types_type_code_key UNIQUE (type_code);


--
-- Name: survey_type_options survey_type_options_pkey; Type: CONSTRAINT; Schema: origo; Owner: postgres
--

ALTER TABLE ONLY origo.survey_type_options
    ADD CONSTRAINT survey_type_options_pkey PRIMARY KEY (id);


--
-- Name: kantor_checklist_data uq_kantor_survey; Type: CONSTRAINT; Schema: origo; Owner: postgres
--

ALTER TABLE ONLY origo.kantor_checklist_data
    ADD CONSTRAINT uq_kantor_survey UNIQUE (kantor_code, survey_seq);


--
-- Name: survey_checklist_items survey_checklist_items_cat_id_fkey; Type: FK CONSTRAINT; Schema: origo; Owner: postgres
--

ALTER TABLE ONLY origo.survey_checklist_items
    ADD CONSTRAINT survey_checklist_items_cat_id_fkey FOREIGN KEY (cat_id) REFERENCES origo.survey_categories(id) ON DELETE CASCADE;


--
-- Name: survey_checklist_items survey_checklist_items_type_id_fkey; Type: FK CONSTRAINT; Schema: origo; Owner: postgres
--

ALTER TABLE ONLY origo.survey_checklist_items
    ADD CONSTRAINT survey_checklist_items_type_id_fkey FOREIGN KEY (type_id) REFERENCES origo.survey_question_types(id);


--
-- Name: survey_type_options survey_type_options_type_id_fkey; Type: FK CONSTRAINT; Schema: origo; Owner: postgres
--

ALTER TABLE ONLY origo.survey_type_options
    ADD CONSTRAINT survey_type_options_type_id_fkey FOREIGN KEY (type_id) REFERENCES origo.survey_question_types(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict qBmojo8KN5JQ8oWNEvaUDaIIUSc4iUIjA8Igy5sjhFZ2NaTstyx5bU9oYFwZ8Wb

