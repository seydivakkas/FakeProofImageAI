# P9-I09 — Kaynaklı bilimsel görselleştirmeler ve bulgu–görüntü odağı

Sürüm: **v0.37.0** · durum: *sentetik yazılım geliştirmesi*. Gerçek kamera ölçümleri ve gerçek Windows 10/11 kullanıcı kabulü yapılmadı.

## 1. Kalibrasyon kaydı gösterimi

\`science_panel_data.recorded_calibrations(project)\` yalnızca proje \`runs\` envanterindeki \`SUCCEEDED\` kayıtlarını ve beklenen dosya adlarını okur:

- **P1-G01** → \`g01_report.json\` içindeki \`vp_models[*].vp_xy_px\`; salt kaynak piksel koordinatlı keşif VP diyagramı.
- **P1-G02** → \`g01_g02_report.json\`, \`g01_models[*].vp_xy_px\` ve \`g02_calibration.K\`; bu matris varsayımsal model çıktısıdır, bağımsız kamera kabulü değildir.
- **P1-G04** → \`g04_homography_report.json\`; \`train_reprojection_rmse_px\` ve \`holdout_reprojection_rmse_px\` ayrı; \`holdout_reprojection_errors_px\` dizisi ve beyan edilen \`holdout_threshold_px\` çizilir. Kullanıcı eşiği istatistiksel kalibre p değeri değildir.

Rapor kaynakları SHA-256 ile kimliklendirilir; bozuk JSON, beklenmeyen köken kararı, symlink veya klasör dışı dosya kesin sonuç üretmez. G02'nin üç dünya doğrultusunun birbirine dikliği haricî önkabul olmaya devam eder. Kaçış noktası grafiği doğrudan ham görüntünün üstüne bindirilmez, çünkü fizik modülleri ile görüntünün aynı kaynağa ait olduğu açıkça doğrulanmadan böyle bir bağ kurulamaz.

## 2. Artık ve belirsizlik

\`science_panel_data.residual_groups\` yalnızca E03 sürüm sözleşmesine uygun JSON'daki \`measurement.signed_residual\`, \`unit\`, \`confidence_interval_95_for_residual\` ve \`uncertainty.residual_std\` alanlarını işler.

- Fiziksel birimler ayrı sekmelerde yer alır. Piksel ile radyan/derece karıştırılmaz.
- %95 aralık grafiğe **yalnızca E03 raporunda gerçekten varsa** çizilir.
- Boş/şüpheli rapor veya NaN/Infinity durumunda gösterim sonuç uydurmaz.
- Bu veri görselleştirme yeniden p-değeri hesaplamaz; bağımlı kanıt birleştirme kararı E02'de kalır.

## 3. Bulgu → görüntü odağı

P9-I04 \`bind_finding_to_image\` ile kurulmuş, \`user_asserted_not_verified\` türündeki bağlantı olmadan odak işlemi başlatılmaz.

1. Kullanıcı E03 raporunu ve bulguyu seçer.
2. Önceden bağladığı görüntüyü seçer; SHA-256 bütünlük ve E03 kimliği yeniden denetlenir.
3. **Seçili Bulguda Görüntü Bölgesine Git** ile piksel-ROI penceresini açar.
4. Fareyle yerel görüntü üzerinde ROI çizer; uygulama özgün piksel uzayında \`review_focus.json\` içinde saklar ve o alana yakınlaştırır.
5. Kullanıcı tekrar açtığında yalnız aynı E03 bulgusu, SHA-256 ve açık bağlantı için ilgili ROI açılır. Bunlar hiçbir şekilde bilgisayarlı görü tarafından otomatik çıkarılan bölgeler veya bağımsız doğrulanmış kaynak kanıtları değildir.

## 4. Kod bileşenleri

| Dosya | Sorumluluk |
|---|---|
| \`science_panel_data.py\` | Kaynak kayıtları ve ölçüm-sözleşmesi |
| \`science_panel_ui.py\` | VP, G04 holdout, birim ayrımlı E03 artık çizimleri |
| \`focus_region.py\` | ROI doğrulama, hash ve kalıcı bağ |
| \`focus_view_ui.py\` | Kullanıcı ROI çizimi/yakınlaştırma Tkinter penceresi |
| \`ui_polish.py\` | Kalibrasyon ve ölçüm sayfalarına bağ |
| \`review_ui.py\` | E03 bulgusundan ROI penceresine geçiş |
| \`tests/test_p9_i09_science_views.py\` | Sentetik ve negatif regresyonlar |

## 5. Ekran karşılaştırması ve açık kabul

Daha önceki sekiz ekran maketiyle son kontrol: Tkinter'in dokuz sayfası 1366×768 ve 1920×1080 çözünürlüklerde Linux/Xvfb sanal ekranında yakalanır. Boş sentetik projede VP, G04, E03 panelleri **boş kalmalıdır**. Grafiklerin ekranda gerçekten görünmesini sınamak için bağımsız kontrollü sentetik veri seti gerekiyor; boş sayfanın doğru gösterimi grafiğin doldurulmuş veride doğru davrandığının delili değildir.

**Açık:** 100/125/150% DPI, ekran okuyucu, klavye/fare ergonomisi, bağımsız gerçek kalibrasyon, gerçek fotoğraflarda yanlış pozitif oranları, Windows 10/11 kurulum/kullanıcı kabulü. Bunlar son aşamaya ertelenmiştir.

Fiziksel tutarsızlık veya istatistiksel hipotez reddi görüntünün AI ile üretildiğine dair kesin hüküm değildir.
