# P7-S02 deney günlüğü — v0.25.0

- Önceki regresyon: **705/705 PASS**, mevcut çalışma ortamında yeniden çalıştırıldı.
- P7-S02 yeni testleri: **48/48 PASS**.
- Birleşik regresyon: **753/753 PASS**.
- Sabit tohumlu sentetik benchmark: **80 bağımsız farklı seed**, her seed içinde referans, aynı sensörden bağımsız sorgu ve farklı sentörden sorgu; 20 kare/stack, 32×32 yerel piksel.
- Doğru sensör eşleşmesi: **80/80**; farklı sensör ayrımı: **80/80**. Medyan aynı-sensör PRNU Pearson `0.9765927879535998`, medyan farklı-sensör PRNU Pearson `0.002512199131311914`.
- Negatif kontrol örnekleri: JPEG reddi, köken/aydınlatma/sıcaklık/hizalama eksikliğinde belirsizlik, referans-kare sızıntısı, doygunluk ve çözünürlük farkında güvenli reddetme.
- Sınır: Bu başarı oranları aynı **bağımsız-piksel sentetik sensör modelinden** gelmektedir. P7-S02'nin gerçek cihaz yanlış eşleşme oranı, sensör parmak izi PCE oranları ve AI kökeni tespit doğruluğu ölçülmedi.
- Windows üzerinde son kullanıcı çalıştırması yapılmadı. GitHub'a push yapılmadı.
