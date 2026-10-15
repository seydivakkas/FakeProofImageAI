# P9-I09 — v0.37.0 görsel karşılaştırma ve bilimsel kabul sınırı

**İnceleme:** Daha önce hazırlanmış yüksek sadakatli ekran maketleri ↔ gerçek v0.37.0 Tkinter pencereleri.

## İnceleme kanıtı

- [Boş proje dokuz ekran / 1366x768 + 1920x1080](https://github.com/seydivakkas/FakeProofImageAI/actions/runs/38793469603): ekran ve boşluk davranışı.
- [Gerçek CLI ile üretilmiş kontrollü sentetik G02/G04/E01-E02-E03 panelleri / iki çözünürlük](https://github.com/seydivakkas/FakeProofImageAI/actions/runs/38794197243): kalibrasyon/ölçüm/kanıt panelleri, kaydırılmış bilimsel grafik alanları, kullanıcı ROI yakınlaştırması.
- [P9-I09 son VP etiket yerleşimi düzeltmesi](https://github.com/seydivakkas/FakeProofImageAI/commit/b96af7b44ad04c0601c1fb05bced93dc7f9c7bd7) ve ilgili CI: [sentetik görsel](https://github.com/seydivakkas/FakeProofImageAI/actions/runs/38794892413).
- Bu görüntüler **Ubuntu/Xvfb sanal ekranda** kaydedildi; gerçek Windows 10/11 deneyimi değildir. Maketlerin farklı tipografik/yerleşim tasarımı birebir doğrulanmadı.

## Kaynaklı görsel farklar

| Ekran | Maket hedefi | Kodla çalışan / görülen durum | Açık fark |
|---|---|---|---|
| Kalibrasyon | Geniş kaynak fotoğrafı + VP çizgileri + K matrisi + reprojeksiyon | Kaynak görüntü önizlemesi, çizim editörüne geçiş, kaydedilmiş G01/G02 VP noktaları ve K, G04 train/holdout ayrı sayısal grafik | Doğrulanmamış G02 VP'leri otomatik fotoğraf üstüne çizilmiyor; maketin tek panel içi ölçüm/kalibrasyon etkileşimi henüz birebir değil |
| Fiziksel ölçümler | Fotoğrafa bindirme + veri tablosu + artık ve hata aralığı | I02/I04 görüntü ve anotasyonlar; P1–P7 modül menüsü; kaynaklı E03 artık grafiği; pikseller/dereceler için ayrı sekmeler | Birçok modülün fiziksel artıklarını tek bir standart kamera sahnesine bağlayan gerçek kaynak eşleştirmesi yok |
| Kanıt inceleme | Tekil iddia, belirsizlik, bağımlılık, kaynak görüntü ve ROI aynı çalışma alanında | E03 rapor tablosu; ilgili kaynak bağımlılık gezgini; açık kullanıcı bağlantısı zorunlu ayrı ROI çizim/yakınlaştırma penceresi | Bulgu→kaynak ROI ayrı pencerede; otomatik resim bölgesi tahmini yapılmıyor ve yapılmış gibi gösterilmiyor |
| Genel yerleşim | Koyu tema, katman, kontroller, çok panelli ergonomi | Önceki P9-I08 düzeni korunur; P9-I09 bilimsel sekmeleri eklenmiştir | 100/125/150% DPI, klavye odak sırası ve Windows kullanıcı gözlem testi açık |

## Dürüst kabul kararı

- P9-I09 **sentetik yazılım entegrasyonunda PASS** (CI koşulları sağlanınca).
- Bilimsel kamera kalibrasyonu ve görüntü kaynağı **NOT VERIFIED**.
- Maketle **birebir piksel / Windows ergonomi uyumu NOT ACCEPTED**.
- Bağımsız gerçek kamera, gerçek fotoğraf hata oranı ve gerçek Windows cihaz kabulü **en son**.
- Fiziksel tutarsızlık AI kökenini kanıtlamaz; AI-orijin ihtimali hiç hesaplanmıyor.
