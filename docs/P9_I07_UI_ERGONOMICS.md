# P9-I07 — Tasarım maketleriyle görsel/ergonomik uyum incelemesi

## İnceleme sınırı

Kaynak: P9-I06 Tkinter ana ekranı, I02 anotasyon editörü, I03 modül formları, I04 inceleme/kanıt gezgini ve daha önce oluşturulan 8 görsel tasarım maketi (Genel Bakış, Görüntü Yükleme, Analiz Planı, Kalibrasyon, Fiziksel Ölçümler, Kanıt İnceleme, Bağımlılık Grafiği, Rapor Dışa Aktarma).

**Yöntem:** Kod bileşenleri ve kullanıcı akışı, görsellerdeki bilgi mimarisiyle karşılaştırıldı. Gerçek masaüstü ekranlarının aynı çözünürlük/DPI değerlerinde piksel karşılaştırması ve bağımsız kullanılabilirlik gözlemi **yapılmadı**. Maketlerdeki örnek performans yüzdeleri, sahte vaka dosyaları, yanlış modül adları veya otomatik doğrulama statüleri ürüne aktarılmayacak.

## Ekran bazında açıklıklar

| Sayfa | Desteklenen işlev | Makete göre eksik | Öncelik |
|---|---|---|---|
| Genel Bakış | Gerçek sayaçlar, beş aşama, seçili görüntü, sentetik E01→E03 | Modül odaklı panel düzeni ve tutarlı küçük ekran yerleşimi | P1 |
| Görüntü Yükleme | İçe alma, hash, önizleme, envanter | Toplu sürükle-bırak, filtre, histogram, dosya özniteliği paneli | P2 |
| Analiz Planı | 27 komut, JSON formları ve önkoşul planlayıcı | Kart/kuyruk hiyerarşisi ve görünür engelleme özetleri | P1 |
| Kalibrasyon | I02 çizim, kalibrasyon JSON, modül bağlantıları | Görüntü üzerinde VP/kamera matrisi/reprojeksiyon inspector | P1 |
| Fiziksel Ölçümler | I02 ve I04 katmanları, CLI çıktıları | Ölçüm-artık-belirsizlik tablosunun görüntüyle aynı yerde olması | P1 |
| Kanıt İnceleme | E01/E02/E03 raporları, kullanıcı tanımlı bağlantı | Bulguya tıklayınca bölgeye odaklanma, daha zengin belirsizlik görselleri | P1 |
| Bağımlılık Grafiği | E03'e dayalı gerçek düğüm/kenarlar | Yakınlaştırma, pan, düğüm odak, filtre ve kenar açıklamaları | P2 |
| Rapor Dışa Aktarma | JSON/HTML ve hash'li ZIP | PDF, gerçek kriptografik imza, sayfa önizleme (yapılmadı) | P2 |
| Ayarlar | Yerel proje ve doğrulama sınırları | Ölçek/klavye/erişilebilirlik seçeneği (9. sayfa; maket yok) | P1 |

## Bu sürümdeki gerçek düzeltmeler

1. **P0 — Anotasyon yolu:** I02 editörün kaydettiği \`manifests/annotations_<SHA>.json\` artık I04 gezgininde yüklenir; eski \`annotations/*.json\` uyumluluğu korunur. Yalnız aynı görüntü SHA-256 ve gerçek piksel çözünürlüğüne ait işaretlemeler görünür.
2. **P0 — Görüntü bağlamı:** Ana ekranda seçili görüntünün SHA-256 değeri, I04 inceleme penceresine aktarılır. Geçersiz seçime başka görüntüyle sessiz geri dönüş yapılmaz.
3. **P1 — Küçük ekran:** Ana Tkinter içerik alanı dikey kaydırılabilir. Önceki sabit 1400×870 ekranda taşan uzun sayfalardaki bölümler korunur.
4. **P1 — Klavye:** Ctrl+1..9 sayfa; Ctrl+N yeni proje; Ctrl+O görüntü ekleme; F5 yenileme; PageUp/PageDown sayfa kaydırma.

## Bilimsel doğruluk ve kabul

- Maketlerdeki \`%94 güven\`, \`AI üretim olasılığı\`, \`dijital imzalandı\`, \`PDF hazır\` gibi **kaynaklanmamış veya henüz kodlanmamış** durumlar **üretilmez**.
- JPEG gibi işlenmiş dosyalar gerçek sensör kimliği için RAW doğrulaması yerine geçmez.
- Sentetik CI Windows üzerinde çalışan Python testleridir; **etkileşimli Windows 10/11 UI kabulü değildir**.
- Kod incelemesi ve sentetik regresyonlar, maketlerin birebir görsel veya ergonomik kabulünü **kapamaz**.

## Nihai görsel değerlendirme kapısı

1. 1366×768 ve 1920×1080: 100% / 125% / 150% DPI, uzun sayfa kaydırma.
2. Klavye odak sırası; yazı kontrastı, seçili modül durumları, hata paneli görünürlüğü.
3. Seçili görüntü → anotasyon → kaydedilmiş katman → E03 bulgu → rapor yönlendirmesi.
4. Bozuk görüntü/kalibrasyon/manifest, kayıp referans ve kullanıcının iptal ettiği işlemlerin güvenli durması.
5. Anotasyon ölçek/dpi dönüşümünde piksel koordinatlarının değişmemesi.

Bu kapıların sentetik desktop smoke/ekran görüntüsü karşılaştırması özellik testidir; **nihai gerçek Windows cihaz kabulü ve gerçek kamera performans testi en son** yapılır. Bunlar tamamlanmadan *birebir görsel uyum* iddiası kurulmaz.
