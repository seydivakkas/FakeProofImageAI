# P2-S04 — Güneş/gölge matematiği ve astronomik hipotez karşılaştırması

## Kapsam ve güvenilirlik

**Fiziksel geometri hipotezi:** Düşey, yüksekliği bilinen bir nesnenin üst noktası, zemindeki taban noktası ve karşılık gelen gölge noktası, birim paralel ışık doğrultusunu sınırlar. Sonuç görüntünün üretim kökenini kanıtlamaz.

**Bu modül AI dedektörü değildir.** Gölgenin güneşten geldiği ve çekim zaman/konumunun doğruluğu dışarıdan doğrulanmadıysa, azimut ve yükseklik yalnız ölçülen bir **uzak/yönlü ışık** hipotezidir.

## Referans koordinat sistemi

- `world_frame="ENU_TRUE_NORTH"`: Sağ elli yerel **X=Doğu, Y=Kuzey, Z=Yukarı**.
- Azimut `A` gerçek kuzeyden saat yönüne doğru artar: kuzey=0°, doğu=90°, güney=180°, batı=270°.
- Yükseklik `alpha`: gerçek ufuktan yukarı +; `object_height_m` *yerçekimi doğrultusunda düşey* yüksekliktir, normal-doğrultu uzaklığı değildir.
- `world_units="m"`; `camera.K`, `camera.R_world_to_camera`, `camera.t_world_to_camera` ve `ground_plane` aynı ENU dünyasında olmalıdır. Dünya ölçeğinin metre olduğu bağımsız referansa dayanmalıdır.
- Kamera verileri rectilinear/undistorted piksel kabul eder. `K` tek başına yeterli değildir; sahne düzlemi, `R`, `t` ve metrik yükseklikler gerekir.

## Matematik

Kalibre kamera merkezinden çıkan ışın:

`X(lambda)=C+lambda*R^T*K^-1*[x,y,1]^T`, `C=-R^T*t`.

Alıcı düzlem `n·X+d=0` ise `base_xy` ve `shadow_xy` pikselleri bu düzlemle geri kesiştirilir: `B`, `Q`. Düşey tepe noktası `P=B+h*[0,0,1]^T`. Opsiyonel `tip_xy` varsa `pi(KR(P-C))` noktasına olan piksel uzaklığı ayrıca ölçülür; yanlış yükseklik veya bir kısım yanlış kamera parametresini dışlayabilir.

Güneşe doğru birim ışın `u=(P-Q)/||P-Q||`.

`azimuth = atan2(u_x, u_y) mod 360°`

`elevation = atan2(u_z, sqrt(u_x²+u_y²))`

Yatay alıcı için taban-gölge yatay uzaklığı `L=||Q_xy-B_xy||` ve `tan(alpha)=h/L`. Eğimli zeminde `Q_z != B_z`; doğru formül `tan(alpha)=(P_z-Q_z)/L`. Bu yüzden eğimli zeminde körlemesine `h/L` kullanmak yanlıştır.

Bir güneş azimut/yükseklik çiftinden ENU kaynak doğrultusu:

`u=[cos(alpha) sin(A), cos(alpha) cos(A), sin(alpha)]`

Gölge geometrisinin fiziksel öngörüsü:

`Q_pred=P-lambda*u`, `lambda=(n·P+d)/(n·u)`.

`n·u <= 0` ya da `lambda <= 0` ise verilen yüzey güneşle bu basit model altında aydınlatılmıyor; hesaplanmış fiziksel gölge diye sunulmaz.

## İstatistiksel kestirim

- Anotasyonlardan tek tek `u_i` hesapla; min yatay gölge uzunluğu, pozitif yükselti, tip yeniden izdüşüm farkı, pozitif ray/düzlem kesişimi koşullarını denetle.
- Deterministik açısal RANSAC ve confidence-ağırlıklı birim vektör ortalaması uygula. Default açı toleransı `2°`, en az 4 çift ve ağırlıklı destek `>=0.70`.
- Yakın kaynaklar veya çoklu güneş gibi yorumlar yapılmaz; ciddi çoklu yön varsa tek kaynak kabulü `INDETERMINATE`.
- `bootstrap_direction_change_p90_deg` desteklenen yön vektörlerinin tekrar örneklemesinden hesaplanan *açıklayıcı kararlılık istatistiğidir*. Kamera, yükseklik, coğrafi yön ve gölge sınır belirsizliklerini kapsayan istatistiksel güven aralığı **değildir**.
- Hesaplanan `elevation_from_shadow_length_deg` numune başına ölçüm olarak JSON'a kaydedilir.
- Tam otomatik nesne-gölge algılama **yok**. Önceden hazırlanmış ve eşleşmiş anotasyonlar gerekir.

