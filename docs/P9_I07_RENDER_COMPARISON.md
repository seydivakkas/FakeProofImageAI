# P9-I07 — Gerçek Tkinter render ile maketlerin karşılaştırması

**Karar: GÖRSEL UYUM KABUL EDİLMEDİ.** Bu rapor işlevsellik değil, arayüz ve ergonomi farklarını kaydeder.

Kaynak: Önceden hazırlanmış sekiz ekran tasarımı. Karşılaştırılan arayüz: v0.35.0 masaüstü Tkinter, **boş sentetik projede** Ubuntu/Xvfb sanal ekranında 1366×768 ve 1920×1080 çözünürlükte 9 sayfa. DPI ölçeklendirme, etkileşimli Windows 10/11 kullanıcı kabulü ve bağımsız gerçek fotoğraf deneyleri **yapılmadı**.

Görüntü artefaktı: [GitHub Actions — P9-I07 synthetic UI screenshots](https://github.com/seydivakkas/FakeProofImageAI/actions/runs/38784341605). Bu koşum 18 PNG ekran görüntüsü ve boyut/SHA indeksi üretmiştir.

## Sekiz maket için kaynaklı farklar

| Sayfa | Mevcut Tkinter render | Hedefle fark | Öncelik |
|---|---|---|---|
| Genel Bakış | 4 gerçek sayaç, 5 adımlı akış ve sağ panel | 8 modül kartı, büyük analiz görseli, kanıt ve analiz panelleri aynı hiyerarşide değil | P0 |
| Görüntü Yükleme | Dosya düğmesi ve tablo | Drop-zone, metadata inceleyici ve histogram yok | P1 |
| Analiz Planı | 27 modül tablosu, I03 ayrı pencerede | Seçilebilir modül kartları ve kuyruğun görünürlüğü düşük | P1 |
| Kalibrasyon | Editöre açılan ana ekran | VP, kamera matrisi, reprojeksiyon paneli aynı sayfada yok | P1 |
| Fiziksel Ölçümler | I02/I04 butonları ve gerçek çıktı tablosu | Büyük görüntü/katmanlar/artık grafiği üçlüsü tek sayfada değil | P1 |
| Kanıt İnceleme | E01/E02/E03 seçenekleri ve rapor listesi | Bulgu + kaynak görsel + gerekçe yan yana değil; I04 gezgini ayrıdır | P1 |
| Bağımlılık Grafiği | Veri yoksa dürüst boş durum gösterimi | E03 varlığında açılan grafik ayrı pencerede; renk/zoom/filtre sınırlı | P2 |
| Rapor Dışa Aktarma | ZIP ve mevcut JSON/HTML | PDF önizleme, dijital imza henüz yok | P2 |
| Ayarlar (ek) | Yerel ortam ve kabul sınırları | DPI/erişilebilirlik tercihi yok; bu sayfanın tasarım maketi yok | P2 |

## Kod düzeyinde kapatılan P0/P1 boşlukları

- I02'nin kanonik \`manifests/annotations_<SHA>.json\` kaydı, I04 inceleme katmanına bağlandı; eski anotasyon kayıtları desteklendi.
- SHA ve özgün görüntü çözünürlüğü uyuşmayan anotasyonlar gösterilmiyor.
- Seçilen görüntü inceleme penceresinde korunuyor; geçersiz SHA sessizce başka görüntüye aktarılmıyor.
- Kaydırılabilir ana çalışma alanı ve klavye kısayolları eklendi.
- 962 test PASS ve 1 SKIP / ortam; [4/4 GitHub CI başarılı](https://github.com/seydivakkas/FakeProofImageAI/actions/runs/38784341548).

## Önümüzdeki kabul kapısı

1. Maketle yakın görsel hizalama için ana sayfa P1–P8 panelleri ve gerçek kaynaktan türetilmiş analiz görseli/özetleri; uydurma güven yüzdesi veya AI kökeni puanı **yok**.
2. I02 / I04 düzenleyici bağlamlarının seçili görüntüde açılması ve yan yana bilimsel panel gösterimi.
3. 1366×768 ve 1920×1080, farklı DPI oranlarında gerçek screenshot/odak sırası/kontrast ve engel senaryosu incelemesi.
4. En son gerçek Windows cihaz kabulü ve bağımsız gerçek görüntü ölçümleri.

**Not:** Boş sentetik projede boş rapor/kanıt alanı doğru davranıştır; görüntüde kanıt olmadığı halde sayıları doldurmak yasaktır. Başarılı CI ve sanal ekran yakalaması, gerçek kamera veya gerçek Windows ergonomi doğrulaması değildir.

Kod: [P9-I07 commit](https://github.com/seydivakkas/FakeProofImageAI/commit/c99296720a2c2db25ac31ce0b0ee437e5ca1b0f0).