# P9-I01 — Sistem genelinde arayüz ve modül entegrasyonu

## Gerçek çalışan ilk Windows-öncelikli masaüstü kabuk

\`fakeproof-desktop\` veya \`python -m aiforensics.desktop_app\` komutu,
Python standart kitaplığındaki **Tkinter** ile çevrimdışı çalışır.
JPEG/TIFF önizlemesi için \`pip install -e ".[desktop]"\` (Pillow) kullanılabilir.

### Dokuz ekran ve gerçek eylemleri

| Ekran | Çalışan işlev |
|---|---|
| Genel Bakış | Proje, veri ve çalışma geçmişi |
| Görüntü Yükleme | Seç, kopyala, SHA-256, tekrar dosya ayırımı, önizleme |
| Analiz Planı | 24 fizik + E01/E02/E03; gerçek CLI komutlarının seçimi |
| Kalibrasyon | Harici JSON dosyasını projeye kaydet; G02/G04/O01'e git |
| Fiziksel Ölçümler | Fizik motorlarının JSON/görsel çıktılarını incele |
| Kanıt İnceleme | E01/E02/E03 kanıt raporlarını bul / HTML aç |
| Bağımlılık Grafiği | Yalnız E02/E03 gerçek lineage gruplarını göster |
| Rapor Dışa Aktarma | Seçilen çalışma dosyaları ve SHA-256 listesiyle ZIP |
| Ayarlar | Yerel proje, köken ve kabul durumu |

### Uygulama mimarisi

\`\`\`text
Tkinter UI (desktop_app.py)
    ↓
Project + allowlisted CLI bridge (desktop_core.py)
    ↓ subprocess(shell=False)
aiforensics CLI → P1..P7 existing physics engines
                     P8-E01 → E02 → E03
    ↓
project/runs/<run_id>/ execution.json + real module outputs
\`\`\`

G01 tek bir RGB görüntüdeki doğrularla keşif analizi yapabilir. Diğer modüller, kılavuzlarında açıklanan bağımsız ölçüm/kalibrasyon JSON girdilerini bekler. Görüntü yüklenince P2–P8'in tümünün otomatik çalıştığını **iddia etmiyoruz**.

Yalnız allowlist'te yer alan komutlar çalışır; kullanıcı girdisi asla shell'e geçirilmez. Hatalar, süre aşımı, stdout/stderr ve kaynak SHA-256 kaydedilir.

### Halen eksik olanlar

* Tasarım görsellerindeki ileri seviye çizgi/ROI anotasyon editörü ve overlay interaksiyonları;
* Tüm fizik motorları için JSON form oluşturucu ve uçtan uca çalışma planlayıcı;
* PDF ve kriptografik dijital imza;
* Bağımsız gerçek görüntü/kalibrasyon hata oranı kabulü;
* Windows 10/11 üzerinde gerçek kullanıcı kurulumu ve etkileşimli kabul.

HTML/JSON E03 raporu ve ZIP dışa aktarımı kullanılabilir; diğer seçenekler uygulanmamıştır. Birleşik raporda \`NO_AI_ORIGIN_CONCLUSION\` korunur.

**Sıra:** Fonksiyonel masaüstü iskeleti → anotasyon/manifest editörleri ve otomatik bağımlılık çözümü → modül uçtan uca entegrasyonu → real-camera / Windows end-user acceptance en son.
