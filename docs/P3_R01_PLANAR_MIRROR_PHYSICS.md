# P3-R01 — Düzlem ayna: matematiksel görüntü doğrulama

## Hedef ve kanıt düzeyi

Bu modül, **önceden kalibre edilmiş kamera** ve **bağımsız olarak belirlenmiş ideal düzlem ayna** ile **bağımsız bilinen 3B nesne noktalarına ait** ayna görüntülerinin uyumunu test eder. Otomatik ayna tespiti, 3B nesne konumu kestirimi, malzeme sınıflandırması veya yapay zekâ kökeni sınıflandırması değildir. Bağımsız gerçek fotoğraf doğrulaması projenin son aşamasındadır.

## Dünya ve kamera koordinatları

- Homojen kamera projeksiyonu: `p ∼ K [R|t] [X;1]`.
- Dünya→kamera: `Xc=R Xw+t`; kamera merkezi `C=-Rᵀt`.
- Kamera kalibrasyon girdileri `K (3×3)`, düzgün dönme matrisi `R∈SO(3)`, `t (3)`.
- Lens distorsiyonunun önceden düzeltildiği, iğne deliği kamera varsayılır.
- Fiziksel birim tutarlı olmak zorundadır. Mutlak 3B ölçek kamera ötelemesi, ayna düzlemi ve nesne koordinatlarında aynıdır.

## Ayna düzlemi ve sanal görüntü

Düzlem: `nᵀ X+d=0`, `||n||=1`. İşaret bağımsızdır: `(n,d)` ile `(-n,-d)` aynı düzlemi temsil eder.

`X_virtual=X−2(nᵀX+d)n`.

Gözlenecek yansımış piksel: `p_pred = project_K,R,t(X_virtual)`.

Kamera ışını `C+λ Rᵀ K⁻¹ [u,v,1]`; aynayla kesişme parametresi:

`λ=−(nᵀC+d)/(nᵀr)`.

Kesim `λ>0` olmalı; nesne ve kamera **aynı fiziksel tarafta** olmalı. Girdi poligonla sınırlı aynaysa hem beklenen hem gözlenen ışın kesit noktaları bu poligon içinde kalmalı. Kesişme paralel/arkada olduğunda veya referans nokta ışık yolunu sağlayamadığında ölçüm `INDETERMINATE`.

## Yansıma yasası ve gözlemsel hata

Gelen birim ray `d_in=(M−X)/||M−X||`; aynadan kameraya giden birim ray `d_out=(C−M)/||C−M||`.

`d_reflected=d_in−2(d_inᵀ n)n`

- `reprojection_residual_px = ||p_observed−p_pred||`.
- `reflection_law_residual_deg = acos(d_reflectedᵀ d_out)` derece cinsinden.
- `ray_implied_normal_world = normalize(d_in−d_out)`; işareti keyfîdir.
- `surface_normal_mismatch_deg = acos(|n_impliedᵀ n|)`.

**Önemli:** Üç hata aynı gözlenen eşleşmelerden hesaplanır. Bunları bağımsız kanıtlar gibi toplayarak güven skoru üretmek geçersizdir. Gözlemsel sınıflandırma yalnız konfigürasyonla belirlenen piksel toleransına dayanır ve istatistiksel yanlış alarm düzeyi kalibre edilmemiştir.

## Snell kanununun doğru kapsamı

Aynada yukarıdaki **yansıma yasası** uygulanır. Snell yasası `n₁ sin θ₁=n₂ sin θ₂` iki geçirgen ortam arasında **kırılma** içindir; düzlem ayna uygunluğu için **kullanılmaz**. `refract_direction()` ayrı optik yardımcı fonksiyonudur ve toplam iç yansıma koşulunda `TotalInternalReflection` üretir. P3-R02 cam/su geometrisinde ayrı olarak tekrar kullanılır.

## Manifest örneği

```json
{
  "image_shape_hw": [720, 1280],
  "camera": {
    "K": [[850,0,640],[0,850,360],[0,0,1]],
    "R_world_to_camera": [[1,0,0],[0,0,-1],[0,1,0]],
    "t_world_to_camera": [0,1.7,6.5]
  },
  "mirror_plane": {
    "normal_world": [0,-1,0],
    "offset_world": 0,
    "polygon_world": [[-5,0,0],[5,0,0],[5,0,4],[-5,0,4]]
  },
  "correspondences": [
    {"id":"P0", "object_world_xyz":[0,-2,1.5], "reflection_xy":[640,370], "confidence":1}
  ]
}
```

*Bu örnek yalnız alan şemasıdır; piksel değerleri bağımsız ölçüm veya gerçek eşleşme değildir.* Uygun sentetik fixture için `demo-mirror` çıktısını kullan.

## CLI ve rapor

```powershell
python -m aiforensics demo-mirror --out outputs/p3_r01_demo
python -m aiforensics analyze-mirror --input outputs/p3_r01_demo/p3_r01_fixture.json --image outputs/p3_r01_demo/p3_r01_fixture.png --out outputs/p3_r01_check --tolerance-px 3
python scripts/p3_mirror_benchmark.py --trials 80 --out outputs/p3_r01_benchmark.json
```

- `p3_r01_report.json`: girdi hash'i, her noktanın beklenen/ölçülen görüntü konumu, 3B yansıma kesişimi, sanal 3B nokta, normal ve açısal hata, gözlenebilirlik gerekçesi.
- `p3_r01_overlay.png`: gerçek nesne noktası (soluk mavi), gözlenen ayna noktası (yeşil/turuncu), beklenen nokta (mavi haç), uyuşmazlık çizgisi ve ayna poligonu.
- Durum: `CONSISTENT_UNDER_ASSUMPTIONS`, `INCONSISTENT_UNDER_ASSUMPTIONS`, `MIXED_EVIDENCE` veya `INDETERMINATE`.
- Nihai karar her zaman `NO_AI_ORIGIN_CONCLUSION`.

## Eksikler / nihai kabul önkoşulları

- `K/R/t`, düzlem poligonu ve 3B kaynak noktalarının gerçek sahnede *bağımsız ölçümü* henüz yapılmadı.
- Gerçek fotoğraflarda elle çizilmiş yansıma eşleşmelerinin tutarlılığı ve ölçüm belirsizliği doğrulanmadı.
- Yüzeyin düz, ayna gibi specular ve kadrajdaki görüş ışınlarının engellenmemiş olduğu varsayılıyor.
- Aynanın eğriliği, kir, kaplama kalınlığı, kromatik etkiler, panorama birleştirme ve lens distorsiyonu henüz modellenmedi.
- Bilinen ayna/nesne/kamera ölçülerinin aynı görüntüden eş zamanlı fit edilmesi ve aynı örneklerle doğrulama yapılması **bağımsız kanıt sayılamaz**.
- Sentetik deneylerdeki sınıflandırma başarısı gerçek fotoğraf, fotomontaj veya AI tespit başarısı değildir.
