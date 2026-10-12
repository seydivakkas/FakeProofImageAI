# P4-O01 — Brown–Conrady lens distortion and independent residual evidence

**Geliştirme durumu:** Sentetik matematiksel doğrulama. Gerçek kamera, gerçek fotoğraf veya AI-kökeni kabulü **henüz gerçekleştirilmedi**.

## 1. Problemin kapsamı

Düz bir 3B çizgi merkezi izdüşüm altında ideal pinhole görüntüde düz kalır. Radyal lens distorsiyonu çizgiye görüntüde eğrilik verebilir; teğetsel distorsiyon da simetrik olmayan kayma üretir. Bununla birlikte gerçek eğrisel yüzeyler, panoramik birleştirme, kamera modeli ve yanlış anotasyonlar da benzer sapmalar doğurabilir. Bu nedenle **bükülmüş çizgi AI üretimi ispatı değildir**.

P4-O01, G01/G02/G04 geometrisini optik etkilerden ayırmak amacıyla *isteğe bağlı* lens düzeltme/ölçüm katmanıdır. Bu sürümün kalibrasyonu için **bağımsız olarak bilinen kamera matrisi K** ve bilinen ideal izdüşüm noktaları gerekir; yalnızca görüntüdeki rastgele çizgilerden tek başına benzersiz lens veya K keşfi iddiası yoktur.

## 2. Brown–Conrady kamera modeli

Birimlenmiş koordinatlar

\[
 x=(u-c_x)/f_x, \qquad y=(v-c_y)/f_y,\qquad r^2=x^2+y^2.
\]

Radyal fonksiyon

\[
 g(r)=1+k_1r^2+k_2r^4+k_3r^6.
\]

Radyal + teğetsel distorsiyon

\[
 \begin{aligned}
 x_d&=xg(r)+2p_1xy+p_2(r^2+2x^2),\\
 y_d&=yg(r)+p_1(r^2+2y^2)+2p_2xy.
 \end{aligned}
\]

Distorsiyon sonrası piksel

\[
 u_d=f_xx_d+c_x,\qquad v_d=f_yy_d+c_y.
\]

Parametre sırası OpenCV ile aynıdır: **`[k1,k2,p1,p2,k3]`** (opsiyonel 4 terimli modelde `k3=0`). İleri harita NumPy ile uygulanır; ters harita OpenCV'nin iteratif nokta düzeltme işleviyle çıkarılır, bağımsız ileri uygulamayla **round-trip** kontrolünden geçirilir. Kalibrasyon sırasında yarıçap fonksiyonunun türevi ve örneklenmiş 2B Jacobian determinantı sınanır. Bunlar yalnızca fiziksel terslenebilirlik için *gerekli yerel kontrollerdir*, global biyeksiyon ispatı değildir.

