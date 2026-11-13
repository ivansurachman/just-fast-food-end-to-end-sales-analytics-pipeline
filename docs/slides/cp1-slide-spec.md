# Spesifikasi slide Check Point 1

Untuk presentasi Check Point 1 (PPT dikumpulkan 14 Nov, dipresentasikan 15 Nov). Struktur mengikuti tiga bagian template bootcamp: Introduction, Overview Project, Main Project. Teks di bawah adalah draf siap tempel. Desain dan tata letak sepenuhnya milikmu. Angka berasal dari `docs/data-profile.md` (45 hari, skala 0,1, seed 42) kecuali disebut lain.

Dokumen ini sengaja berbahasa Indonesia karena isi slide akan dibawakan dalam bahasa Indonesia. Dokumen lain di repo tetap berbahasa Inggris.

## Slide per slide

| # | Slide | Harus berisi | Visual dan penempatan | Status |
|---|---|---|---|---|
| 1 | Judul | Nama proyek "Just Fast Food: analitik penjualan end-to-end", namamu, bootcamp, Check Point 1, tanggal | Tidak ada | Butuh namamu dan tanggal |
| 2 | Introduction | Profil diri, pendidikan (gelar, institusi, konsentrasi), pengalaman kerja (peran, proyek, pencapaian) | Foto opsional di kiri | Butuh input darimu |
| 3 | Overview Project | Satu baris per proyek bootcamp: judul, deskripsi singkat (tujuan, analisis, hasil, teknologi). Proyek ini jadi baris terakhir | Tabel selebar slide | Butuh daftar proyek bootcamp lainnya |
| 4 | Latar belakang proyek | Jaringan makanan cepat saji fiktif, 100+ cabang di seluruh Indonesia, sekitar 120 ribu order per hari, lima channel penjualan. Laporan terpecah per channel dan datang terlambat, duplikat, atau kotor. Tujuan: satu tampilan penjualan yang bisa dipercaya dan pipeline yang bisa diulang. Penerima manfaat: operasional, manajer wilayah, marketing, keuangan | Tidak ada, atau deretan ikon channel kecil | Teks siap |
| 5 | Problem statement dan ukuran sukses | Masalah: (1) penjualan bersih per channel setelah komisi platform belum diketahui, (2) jam sibuk per cabang tidak terlihat, (3) biaya promo dibanding efeknya tidak jelas, (4) data yang terlambat dan kotor membuat angka harian tidak bisa dipercaya. Ukuran sukses: 11 metrik P1 terjawab, pipeline harian berjalan sukses end to end, setiap cacat yang disuntikkan terdeteksi (9 dari 9 saat ini) | Kanan: tabel 11 metrik P1 (M1, M2, M3, M4, M6, M7, M8, M10, M12, M15, M17) | Target di bawah perlu persetujuanmu |
| 6 | Data platform understanding | Sumber, penyimpanan, transformasi, dan penyajian, masing-masing satu kalimat. Semua layanan jalan di container Podman dengan batas memori 9 GB. Dashboard memakai Metabase | **Selebar slide: `architecture.png`** | Desain v1, final setelah Phase 3 |
| 7 | Data understanding: sumber dan struktur | Pengumpulan: generator Python ber-seed, CSV harian ke penyimpanan kompatibel S3. Entitas dan grain: orders (satu baris per order), order_items (satu per baris item), order_changes (satu per refund), 4 tabel dimensi. Volume: skala penuh sekitar 120 ribu order dan 290 ribu baris item per hari, sekitar 44 juta order per tahun. Jendela development: 541 ribu order, 1,3 juta baris item, 109 MB | Kiri: tabel entitas. Kanan: screenshot isi awal `orders.csv` (kamu ambil sendiri) | Teks siap, screenshot dibutuhkan |
| 8 | Data understanding: pola data | Puncak di jam makan siang dan makan malam, order online condong ke malam, kenaikan di akhir pekan, online setengah dari jumlah order tetapi porsinya lebih kecil dari penjualan bersih | **Kiri: `chart_hourly_share.png`. Kanan atas: `chart_channel_mix.png`. Kanan bawah: `chart_weekday.png`** (atau satu grafik per slide) | Siap |
| 9 | Data understanding: kualitas data | Sembilan cacat ala produksi disuntikkan: baris duplikat, order terlambat, cabang-hari hilang, label pembayaran kosong atau tidak konsisten, total tidak sama dengan jumlah item, menu tidak dikenal, referensi platform kosong. Profil data menemukan semuanya, dan jumlahnya sama dengan manifest generator | Tabel: cacat, terdeteksi, disuntikkan (salin dari bagian 7 `data-profile.md`) | Siap |
| 10 | Data modeling | Star schema: dua tabel fakta (order, baris order), satu fakta cakupan cabang-hari, satu fakta kualitas data, lima dimensi. Dipartisi per tanggal order. Refund diatribusikan ke tanggal order, jadi satu refund menulis ulang partisi order tersebut | **Selebar slide: `er_diagram.png`**, atau pecah panel A dan B ke dua slide | Siap |
| 11 | Transformasi dan pertimbangan | Kenapa batch: sekitar 4 sampai 5 order per detik saat puncak, pelaporan harian, refund bisa datang sampai 8 hari kemudian. Pilihan engine: DuckDB + dbt muat di budget 9 GB (Trino saja diperkirakan sekitar 2,6 GB). Lapisan: CSV mentah, bronze Parquet, silver bersih, gold star schema, mart di PostgreSQL | Kiri: tabel keputusan (opsi, RAM, putusan). Kanan: strip lapisan | Teks siap, strip kamu gambar sendiri |
| 12 | Rencana dan risiko | Garis waktu ke 22 Nov (pipeline end to end) dan 29 Nov (review). Risiko: batas 9 GB di Podman dan WSL2, integrasi S3 belum teruji, setup Windows belum teruji | Bilah garis waktu sederhana dan tabel risiko tiga baris | Teks siap |
| 13 | Yang sudah selesai dan berikutnya | Selesai: generator dengan 39 tes, ber-seed dan dapat direproduksi, repo dengan riwayat commit, data model, data dictionary, profil data. Berikutnya: infrastruktur, DAG, model dbt, dashboard | Tiga screenshot kecil (kamu ambil sendiri): `git log --oneline`, ringkasan `pytest`, hasil menjalankan `jff-gen generate` | Screenshot dibutuhkan |

