# P3-R03 — Ardışık düzlem aynalarda sanal görüntü zinciri ve ışın yolu doğrulaması

## Amaç ve sınırlar

Kalibre edilmiş pinhole kamera (`K`, `R_world_to_camera`, `t_world_to_camera`), bağımsız olarak ölçülmüş 3B nesne noktaları ve **sınırları bilinen ideal düzlem aynalar** verildiğinde, bir nesnenin belirli bir **ardışık yansıma sırasından** görüntülenip görüntülenemeyeceğini test eder. Bu modül bir AI görüntü sınıflandırıcısı değildir, ayna/piksel eşleşmelerini otomatik bulmaz. Gerçek görüntü doğrulaması proje sonuna bırakılmıştır.

## Matematik

Ayna düzlemi: `nᵀX+d=0`, `||n||=1`.

Bir noktanın aynaya göre simetriği:

```text
H_i(X) = X - 2 (n_i^T X + d_i) n_i
```

Nesneden kameraya **yansıma sırası** `M1, M2, ..., Mk` ise zincir:

```text
V0 = X_object
V1 = H_1(V0)
V2 = H_2(V1)
...
Vk = H_k(Vk-1)
p_expected = project(K, R, t, Vk)
```

Elde edilen `p_expected`, yalnızca bir adaydır. Sanal görüntünün hesaplanabiliyor olması gerçek ışın yolunun mümkün olduğunu kanıtlamaz.

Kameradan ters yönde izleme yaparken sıralama `Mk -> ... -> M2 -> M1` olur. Her k adımında:

```text
r(t) = origin + t * direction, t > 0
intersection t = -(n·origin + d) / (n·direction)
direction_out = direction_in - 2(n·direction_in)n
```

Yalnız ileri kesişim kabul edilir. Kesişim ayna poligonunun içinde olmalı, ışın `reflective_side` ile izin verilen yüzden gelmeli ve **başka bir tanımlı opak aynayla daha önce** kesişmemelidir. Son ışın için bağımsız olarak verilen 3B nesne konumunun doğrultusuna olan dik uzaklık hesaplanır:

```text
miss_3D = || (X_object - last_hit) × direction_out ||
```

Beklenen piksel ile gözlenen pikselin uzaklığı:

```text
residual_px = ||p_observed - p_expected||_2
```

3B ışın sapması ve piksel farkı aynı eşleşmenin farklı ifadeleridir; **iki bağımsız kanıt** olarak sayılmaz.

## Veri sözleşmesi

- `camera`: R01/R02 ile aynı `K`, `R_world_to_camera`, `t_world_to_camera` sözleşmesi.
- `image_shape_hw`: `[yükseklik, genişlik]`, pozitif tamsayılar.
- `mirrors`: benzersiz `id` sahibi, `normal_world`, `offset_world`, **zorunlu** `polygon_world` (sıralı, düzlemsel, konveks, en az 3 köşe) içeren 2–8 aynalık dizi. `reflective_side`: `positive`, `negative` ya da `both` (varsayılan).
- `reflection_order_object_to_camera`: 2–4 farklı ayna `id` dizisi. Anotasyonda aynı adlı alanla üzerine yazılabilir. Tek ayna R01 modülünde değerlendirilir; yinelenen ayna zincirleri henüz desteklenmez.
- `correspondences`: benzersiz `id`, `object_world_xyz` (metrik 3B nokta), `reflection_xy` (görüntü koordinatı) ve isteğe bağlı `confidence` (0,1] alanlarını içeren eşleşme dizisi.

Örnek JSON: `outputs/p3_r03_demo/p3_r03_fixture.json`.

## Çıktı / fail-closed

En az 3 **farklı 3B nesne noktası** gereklidir; aynı fiziksel noktanın tekrar anotasyonları bağımsız kanıt kabul edilmez. Tekrarları sayısal yuvarlama toleransında birleştiririz.

`p3_r03_report.json`: `virtual_image_chain_world`, `ray_hits_camera_to_object` (gerçek ayna yüzeyiyle 3B kesişimler), kamera–ayna–nesne `path_world`, pikselleştirilmiş beklenen yansıma, `reprojection_residual_px`, `object_ray_miss_world`, gerekirse `physical_trace_rejection_reason` ve giriş SHA-256 özetleri.

- `CONSISTENT_UNDER_ASSUMPTIONS`: modelin beklenen pikseline yeterince yakın, fiziksel ışın yolu uygun.
- `INCONSISTENT_UNDER_ASSUMPTIONS`: modelin öngördüğü yol geçerli fakat anotasyondaki görüntü gözlemi bu yolun pikseline tolerans dışında ya da gözlemin ters ışın yolu fiziksel olarak imkânsız.
- `INDETERMINATE`: bilinen kamera/ayna/nesne koşullarında beklenen fiziksel yansıma yolu oluşturulamıyor; gözlem görüntü dışında; veya yeterli **bağımsız 3B nesne noktası** yok.
- `MIXED_EVIDENCE`: değerlendirilmiş eşleşmelerin bazısı uyumlu bazısı değil.

Dikkat: Belirli bir ayna sırası fiziksel olarak olanaksızsa bu, görüntünün sahte olduğunu değil **o hipotezin elendiğini** ifade eder. Dışarıdan belirlenen sıra yanlış, nesne/ayna kalibrasyonu hatalı veya bilinmeyen ayna/örtücü yüzey bulunabilir. Kod **yansıma sırasını otomatik kestirmez**, ayna dışı genel 3B oklüzyonu çözmez. `tolerance_px=3` bilimsel olarak kalibre edilmiş yanlış alarm eşiği değildir.

## Çalıştırma

```powershell
python -m aiforensics demo-mirror-chain --out outputs/p3_r03_demo
python -m aiforensics analyze-mirror-chain `
  --input outputs/p3_r03_demo/p3_r03_fixture.json `
  --image outputs/p3_r03_demo/p3_r03_fixture.png `
  --out outputs/p3_r03_analysis --tolerance-px 3
python scripts/p3_mirror_chain_benchmark.py --trials 60
pytest -q
```

## Test kapsamı ve bilinen açıklar

- İki aynalı pozitif/negatif kontrollü sentetik sahneler: farklı rastgele tohumlarda piksel gürültüsü ve kasıtlı eşleşme kaydırmaları.
- Üç ayrı aynalı yansıma sırası: tam 3B yol ve sanal görüntü zincirinin deterministik doğrulanması.
- Sıra hataları, çokgen dışına çıkan ışın, yanlış yansıtıcı yüz, geçersiz kamera/geometri, tekrar eden ayna kimliği, görünmez nokta, düşük destek ve CLI/JSON regresyonları.
- Dört yansıma koda kabul edilse de bağımsız üçten fazla yansıma sisteminde test kapsamı sınırlıdır.
- Pürüzlü/çarpık aynalar, spektral Fresnel yansıması, cam arkası aynalar, lens bozulması, nesne oklüzyonu, fotometrik uygunluk ve çoklu alternatif ışın sırası testleri gelecek geliştirmelerdir.
- Gerçek kamera fotoğraflarında bağımsız kalibrasyon ve saha doğrulaması **en son**.
