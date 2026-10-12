# P0/G01 — İlk deney kaydı (2026-10-09)

## Koşullar

- Windows üzerinde çalıştırılabilir proje hedefleniyor; ilk doğrulama Linux konteynerinde.
- Python yerel kurulu paketleri: NumPy, SciPy, OpenCV, pytest.
- Ortamda ağ erişimi yoktu; `pip install -e '.[dev]'` komutu izole build
  bağımlılığını indiremedi. Testler `PYTHONPATH=src` üzerinden çalıştırıldı.
- Kod, gerçek görüntüler için fiziksel tutarlılık kararı veya AI sınıflandırması üretmez.

## Test kanıtı

- `PYTHONPATH=src pytest -q`: **10 passed**.
- `PYTHONPATH=src python -m aiforensics benchmark --trials 100 --out outputs/benchmark`
- 100 sentetik deneme; 35 aynı VP'ye yönelen çizgi, 20 bağımsız aykırı çizgi;
  uç noktalara 0.75 piksel Gaussian gürültüsü.
- Başarılı VP tahmini: 100/100 (yalnız seçilen sentetik dağılımda).
- Medyan konum hatası: 0.4611 px; 90. yüzdelik: 0.7464 px;
  maksimum: 1.3344 px.
- Bilinen VP (640,360) olan 1280x720 render koridorda:
  VP tahmini yaklaşık (640.131,359.690), çizgi tespitleri: 319,
  birleştirme sonrası destekleyen çizgiler: 126.
- Sayılar `outputs/benchmark/synthetic_benchmark.json` ve
  `outputs/demo/corridor_analysis/g01_report.json` içinden türetilmiştir.

## Bulgular

- Başlangıçta aynı VP etrafında iki yakın hipotez çıktı; bunlar birleştirildi.
- Görüntüde başka gerçek doğrultular bulunabileceğinden, model dışı çizgiler
  fiziksel sahteciliğin kanıtı değildir.
- Sabit sentetik senaryo ve kontrollü çizgi seçimi nedeniyle bu sonuçlar
  AI tespitinde false positive/negative oranı olarak sunulamaz.

## Gate durumu

| Gate | Ölçüt | Durum |
|---|---|---|
| P0-UNIT | Temel matematik fonksiyonları testli | PASS (10 test) |
| P0-REPRO | Seed + kod + komut + ölçüm JSON'u | PARTIAL (dependency lock/CI açık) |
| G01-SYNTH | Bilinen VP'de sabit senaryo doğrulaması | PASS (seçilmiş senaryo) |
| G01-REAL | Bağımsız gerçek kamera validasyonu | OPEN |
| G01-FPR | Gerçek fotoğraflarda yanlış alarm ölçümü | OPEN |
| G01-INFINITY | Sonsuz VP / distorsiyon modellemesi | OPEN |
| AI-ORIGIN | Üretici/sahte karar sistemi | NOT IN SCOPE |

Önceden belirlenmemiş sayısal eşikleri sonradan başarı ölçütü olarak sunmayın.
İlerideki kabul testi için veri seçimi, test planı ve eşikler deney öncesinde
kesinleştirilecektir.