## Daftar gambar

| File (di `docs/`) | Dipakai di slide | Penempatan | Catatan |
|---|---|---|---|
| `slides/architecture.png` dan `.svg` | 6 | Selebar slide | Sumber `slides/architecture.dot`, ubah lalu render ulang dengan Graphviz |
| `er_diagram.png` dan `.svg` | 10 | Selebar slide, atau panel A dan B di dua slide | Sumber `er_diagram.dot`, render dengan `neato -n2` (tata letak tetap) |
| `slides/chart_hourly_share.png` | 8 | Kiri | Buat ulang dengan `slides/make_charts.py` |
| `slides/chart_channel_mix.png` | 8 | Kanan atas | |
| `slides/chart_weekday.png` | 8 | Kanan bawah | |

File SVG bisa diwarnai ulang di PowerPoint agar cocok dengan desainmu.

## Yang masih kamu perlu siapkan

1. File template slide, kalau bootcamp mewajibkannya.
2. Namamu, pendidikan, dan pengalaman kerja (slide 2).
3. Daftar proyek bootcamp lainnya dengan deskripsi satu baris masing-masing (slide 3).
4. Screenshot dari mesinmu: isi awal `orders.csv`, `git log --oneline`, ringkasan `pytest`, dan hasil menjalankan `jff-gen generate` (slide 7 dan 13).
5. Konfirmasi bagian template mana yang diwajibkan di Check Point 1. Slide 11 dan 12 melewati tahap Design, jadi buang kalau mentor hanya meminta dataset, diagram, data model, dan repo.
6. Persetujuan atas usulan target sukses untuk slide 5: pipeline harian berhasil minimal 95% hari pada jendela pengujian, data kemarin tersedia di dashboard pada jam pagi yang ditetapkan, dan deteksi cacat tetap 9 dari 9.

## Catatan yang sebaiknya jujur dinyatakan di slide

- Arsitektur masih desain v1. Belum pernah dijalankan, dan angka RAM adalah estimasi.
- Menjalankan generator sebagai DAG Airflow masih usulan, belum dikonfirmasi.
- Semua data sintetis, jadi insight mencerminkan asumsi generator, bukan pelanggan nyata.