## Astronomik karşılaştırma

İsteğe bağlı manifest `solar_claim={latitude_deg, longitude_deg, timestamp_utc}` içerir. ISO 8601 `Z`/`+00:00` saat zorunludur; Türkiye yerel saatini kullanıcı önceden UTC'ye dönüştürmelidir. İddia edilen zaman doğru olmayabilir. Dünyanın gerçek kuzeye hizalanması ayrıca gereklidir.

Basitleştirilmiş NOAA fractional-year yıllık harmonik modelini uyguluyoruz:

- `gamma=2*pi/N*(day_of_year-1+(UTC_hour-12)/24)`
- NOAA `eqtime(gamma)` (dakika) ve `decl(gamma)` (radyan)
- `true_solar_time_minutes=UTC_minutes+eqtime+4*longitude_E`;
- `hour_angle=true_solar_time_minutes/4-180` (derece)
- Sonuç enlem, deklinasyon ve saat açısıyla ENU vektörü; azimut ve yükseklik.

Bu NOAA *yaklaşık* algoritmasıdır, NREL SPA ile aynı hassasiyetin garanti edildiği iddia edilmez. Ufka yakın atmosferik kırılma, coğrafi yükseklik, topografya ve perspektifinin etkileri hesaba katılmaz. Karşılaştırma açısal toleransı ilk yazılım geliştirme için **2° mühendislik varsayımıdır**, gerçek-veri yanlış alarm kalibrasyonu değildir.

Astronomik güneş ufkun altındaysa, yapay ışık veya yanlış zaman ihtimalleri yüzünden `INDETERMINATE` kullanılır. Uygun referans varsa `CONSISTENT_UNDER_ASSUMPTIONS` veya `INCONSISTENT_UNDER_ASSUMPTIONS` üretilir; hiçbiri görüntünün AI üretimi olduğunu söylemez.

## JSON şeması (gösterim amaçlı)

```json
{
  "world_frame":"ENU_TRUE_NORTH",
  "world_units":"m",
  "image_shape_hw":[720,1280],
  "camera":{
    "K":[[850,0,640],[0,850,360],[0,0,1]],
    "R_world_to_camera":[[1,0,0],[0,1,0],[0,0,1]],
    "t_world_to_camera":[0,0,0]
  },
  "ground_plane":{"normal_world":[0,0,1],"offset_world":0},
  "correspondences":[
    {"id":"pair_000","base_xy":[640,400],"tip_xy":[640,325],"shadow_xy":[600,450],"object_height_m":1.5,"confidence":1.0}
  ],
  "solar_claim":{"latitude_deg":41.0,"longitude_deg":29.0,"timestamp_utc":"2025-06-21T09:00:00Z"}
}
```

**Yukarıdaki şema yalnız alan örneğidir, geçerli kamera/düzlem/ölçüm düzeni değildir.** Çalışan sentetik manifest `demo-solar` veya `scripts/p2_solar_ephemeris_demo.py` ile üretilir.

## CLI

```powershell
python -m aiforensics demo-solar --out outputs/p2_s04_demo
python -m aiforensics analyze-solar --input outputs/p2_s04_demo/p2_s04_fixture.json --image outputs/p2_s04_demo/p2_s04_fixture.png --out outputs/p2_s04_analysis
python scripts/p2_solar_benchmark.py --trials 80 --out outputs/p2_s04_benchmark.json
python scripts/p2_solar_ephemeris_demo.py --out outputs/p2_s04_ephemeris_demo
pytest -q
```

## Kabul ve deney sınırlamaları

- Sentetik kamera, zemin ve nesne yüksekliği referansı; düz/eğimli zemin, değişen azimut, yönde wraparound ve gürültü + yanlış eşleşmeler.
- Negatif test: karma yapay ışık yönleri, yanlış `tip_xy`, geçersiz georeferans, yanlış kamera duruşu, gece güneş iddiası, bozuk saat dilimi, yetersiz örneklem.
- Astronomik algoritmanın bağımsız SPA/pvlib sayısal referansla doğrulanması **gelecekteki geliştirme/validasyon işi**.
- Gerçek fotoğraf, dış kaynak konum/zaman/kamera tespiti, azimut yönelim hatası ve gerçek yanlış alarm: **son doğrulama fazına ertelendi**.

## Bilimsel referanslar

- NOAA GML Solar Calculator: https://gml.noaa.gov/grad/solcalc/
- NOAA Solar Calculations: https://gml.noaa.gov/grad/solcalc/solareqns.PDF
- NREL SPA (yüksek doğruluk ayrı, bu sürümde uygulanmadı): https://midcdmz.nlr.gov/spa/
