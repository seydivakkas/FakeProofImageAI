# P9-I02 — Görüntü anotasyon ve ölçüm editörü

## Amaç ve sınırlama
P9-I01 Tkinter masaüstü uygulamasının **Kalibrasyon** ve **Fiziksel Ölçümler** sayfalarından açılan gerçek çizim editörü. Windows-first / offline-first. PIL/Pillow `[desktop]` opsiyonel bağımlılığı yüklenmelidir.

**Bu bir fizik doğrulayıcısı değildir.** İşaretlemeler yalnız kullanıcı tarafından çizilen 2B piksel geometrisidir. Kalibre edilmeyen piksel uzunlukları metreye çevrilmez; işaretli X/Y/Z çizgilerinden 3B ortogonalliğin doğrulandığı ilan edilmez.

## Etkileşimler
- Nokta, çizgi, çoklu çizgi, çokgen, dikdörtgen ROI; tüm noktalar özgün görüntü piksel koordinatlarında saklanır.
- Pan, tekerlek ile zoom, görüntüye sığdırma; geometri/ölçüm yakınlaştırma değişikliklerinden etkilenmez.
- Çizgi ve çokgeni seçme, köşe tutamağını ve çizgiyi sürükleyerek düzenleme.
- Undo/redo, silme, görüntü SHA-256 ve çözünürlük kontrolüyle tekrar açma.
- Piksel uzunluğu, piksel alanı; **metrik kalibrasyon yok**.
- Yalnız çizgiler için kullanıcı tarafından seçilmiş X/Y/Z etiketleri.
- X/Y/Z ailelerinde en az ikişer çizgi olduğunda `image_shape_hw` / `orthogonal_groups` alanlarıyla G02 formatında **doğrulanmamış taslak** JSON dışa aktarımı.

## Kayıt/şema
`fakeproof.annotations.v1`: `coordinate_space=original_image_pixels`, `image_sha256`, `image_size_wh`, `marks`, `source_type=user_annotation_unverified`, `metric_scale_verified=false`, `decision=NO_AI_ORIGIN_CONCLUSION`.
Dosyalar `<workspace>/<project>/manifests/annotations_<sha256>.json` yolunda atomik olarak yazılır. Farklı görüntü/SHA-256 veya değiştirilmiş doğrulama bayraklarıyla açılmaz. G02 taslağı kaydetmeden önce ayrıca kullanıcı uyarısı gösterilir.

## Kullanım
```powershell
python -m pip install -e ".[desktop,dev]"
fakeproof-desktop
```

1. Görüntü Yükleme sayfasından PNG/JPEG/TIFF görüntü ekleyin.
2. Kalibrasyon → **Görüntü Üzerinde Kalibrasyon Çiz** veya Fiziksel Ölçümler → **Görüntü Üzerinde Fiziksel Ölçüm Yap**.
3. Çizimleri düzenleyip **Kaydet**. Veriler özgün piksel koordinatlarında tutulur.
4. G02 taslağı oluşturmak isterseniz en az iki çizgiyi her X/Y/Z ailesinde işaretleyin. Kalibrasyon geçerliliği için ayrıca bağımsız ölçüm gerekir.

## Test stratejisi
Saf geometri / koordinat / veri kökeni / kayıt / draft / seçim regresyonları sentetiktir. GitHub CI X sunucusu gerektirmeyen çekirdekleri test eder. **Gerçek Windows fare/ekran etkileşim kabulü, farklı DPI/çoklu monitör ve fiziksel kamera doğrulaması en son aşama.**

## Sonraki işler
P9-I03 tüm fizik motoru manifest formları ve otomatik bağımlılık sıralaması. P9-I04 gelişmiş kanıt inceleme ve Windows paketleme. PDF imzalama ve gerçek kamera doğrulaması tamamlanmış gibi gösterilmez.
