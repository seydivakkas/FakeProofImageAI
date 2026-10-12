# P1-G02 deney kaydı — 9 Ekim 2026

## Başlangıç ve kaynak

Kaynak proje: P0+G01 ZIP (`AI_Image_Forensics_P0_G01.zip`). Başlangıçta G01 testleri 10/10 geçti.

EyeLib proje kodları incelenmiştir: `matlab/computeKviaIAC.m`, `matlab/computeRviaVanishingPointsandK.m` ve `matlab/computeCameraHeight.m`; **hiçbir MATLAB fonksiyonu projeye kopyalanmamıştır**.

## Yeni algoritma

`calibration.py`: üç sonlu ortogonal VP'nin 3×3 doğrusal çözümü, `f²>0`, kamera `K`, SVD ile `SO(3)` rotasyon, deterministik fail-closed, JSON raporu.

`calibrate_from_g01_groups`: kullanıcı tarafından üç fiziksel ortogonal aile olarak etiketlenmiş Nx4 çizgi parçalarını G01 ile tahmin ederek G02'ye geçirir. Etiketin doğruluğu görüntüden kanıtlanamaz.

## Sentetik test sonuçları

- Otomatik `pytest`: **22 passed** (eski G01: 10; yeni G02: 12).
- Sabit tohumlarla 50 G01→G02 deneyinde: **50 başarı, 0 INDETERMINATE**.
- Median focal absolute error: **3.5536 px**; p90: **7.4004 px**.
- Median principal point position error: **8.4331 px**; p90: **13.7592 px**.
- Düzenek: tek kamera, `f=900px`, `1280×720`, doğrultu başına 45 çizgi, uç koordinatlara Gauss gürültüsü σ=0.35 px, haricen doğru olarak etiketli ortogonal doğrultular, RANSAC.

Ayrıntılı machine-readable bulgular: `outputs/g02_benchmark/g02_benchmark.json`. Testler kontrollü veri içindir; gerçek fotoğraf ve AI tespit performansı ölçülmedi.

## Açık eksikler

- Sonsuz VP; fisheye, panorama ve lens distorsiyonlarının kalibrasyonu.
- Yön ailelerinin semantik/düzlemsel doğrulanması.
- Bağımsız dış kamera referansı ile doğrulama.
- VP ölçüm belirsizliğinin K/R kovaryansına propagasyonu.
- Gerçek fotoğraf benchmark'ı ve yanlış alarm analizi.
