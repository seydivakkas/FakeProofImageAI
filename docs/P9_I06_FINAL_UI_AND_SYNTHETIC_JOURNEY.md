# P9-I06 — Arayüz uyumu ve kontrollü sentetik uçtan uca akış

Bu iş paketi, v0.33.0 masaüstü kabuğunu önceki koyu tema tasarım maketlerinin temel hiyerarşisine yaklaştırır: gerçek proje sayaçları, beş adımlı gezinme, geçerli görüntü SHA-256 kontrolü, doğrudan anotasyon/kalibrasyon ve modül planlayıcısı, E01/E02/E03 kanıt gezgini.

## Gerçek kullanıcı eylemleri

1. Yerel proje seç veya oluştur.
2. Dosya içe aktar; kaynak doğrulaması yapılmış sayılmaz. Görüntü seç.
3. Piksel anotasyonları, kalibrasyon taslakları veya bağımsız ölçüm manifestleri oluştur.
4. Modülün kendi önkoşullarını sağlayarak P1–P7 çalıştır. RGB görüntü yüklemek bütün fizik motorlarına otomatik kanıt sağlamaz.
5. E01/E02/E03 için kontrollü sentetik örneği ana ekrandan başlat veya kendi ölçüm manifestlerini modül formlarında tek tek çalıştır.
6. E03 HTML/JSON ve SHA-256 kayıtlarını incele, ZIP olarak dışa aktar.

## E01 → E02 → E03 demo senaryosu

Yerel, üretilmiş üç skaler ölçüm girdisi, ilk ikisi ortak sentetik kaynağa ait olacak şekilde tasarlanmıştır. Ham JSON içerik SHA-256 ile anlık görüntüye alınır; aynı anlık görüntü üç mevcut CLI motoruna geçirilir. Zincir her aşamada kaynak hash'i ve çıktı şemalarını denetler. Başarısız aşamada durur; süreç raporu exports/p9_i06_chain_*.json içinde saklanır.

Komut:

    python scripts/p9_i06_synthetic_e2e.py --workspace outputs/p9_i06_demo

Testler:

    python -m pytest -q

Masaüstü:

    fakeproof-desktop

## Bilimsel ve ürün sınırı

**Bu bir sentetik yazılım entegrasyonudur**, aynı görüntünün P1–P8'de otomatik analiz edildiği veya fiziksel kalibrasyonların doğrulandığı anlamına gelmez. Koşullu hipotez reddi fotoğrafın AI kökenli olduğunu kanıtlamaz. Raporda AI köken olasılığı yoktur.

Tasarımlarla birebir piksel karşılaştırmalı ekran ölçümü, ekran okuyucu/klavye erişilebilirliği, gerçek Windows 10/11 .exe kurulum ve GPU/donanım kabulü, gerçek fotoğraf ve bağımsız kamera ölçümleri sona bırakılmıştır.
