# P10 — Bağımsız kabul matrisi

**Durum: NOT_STARTED.** P9-I10 v0.38.0 yalnız sentetik yazılım kapısıdır. Aşağıdaki kapıların hiçbiri gerçek veriyle kabul edilmemiştir.

## Kurallar
Her bağımsız kabulde özgün veri SHA-256, veri kullanma hakkı, çekim/ölçüm kaynağı, referans/kalibrasyon ve belirsizlik, ayrı eğitim ve holdout, bağımsız gözden geçirme, tekrar üretim komutu, Git commit ve çalışma ortamı saklanmalıdır. Bir dosyada "real" yazması bağımsız doğrulama değildir. Sayısal eşikler holdout açılmadan ön-kayda alınacaktır. Fiziksel tutarsızlık AI kökenini kanıtlamaz.

İzin verilen durumlar: NOT_STARTED, IN_PROGRESS, BLOCKED, PASS, FAIL. Herhangi bir kapıda başka kapının PASS durumunu kopyalamak yasaktır.

| Paket | Bağımsız ölçüm | Kapanış kanıtı | Durum |
|---|---|---|---|
| P10-A01 | Özgün gerçek görüntü, RAW/JPEG ayrımı, telif/izin, çekim oturumu, referans ve holdout | Orijinal SHA, kaynak tanıklığı, kamera/sahne/oturum sızıntısı kontrolü ve ön-kayıt | NOT_STARTED |
| P10-A02 | Bağımsız G01/G02/G04 kamera intrinsics/mercek/metrik ölçüleri ve uygun fizik alt modülleri | K/mercek geometrisi için bağımsız sertifikalı referans, train–holdout ve tolerans bazlı metrik raporlar | NOT_STARTED |
| P10-A03 | Görülmemiş gerçek görüntülerde hata ve abstention analizi | Sahne/cihaz kırılımlı yanlış alarm, belirsizlik, koşullu fizik hipotezi ve ön-kayıtlı sınırlar | NOT_STARTED |
| P10-A04 | Gerçek Windows 10/11 paket, kurulum ve UI | Native makine/OS bilgisi, .exe hash, 100/125/150% DPI, 1366x768/1920x1080, erişilebilirlik, kurulum/kaldırma | NOT_STARTED |
| P10-A05 | Maketlerin bağımsız görsel/ergonomik değerlendirmesi | Hedef ve native screenshot karşılaştırması, sayfa/ekran/DPI tablosu ve insan değerlendirmesi | NOT_STARTED |
| P10-A06 | Son sürüm bağımsız kabul | A01–A05 denetlenmiş sonuçları, açık kusurlar, imzalı karar, sürüm ve hash zinciri | NOT_STARTED |

## İstatistik ve veri yönetimi
Yanlış alarm oranı, her modülün koşullu fizik hipotezine göre önceden tanımlanmalıdır. Aynı kamera/sahne/oturumdan çıkan ilişkili gözlemler bağımsız örnek diye çoğaltılmaz. Özellikle PRNU/DSNU için gerçek RAW dark/flat ayrı referansları; JPEG çıktıdan sensör kimliği kabulü yasak. Test sonuçları eşiğe göre yorumlanır, eşik sonradan değiştirilmez; değiştirilirse yeni deney sürümü ve posthoc etiketi gerekir.

## Kanıt kaydı
Vaka şablonu: docs/p10/P10_CASE_TEMPLATE.json.
Ön-kayıt: docs/p10/P10_PREREGISTRATION_TEMPLATE.md.
Ham orijinal kamera görüntülerini/cihaz seri no/GPS/yüzleri varsayılan olarak **herkese açık repo içine koymayın**. İzinli korumalı kasada saklayın; GitHub'da yalnız gerekli hash ve onay/denetim bağlantısı bulunsun.

P9-I10 synthetic PASS, P10 real acceptance NOT_STARTED. Otomatik GitHub CI veya Ubuntu/Xvfb screenshot hiçbir P10 kapısını tek başına PASS yapamaz.