OpenCV matematiği: [Camera Calibration](https://docs.opencv.org/4.x/dc/dbb/tutorial_py_calibration.html), [Camera Calibration and 3D Reconstruction](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html).

## 3. Parametre kestirimi

Ölçülen `observed_xy_px` ile **bağımsız sağlanan** `ideal_xy_px` arasındaki piksel farkı, bilinen `K` verildiğinde beş katsayıya *doğrusal* bağımlıdır. Her nokta iki denklem sağlar. `fit_coefficients`:

1. Eğitim noktalarını `(train)` ve ayrık değerlendirme noktalarını `(holdout)` **benzersiz ID** ve `role` ile ayırır.
2. Bir tasarım matrisi kurar ve SVD koşul sayısını kontrol eder; dejenere örneklemden kalibrasyon üretmez.
3. Piksel artık hatalarında çift bileşeni birlikte ağırlıklandıran IRLS ile bozuk eğitim ölçümlerinin etkisini sınırlar.
4. Fit edilen katsayılarla, eğitimden **hiç kullanılmayan** noktaların yeniden izdüşüm RMSE, medyan ve p90 artık hatalarını hesaplar.
5. Doğruluğu bağımsız doğrulanmış straight-line holdout işaretlerine ters distorsiyon uygular; ortogonal uzaklık TLS/RMS ölçümüyle **önce/sonra** sapmaları hesaplar.
6. Kontrol edilebilir olmayan, tekil veya tutarsız durumlarda gerekçeli `INDETERMINATE` ya da `INCONSISTENT_UNDER_ASSUMPTIONS` üretir; hiçbir koşulda AI kökeni kararı vermez.

Önemli fark: Normal bir `INCONSISTENT` sonucu *kamera kalibrasyonu, görüntü işleme, açıklanmayan warp, yanlış eşleşme, farklı kamera ayarı veya yapay değişiklik* gibi çok farklı nedenlerden kaynaklanabilir. Doğrudan kaynağı belirlemez.

## 4. Örnek manifest

```json
{
  "data_provenance": "INDEPENDENT_MEASURED_GEOMETRY",
  "K": [[860, 0, 636], [0, 850, 359], [0, 0, 1]],
  "point_pairs": [
    {"id": "train-01", "role": "train", "ideal_xy_px": [100,100], "observed_xy_px": [118,108]},
    {"id": "holdout-01", "role": "holdout", "ideal_xy_px": [1150,620], "observed_xy_px": [1136,612]}
  ],
  "independent_straight_lines": [
    {"id": "verified-wall-edge", "externally_verified_straight": true,
     "observed_points_xy_px": [[100,100],[200,102],[300,107],[400,113],[500,120]]}
  ]
}
```

**Bu sadece alanları açıklayan kısaltılmış şemadır; çözüm için nokta sayısı yetersizdir.** Tam sentetik örnek CLI `demo-lens` ile `outputs/p4_o01_demo/p4_o01_fixture.json` içinde üretilir. 5 katsayılı kalibrasyonda en az 15 eğitim ve 8 holdout gerekir; gerçekte tüm görüntüye yayılan farklı yarıçap ve yönelimlerden yeterli veri toplanmalıdır.

- `data_provenance`: `SYNTHETIC_KNOWN_TRUTH` veya `INDEPENDENT_MEASURED_GEOMETRY`. Salt beyan, bağımsız ölçüm kanıtı sayılmaz.
- `K`: aynı çekim, çözünürlük, crop ve odak ayarı için haricen doğrulanmalıdır. G02'nin **bozulmuş çizgilerden doğrudan kestirdiği K** ile otomatik geri besleme ve dairesel uyum değerlendirmesi yapılmaz.
- `point_pairs`: her `id` benzersiz; `role` yalnız `train` ya da `holdout`.
- `independent_straight_lines`: doğruluğu haricen teyit edilmiş, her biri en az 5 örnekli çizgi; etiketi olmayan çizgi **kanıta eklenmez**.

## 5. CLI / entegrasyon

```powershell
python -m aiforensics demo-lens --out outputs/p4_o01_demo
python -m aiforensics analyze-lens --input measurements.json --image frame.png --out outputs/lens_report
python scripts/p4_lens_benchmark.py --trials 80 --out outputs/p4_o01_benchmark.json
python scripts/p4_lens_negative_controls.py
```

`p4_o01_report.json` durum, model, K, beş katsayı, fit ve holdout hata dağılımları, radial/Jacobian kontrolleri, çizgi öncesi/sonrası ölçümleri, kaynak SHA256 ve sınırlamaları içerir.

Görüntü verilirse `p4_o01_overlay.png` (anotasyonlar) ve `p4_o01_rectified.png` (optik düzeltme ön izlemesi) çıkar. `rectified` görüntü gerçek veya doğru olduğu anlamına gelmez. Önceki G01/G04 işlem hatları, istenirse kullanıcı tarafından düzeltilmiş görüntüyle *bağımsız tekrar çalıştırılabilir*; ham görüntü ve kanıt zinciri değiştirilmez. Böyle bir tekrar otomatik bir saha validasyonu değildir.

## 6. Negatif kontroller ve kabul

- Tamamen sentetik ama fiziksel uyumlu görüntü: lens modeline uyması **gerçek fotoğraf ispatı değildir**.
- Tekdüze yarıçap / dejenere veri: `INDETERMINATE`.
- Eğitimde kullanılmamış bozuk holdout koordinatları: koşullu `INCONSISTENT_UNDER_ASSUMPTIONS`.
- Kasıtlı deformasyonlu, gerçekten düz olduğu belgelenmiş bir holdout kenar: koşullu `INCONSISTENT_UNDER_ASSUMPTIONS`.
- Referans kökeni açıklanmamış: `INDETERMINATE`.
- Fisheye / çok geniş açı, rolling-shutter, kamera içi geometri düzeltmesi, kırpma veya yeniden örnekleme: 5 terimli model uygun olmayabilir.
- Çeşitli lens/focal/crop çözünürlüklerinde karşılaştırma yapılacaksa her kamera kurulumuna özel `K` gerekir.
- Gözlem noktalarındaki hata belirsizliğinden bir **kalibre edilmiş güven aralığı** henüz türetilmedi; 2 piksel varsayılan holdout eşiği evrensel fizik sabiti değildir.

**Nihai gerçek fotoğraf, fiziksel kamera kalibrasyonu ve Windows cihaz kabulü** kullanıcı kararı gereği projenin son doğrulama fazında kalır.
