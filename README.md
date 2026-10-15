# AI Image Forensics — Physics First v0.24.0

**P0 + P1 / G01–G04 + P2-S01–S05 + P3-R01–R03 + P4-O01–O04 + P5-D01–D03 + P6-M01/M02/M03 + P7-S01:** Ölçülebilir fiziksel/projektif geometri; kesin AI-origin sınıflandırması yok.

## Modüller

- **G01** — LSD/Hough ve RANSAC ile kaçış noktası kestirimi.
- **G02** — üç *bağımsız ortogonal* çizgi grubundan kamera iç parametreleri `K` ve dönme `R` kestirimi. Gerçek kamera referanslı doğrulama **HOLD**.
- **G03** — projektif çapraz oran ve bilinen fiziksel işaretlerin holdout doğrulaması.
- **G03a** — fotoğraftan otomatik çizgi-kesişim tekrar adayı.
- **G03b (yeni)** — kullanıcı/dış kaynak poligonlarıyla düzlem bazında zemin, cephe, duvar ayrımı; dörtgen/yerel görünüş aday eşleştirme. **Otomatik semantik segmentasyon veya gerçek nesne sınıflandırması değildir.** Bölge etiketi haricen verilmezse sınıf `unknown` kalır.
- **G04** — bilinen bir düzlemde bağımsız noktalarla homografi doğrulama.
- **G04-pair (yeni)** — iki fotoğrafın SIFT eşleşmelerinde holdout homografi kestirimi; eşleşme aykırılarını ölçme; bağımsız düzlem verisi yoksa yalnız tanımlayıcı sonuç.
- **P2-S01** — anotasyonlu nesne–gölge nokta eşleşmelerinin matematiksel doğru-kesişim ve gölge ışığı izdüşümü kestirimi; sonlu ya da görüntü düzleminde sonsuzdaki kesişim. Çoklu ışık ve yanlış eşleşme durumlarında kontrollü abstention; gerçek sahne veya AI kökeni kararı yok.
- **P2-S02** — çoklu ışık *izdüşüm ailesi* kestirimi: anotasyonlu gölge ışınları üzerinde RANSAC, yakınsama adaylarının geometrik ayrımı, yanlış eşleşmelerin dışlanması ve belirsiz eşleşmelerin etiketlenmesi. Gerçek 3B ışık sayısı veya AI kökeni kararı değildir.
- **P2-S03** — kalibre `K/R/t`, bilinen alıcı düzlem ve bağımsız bilinen nesne nokta yükseklikleri üzerinden nesne/gölge görüntü koordinatlarından 3B ışınlar üretir. Sonlu ışığın 3B konumunu veya uzak/parallel kaynağın yalnız yönünü RANSAC ile tahmin eder; yeterli parallax yoksa konumu reddeder. S02 aile atamalarını isteğe bağlı alır. **Gerçek veri doğrulaması sona bırakıldı.**
- **P2-S04** — kalibre ENU yerel dünya koordinatlarından düşey nesne yüksekliği + taban/gölge eşleşmesiyle güneş-benzeri uzak ışık azimutu/yüksekliği. Eğimli zemin, yanlış eşleşme elenmesi ve opsiyonel NOAA yaklaşık konum/zaman hipotez karşılaştırması. **Şimdilik yalnız sentetik test; gerçek veri doğrulaması en son.**
- **P2-S05 (yeni)** — **umbra/penumbra** görünür ışık yüzdesinin disk/şerit kaynaklı analitik modeli, doğrusal göreli ışınım kenar profillerinde sağlam eğri uyumu, metrik kenar yüksekliği/ölçeği verildiğinde *koşullu* açısal ışık çapı kestirimi, aynı kaynak hipotezinde çoklu kenar geometrik tutarlılığı, çözünürlük/PSF belirsizliği ve sonlu kaynak–örtücü–alıcı için tam umbra sınırı hesabı. `.npy` doğrusal görüntüden verilen transect koordinatlarıyla profil örnekleme mevcut. **Otomatik kenar segmentasyonu, fotoğraf gamma doğrulaması ve gerçek veri kabulü yok.**
- **P3-R01** — kalibre kamera `K/R/t` + bağımsız ayna düzlemi/poligonu + 3B nesne noktalarından **düzlem aynanın sanal görüntüsünü**, gözlenen yansıma piksel sapmasını, ışın kesişimini ve yüzey normali/yansıma açılarını test etme. Snell kanunu **yalnızca ayrı kırılma yardımcı fonksiyonudur**. **Saha doğrulaması en son; AI kökeni kararı yok.**
- **P3-R02 (yeni)** — **Snell yasası** ile düz hava–su arayüzü veya paralel hava–cam–hava levhasında analitik/sayısal ışın izi; bilinen `K/R/t`, arayüz normal/konumu, indisler ve 3B noktalara göre beklenen piksel, fiziksel görüş yolu, modeldeki görünür yer değiştirme ve piksel artık hatası. Kritik açıda toplam iç yansıma ve fiziksel olarak çözümsüz geometri fail-closed. **Gerçek fotoğraf doğrulaması son aşamada.**
- **P3-R03 (yeni)** — **Birden fazla sonlu düzlem aynada sıralı yansıma**: sanal görüntü zinciri, kalibre kamera izdüşümü, ters yönde fiziksel ışın izleme, çokgen/yan yüz/önceki ayna oklüzyon kontrolü ve 3B nesne–ışın sapması. İki/üç ayna sentetik testleri ve bozuk eşleşmeler için gerekçeli `INDETERMINATE`/`INCONSISTENT_UNDER_ASSUMPTIONS` ayrımı. **Gerçek fotoğraf kabulü en sonda; AI kökeni kararı yok.**
- **P4-O01** — Brown–Conrady radyal/teğetsel lens distorsiyonu, ters piksel dönüşümü, kalibrasyon ve holdout çizgi testleri.
- **P4-O02** — İdeal ince mercek, CoC, alan derinliği, derinliğe göre geometrik defocus ve holdout ölçümleri.
- **P4-O03** — Kamera K, fiziksel odak, FoV, kırpma/ölçek, projeksiyon ve perspektif optik tutarlılığı.
- **P4-O04 (yeni)** — Koşullu cos⁴ ışınım düşüşü + log-radyal vinyet modeli; bilinen doğrusal/dark-corrected flat-field üzerinde eğitimden ayrı bölgesel ölçümler, kaymış radyal merkez, güvenli kazanç sınırı ve sapma raporu. **JPG parlaklığı doğrudan fotometri veya sahtecilik kanıtı değildir.**
- **P5-D01** — dışarıdan kalibre edilmiş kamera ve bağımsız metrik zemin/destek çokgeni ile koşullu 3B ışın-düzlem derinliği; bağımsız nesne tabanı, bilinen dik yükseklik ve statik ağırlık merkeziyle sınırlı fiziksel tutarlılık denetimi. Belirsiz veride kesin temas kararı yok.
- **P5-D02 (yeni)** — çoklu, sonlu ve bağımsız metrik düzlem çokgenleri; ışın boyunca derinlik sıralaması, opak yüzeyler arası örtüşme, bağımsız görünürlük etiketi ve 3B nokta kısıtları. Yakın katmanlar ve sınır piksel belirsizliğinde karardan kaçınma. **Serbest 3B sahne rekonstrüksiyonu veya fotoğraftan otomatik örtüşme tespiti değildir.**
- **P5-D03 (yeni)** — Dışarıdan bilinen kütle dağılımı, 3B COM, sonlu destek/temas noktaları, unilateral normal tepkiler, Coulomb sürtünmesi, dış kuvvet ve momentlerle **koşullu statik denge fizibilitesi**. İç koni fizibilitesi varsa koşullu uyum, dış koni fizibilitesi dahi yoksa koşullu ihlal; aksi durum veya yetersiz bağımsız veri `INDETERMINATE`. Otomatik fotoğraf kütle/sürtünme tahmini **yok**. Sentetik testli; gerçek veriler en son.
- **P6-M01** — Kalibre Lambertian yansıma, albedo ve enerji denetimi; yalnız sentetik doğrulama.
- **P6-M02** — Tek saçılmalı Cook–Torrance/Smith-GGX speküler BRDF, Schlick Fresnel ve pürüzlülük; bağımsız holdout.
- **P6-M03 (yeni)** — Enerji koruyan *konveks Lambertian + GGX* karışımı, ortak malzemenin iki farklı yüzeyde doğrulanması, yalnız eğitim ölçümünden difüz albedo kestirimi ve belirsiz malzeme–ışık ayrımında karardan kaçınma. İsteğe bağlı *fenomenolojik* çoklu-saçılma vekili vardır; gerçek mikro-yüzey çoklu saçılma çözümü değildir. [Teknik matematik ve giriş sözleşmesi](docs/P6_M03_ENERGY_BOUNDED_MATERIALS.md). Sentetik benchmark dışında gerçek ölçüm yok.
- **P7-S01 (yeni)** — Doğrusal RAW Poisson shot/dark + Gaussian read noise; e⁻/ADU kazancı, ADC/full-well sınırı, SNR ve bağımsız zamansal holdout varyans denetimi. PRNU, JPEG veya gerçek sensör parmak izi kapsam dışı. [Fiziksel sözleşme](docs/P7_S01_POISSON_GAUSSIAN_SENSOR_NOISE.md).
- **G02 York hazırlayıcı (v0.5)** — özgün resmî `cameraParameters.mat` + K'dan bağımsız Manhattan çizgi anotasyonlarıyla manifest üretme. Referans `K`'dan türetilmiş etiketleri bilerek reddeder.

## Kurulum (Windows PowerShell)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,benchmark]"
pytest -q
```

`benchmark` ek bağımlılığı `scikit-image` örnek gerçek fotoğraf içeriği çalıştırmak için gereklidir. `python -m pip install -e ".[dev]"` temel testleri çalıştırır, `scikit-image` testleri kurulu değilse atlanır.


## P4-O04 — cos⁴ düşüşü, radyal vinyet ve bağımsız flat-field holdout

**Öncelik:** Önce tüm matematik/optik modüllerinin geliştirilmesi; gerçek RAW düz-alan, kamera verisi ve Windows kabulü en sonda.

```powershell
python -m aiforensics demo-vignetting --out outputs/p4_o04_demo
python -m aiforensics demo-vignetting --fit-center --out outputs/p4_o04_center_demo
python -m aiforensics analyze-vignetting --input outputs/p4_o04_demo/p4_o04_fixture.json --out outputs/p4_o04_check
python scripts/p4_vignetting_benchmark.py --trials 80
```

Gerçek doğrusal `.npy` düz-alan hedefinde, bağımsız referans ışınımı ve çakışmayan ROI anotasyonları sağlandığında ayrıca `sample-vignetting` kullanılabilir. Optik modelin formülleri, dosya sözleşmesi, fiziksel varsayımları ve sınırları: [`docs/P4_O04_VIGNETTING_RADIOMETRY.md`](docs/P4_O04_VIGNETTING_RADIOMETRY.md).

## P2 — İlk ışık/gölge fizik modülü

**Geliştirme önce, gerçek veriyle nihai kabul en son.** P1'in açık gerçek-saha validasyon işleri bilerek son doğrulama fazına ayrılmıştır. Bu durum matematiksel regresyonları veya sentetik hata senaryolarını atlamak anlamına gelmez.

```powershell
# Bilinen 3B nesne, ışık kaynağı ve zeminle oluşturulmuş matematiksel test
python -m aiforensics demo-shadows --out outputs/p2_s01_demo

# Anotasyonlu nesne–gölge nokta çiftlerini incele
python -m aiforensics analyze-shadows --input pairs.json --image frame.png --out outputs/p2_s01

# Kontrollü gürültü / hatalı eşleşme stres deneyi
python scripts/p2_shadow_benchmark.py --trials 60 --out outputs/p2_s01_benchmark.json
```

**Anotasyonlar zorunludur:** P2-S01 şu anda fotoğraftan otomatik gölge maskesi veya nesne-gölge eşleşmesi bulmaz. Yalnızca kullanıcı tarafından verilen gerçek eşleşmelerden ışığın 2B izdüşüm yönelimini kestirir. Giriş formatı ve fiziksel varsayımlar: [`docs/P2_S01_SHADOW_GEOMETRY.md`](docs/P2_S01_SHADOW_GEOMETRY.md).

## P2-S02 — Birden fazla ışık izdüşümü ailesi

```powershell
# Gerçek 3B ışık/nesne/geometri kullanılarak ÜRETİLEN sentetik iki-ışık sahne
python -m aiforensics demo-multilight --out outputs/p2_s02_demo

# Anotasyonları önceden hazırlanmış görsel üzerinde dene
python -m aiforensics analyze-multilight --input pairs.json --image frame.png --out outputs/p2_s02_analysis

# Yanlış eşleşmeler ve gürültüyle tekrarlı kontrollü deney
python scripts/p2_multilight_benchmark.py --trials 60 --out outputs/p2_s02_benchmark.json
```

Rapor: `p2_s02_report.json`; görsel: `p2_s02_overlay.png`. `models` gerçek ışıkların kanıtlanmış sayısı değil, uyumlu görüntü düzlemi doğru aileleri sayısıdır. Anotasyonlar gerçek nesne–gölge karşılıklarından oluşturulmalıdır. Ayrıntılar: [`docs/P2_S02_MULTILIGHT_GEOMETRY.md`](docs/P2_S02_MULTILIGHT_GEOMETRY.md).

## P2-S03 — Kalibre kamera + 3B ışık kestirimi

```powershell
# Gerçek 3B zemin, 3B ışık kaynağı ve kamera ile üretilen sentetik örnek
python -m aiforensics demo-light-3d --out outputs/p2_s03_demo

# Bilinen K/R/t, düzlem, yükseklik ve anotasyonlardan 3B ışık veya ışık yönü
python -m aiforensics analyze-light-3d --input outputs/p2_s03_demo/p2_s03_fixture.json --image outputs/p2_s03_demo/p2_s03_fixture.png --out outputs/p2_s03_analysis

# Kontrol edilen 60 sentetik deneme, yanlış eşleşmeler ve gürültü
python scripts/p2_shadow_3d_benchmark.py --trials 60 --out outputs/p2_s03_benchmark.json

# Önceden aynı görüntü ve anotasyonlarda çalıştırılmış S02 aile hipotezlerini aktar
python -m aiforensics analyze-light-3d --input camera_shadow_pairs.json --s02-report s02_result/p2_s02_report.json --out outputs/p2_s03_grouped
```

`K` ve `R` tek başına metrik 3B konum için yeterli değildir; **kamera ötelemesi `t`, alıcı düzlem ve her eşleşmenin bilinen düzleme göre yüksekliği gerekir.** P2-S03 bugün sadece anotasyon ve kalibrasyon verilmiş durumlarda çalışır; gölgeleri otomatik algılama ve gerçek saha ölçümü yapılmadı. Detaylar: [`docs/P2_S03_CALIBRATED_3D_LIGHT.md`](docs/P2_S03_CALIBRATED_3D_LIGHT.md).

## P2-S04 — Güneş azimut/yükseklik ve gölge uzunluğu

**Koordinat sistemi açıkça ENU_TRUE_NORTH olmalı:** X doğu, Y gerçek kuzey, Z yukarı. Yükseklik nesnenin düşey metre cinsinden uzunluğudur. Kamera **K/R/t**, düzlem, doğru nesne–gölge eşleşmeleri ve bilinen yükseklik olmadan açı hesabı kesin kaynak kanıtı değildir.

```powershell
# Sabit bilinen Güneş ile sentetik örnek
python -m aiforensics demo-solar --out outputs/p2_s04_demo
# Mevcut manifestten hesapla
python -m aiforensics analyze-solar --input outputs/p2_s04_demo/p2_s04_fixture.json --image outputs/p2_s04_demo/p2_s04_fixture.png --out outputs/p2_s04_analysis
# Fiziksel yön kestirimi sentetik stres deneyi
python scripts/p2_solar_benchmark.py --trials 80 --out outputs/p2_s04_benchmark.json
# UTC zaman/enlem/boylamdan NOAA yaklaşık Güneş konumu ve yanlış saat karşılaştırması
python scripts/p2_solar_ephemeris_demo.py
```

Astronomik eşleştirme dışarıdan bildirilen zaman ve konuma dayanır; NOAA'nın yaklaşık formüllerini kullanır, yüksek hassasiyetli NREL SPA değildir. Güneş ufuk altında veya eşleşmeler yetersiz olduğunda `INDETERMINATE`; `INCONSISTENT_UNDER_ASSUMPTIONS` ise **AI üretimi** demek değildir.

Matematik ve manifest alanları: [`docs/P2_S04_SOLAR_SHADOW_PHYSICS.md`](docs/P2_S04_SOLAR_SHADOW_PHYSICS.md).

## P2-S05 — Penumbra ve umbra matematiksel profili

```powershell
# Tamamen sentetik ve bilinen ışık açılı kalibre ışınım profilleri
python -m aiforensics demo-penumbra --out outputs/p2_s05_demo
# Anotasyonlu 1B irradiance edge manifestini analiz et
python -m aiforensics analyze-penumbra --input outputs/p2_s05_demo/p2_s05_fixture.json --out outputs/p2_s05_check
# Yalnız önceden kalibre edilmiş doğrusal 2B numpy ışınım verisinden özel kesit çıkar
python -m aiforensics sample-penumbra --npy linear_image.npy --transects annotated_transects.json --out outputs/edge_profiles.json
# Bilinen fiziksel parametreli stres deneyleri, hataları atlamaz
python scripts/p2_penumbra_benchmark.py --trials 80 --out outputs/p2_s05_benchmark.json
```

Gölge sınırındaki profil **doğrusal göreli irradiance** olarak sağlanmalıdır: JPG/PNG RGB sayıları doğrudan doğruya fiziksel ışık şiddeti değildir. Tek profilden 3B ışık boyutunu kesin çıkarmayız. Ölçümün neyi tanımladığı ve tüm varsayımlar: [`docs/P2_S05_PENUMBRA_UMBRA_PHYSICS.md`](docs/P2_S05_PENUMBRA_UMBRA_PHYSICS.md).

## P3-R01 — Düzlem aynada sanal nokta ve yansıma kanıtı

```powershell
python -m aiforensics demo-mirror --out outputs/p3_r01_demo
python -m aiforensics analyze-mirror --input outputs/p3_r01_demo/p3_r01_fixture.json --image outputs/p3_r01_demo/p3_r01_fixture.png --out outputs/p3_r01_check --tolerance-px 3
python scripts/p3_mirror_benchmark.py --trials 80 --out outputs/p3_r01_benchmark.json
```

`object_world_xyz` ile gözlenen `reflection_xy` eşleşmesi, kamera `K/R/t` ve ayna düzlemi **dışarıdan bilinmelidir**. `p3_r01_report.json` bağımsız sahtecilik sonucu değil **fiziksel varsayım altındaki ölçüm**dür. Yansıma geometrisi `docs/P3_R01_PLANAR_MIRROR_PHYSICS.md` içinde detaylıdır.

## P3-R02 — Snell yasasıyla hava, su ve düz cam levha

```powershell
# Bilinen yüzey, kamera ve su kırılması; tam kontrollü sentetik pozitif/negatif fixture
python -m aiforensics demo-refraction --out outputs/p3_r02_water
# Paralel cam levha, tam açısal yön kayması sıfır olsa bile yanal piksel kayması var
python -m aiforensics demo-refraction --model parallel_slab --out outputs/p3_r02_glass
# Anotasyonlu bağımsız 3B nesne + gözlenen piksel girişi
python -m aiforensics analyze-refraction --input outputs/p3_r02_water/p3_r02_fixture.json --image outputs/p3_r02_water/p3_r02_fixture.png --out outputs/p3_r02_check --tolerance-px 3
# İki ortam modeliyle 80 tekrarlı kontrollü sentetik stres testi
python scripts/p3_refraction_benchmark.py --trials 80 --out outputs/p3_r02_benchmark.json
# Yalnız tek arayüzde, açıkça ayrılmış train vs holdout noktalarından n_layer kestir
python -m aiforensics estimate-refraction-index --input outputs/p3_r02_water/p3_r02_fixture.json --out outputs/p3_r02_index
```

Bu modül genel kırılma indislerini ve düz yüzeyi fotoğraftan otomatik bulmaz. Yalnız tek arayüzde, bağımsız 3B nokta anotasyonu ve ayrık eğitim/holdout bölümüyle **koşullu `n_layer` kestirimi** sağlar; nesne noktaları ile görüntüdeki karşılıkları haricen verilmelidir. `n_camera`, `n_layer`, `n_beyond` ve `thickness_world` alanları, ölçülmüş/bilinen fiziksel parametre varsayımıyla kullanılır. Gözlenen kırılma konumu ile modellerden hesaplanan pikselin farkı bir **fiziksel varsayım testi**, tek başına AI tespit sonucu değildir. Teknik açıklama: [`docs/P3_R02_REFRACTION_GEOMETRY.md`](docs/P3_R02_REFRACTION_GEOMETRY.md).

## P3-R03 — Birden fazla aynada ardışık yansıma ve sanal görüntü zincirleri

```powershell
# Bilinen kalibre kamera ve iki sonlu ayna ile kontrollü 3B sahne
python -m aiforensics demo-mirror-chain --out outputs/p3_r03_demo

# Nesneden kameraya ayna sırası + bağımsız 3B nesne/görüntü anotasyonları
python -m aiforensics analyze-mirror-chain `
  --input outputs/p3_r03_demo/p3_r03_fixture.json `
  --image outputs/p3_r03_demo/p3_r03_fixture.png `
  --out outputs/p3_r03_analysis --tolerance-px 3

# Tekrarlanabilir 60 sentetik stres deneyi
python scripts/p3_mirror_chain_benchmark.py --trials 60
```

Her kamera/ayna/nesne noktası ve **nesneden kameraya doğru yansıma sırası** önceden bilinmelidir. Bir sanal görüntünün matematiksel varlığı tek başına görünür yansıma kanıtı değildir: sonlu poligon, yansıtıcı yüz ve gerçek 3B ışın yolu ayrıca kontrol edilir. Geçerli ışın yolundan sapma bir fiziksel varsayım testidir, **AI üretimi kararı değildir**. Matematik ve veri sözleşmesi: [`docs/P3_R03_MULTI_MIRROR_CHAIN.md`](docs/P3_R03_MULTI_MIRROR_CHAIN.md).

## Komutlar

```powershell
# Örnek gerçek fotoğraf *içeriği* (G03) ve fotoğrafa uygulanan bilinen homografi (G04)
python scripts/real_photo_experiments.py

# Zemin/cephe bölgesi (poligonlar haricen anotasyonlu)
python -m aiforensics analyze-g03-regions --input data/architectural/scene_regions.json --out outputs/g03_regions

# Gerçek fotoğraf çiftinde açıklayıcı eşleşme analizi
python -m aiforensics validate-g04-pair --image-a images/photo_a.jpg --image-b images/photo_b.jpg --out outputs/g04_pair

# G02 York gerçek kamera referansından manifest hazırlama (foto ve .mat gerekir)
python scripts/prepare_york_manifest.py --image data/YorkUrbanDB/P000/P000.jpg --camera-parameters data/YorkUrbanDB/cameraParameters.mat --labels data/annotations/P000_lines.json
python -m aiforensics validate-g02-real --input data/YorkUrbanDB/P000/P000.g02_manifest.json --out outputs/real_g02

# Önceki v0.4 komutları çalışmaya devam eder
python -m aiforensics demo --out outputs/demo
python -m aiforensics auto-g03 images/corridor.jpg --out outputs/g03_auto
python scripts/g03_auto_demo.py
python scripts/g04_demo.py
```

`examples/g03_region_manifest_template.json` giriş şeması örneğidir; koordinatları gerçek fotoğrafın çözünürlüğüne göre değiştir ve JSON'u fotoğrafla **aynı klasöre koy**. Gerçek fotoğraf, paketle birlikte dağıtılmıyor. Şüpheli veya yanlış desenler otomatik olarak fizik ihlali sayılmaz.

## Gerçek deneylerin kapsamı

`scikit-image` kitaplığındaki **gerçek fotoğraf içerikleri** (tuğla deseni ve fırlatma sahnesi) ile G03b tekrar adayları araştırıldı; G04'te bu fotoğrafın ikinci görünüşü yazılımla üretilip homografi kontrol edildi. Gerçek kameradan bağımsız alınmış ikinci çekim değildi. Ayrıca iki gerçek stereo çekimden oluşan, derinliği değişen motosiklet sahnesi otomatik eşleşme stres testi olarak işlendi; tek homografinin bütün sahneyi açıklaması beklenmez. Gerçek zemin/cephe semantic IoU, eleman precision/recall, gerçek **G02 referans-K** ve gerçek **G04 iki çekim ground-truth homografi** henüz ölçülmedi.

Eksiksiz protokol: [`docs/P1_REAL_PHOTO_VALIDATION_V05.md`](docs/P1_REAL_PHOTO_VALIDATION_V05.md)

## Neden AI sınıflandırması yok?

Bir CGI ya da AI üretimi fiziksel yasalarla tam tutarlı olabilir. Bir gerçek fotoğraf ise yanlış eşleşme, görüntü işleme veya perspektif düzeltmesi nedeniyle tutarsız görünebilir. Bu sistem şu anda yalnız **model altında geometrik anomali bulguları** ölçer; kaynağın AI olup olmadığını ilan etmez.

## Yayın durumu

**G01–G04, P2-S01/S02/S03/S04/S05 ve P3-R01/R02 sentetik/matematiksel regresyonlar: test edildi. P2-S01/S02/S03 için gerçek veri kabulü: DEFERRED. G02 gerçek kamera, G03b semantik/nesne eşleştirme, G04 bağımsız düzlem doğrulaması: FINAL-VALIDATION BACKLOG.**

Gerçek fotoğraf ölçümleri, Windows gerçek cihaz kabul testi ve GitHub'a push bu geliştirmede yapılmadı. P2 gölge doğrultu testi, 3B ışık kaynağının konumunu tek fotoğraftan tekil olarak elde edemez.

## P4-O01 (v0.14.0) — Brown–Conrady kamera lens distorsiyonu

P1/G01–G04, P2/S01–S05 ve P3/R01–R03 korunarak **P4-O01** eklendi. Beş terimli Brown–Conrady (radyal `k1/k2/k3`, teğetsel `p1/p2`) ileri/ters izdüşüm, kalibrasyon tasarım matrisi koşul testi, IRLS katsayı kestirimi, **ayrık train/holdout** yeniden izdüşüm RMSE ve **doğrulanmış düz çizgilerin** önce/sonra RMS sapma ölçümü uygulanır. Görüntüden otomatik lens modelini veya AI kökenini tespit etmez; bağımsız ideal geometri anotasyonlarına ve aynı fotoğraf düzenine ait `K` matrisine ihtiyaç duyar.

```powershell
# Tamamen sentetik eğrilmiş doğru ve lens kalibrasyonu
python -m aiforensics demo-lens --out outputs/p4_o01_demo

# Kullanıcının bağımsız ölçülmüş ideal/gözlenen eşleşmeleri
python -m aiforensics analyze-lens --input measurements.json --image frame.png --out outputs/p4_o01_analysis

# Kontrollü tekrarlı sentetik test ve negatif örnekler
python scripts/p4_lens_benchmark.py --trials 80 --out outputs/p4_o01_benchmark.json
python scripts/p4_lens_negative_controls.py
```

JSON kanıt raporunda `holdout_rmse_px`, `holdout_uncorrected_rmse_px`, tüm katsayılar, örneklenen fiziksel terslenebilirlik kontrolleri ve `line_holdouts` alanında doğrultu düzeltmesi bulunur. Anotasyonlu çizgi ve düzeltilmiş görüntü ayrı dosyalara kaydedilir. Ayrıntılar: [`docs/P4_O01_BROWN_CONRADY_LENS_PHYSICS.md`](docs/P4_O01_BROWN_CONRADY_LENS_PHYSICS.md).

**Durum:** Sadece sentetik modül ve regresyon testleri. Gerçek fotoğraf saha doğrulaması / Windows kabulü projenin sonunda yapılacak. Sonraki optik çalışma P4-O02: alan derinliği, defocus blur ve odak düzlemi.


## P4-O02 (v0.15.0) — Geometric defocus and depth of field

**Added:** axial thin-lens image distance, focus-plane sensor position, millimetre/pixel circle-of-confusion diameter, near/far depth-of-field limits (with infinity), hyperfocal distance, normalized uniform-disc PSF, and independent CoC measurements with uncertainty propagation. Optional focus estimation uses train records only and validates separate holdouts. All measurements are conditional on independently known focal length, aperture, native sensor pixel pitch, focus, depth and measured optical PSF diameter. **No arbitrary-image focus inference, and no AI-origin conclusion.**

```powershell
python -m aiforensics demo-defocus --out outputs/p4_o02_demo
python -m aiforensics demo-defocus --fit-focus --out outputs/p4_o02_fit_demo
python -m aiforensics analyze-defocus --input outputs/p4_o02_demo/p4_o02_fixture.json --out outputs/p4_o02_check
python scripts/p4_defocus_benchmark.py --trials 80 --out outputs/p4_o02_benchmark.json
pytest -q
```

See [`docs/P4_O02_THIN_LENS_DEPTH_OF_FIELD.md`](docs/P4_O02_THIN_LENS_DEPTH_OF_FIELD.md) for derivation, input JSON example, model limits and acceptance boundaries. Real camera and field verification remains **DEFERRED** until completion of all development stages.

## P4-O03 (v0.16.0) — Odak uzaklığı, kamera görüş alanı ve perspektif

**Yeni modül:** `aiforensics.optical_consistency` — zero-skew `K`, kamera `R,t`, fiziksel sensör piksel aralığı, kırpma/yeniden boyutlandırma, FoV, 3B→2B yeniden izdüşüm ve bağımsız nokta/segment/VP doğrulaması. İsteğe bağlı `fit_focal_from_train` modu yalnız eğitim noktalarından `fx,fy` kestirir; test noktaları kalibrasyonda kullanılmaz. Brown–Conrady ile **known-K** düzeltmesi P4-O01 üzerinden yapılabilir. Kestirim ve tutarlılık sonuçları **AI kökeni kararı değildir**.

```powershell
python -m aiforensics demo-optics --out outputs/p4_o03_demo
python -m aiforensics demo-optics --fit-focal --out outputs/p4_o03_fit_demo
python -m aiforensics analyze-optics --input outputs/p4_o03_demo/p4_o03_fixture.json --out outputs/p4_o03_check
python scripts/p4_optical_benchmark.py --trials 80 --out outputs/p4_o03_benchmark.json
python -m pytest -q
```

Model varsayımları, off-center FoV formülü, native-sensor/resize dönüşümü, bağımsız kanıt şeması ve hata durumları: [`docs/P4_O03_FOCAL_FOV_PERSPECTIVE.md`](docs/P4_O03_FOCAL_FOV_PERSPECTIVE.md). Bu sürümdeki testler sentetiktir; nihai gerçek kamera ve Windows cihaz kabulü kararlaştırıldığı gibi en sona bırakılmıştır. P4-O04 vinyet fotometrisi artık v0.17.0 içinde sentetik doğrulamaya eklendi; P5 3B sahne fiziği sıradaki geliştirme alanıdır.

## P5-D01 — Derinlik, nesne–zemin teması ve destek yüzeyi (v0.18.0)

P5 geliştirmesi başladı. **Kalibre kamera + bağımsız metrik destek düzlemi** verilince görüntü ışınının zeminle 3B kesişimini koşullu olarak bulur. Bağımsız 3B temas koordinatı, bilinen nesne yüksekliği ve/veya ağırlık merkezi girildiğinde destek/tutarlılık testleri yapar. Zemine ışın düşmesi tek başına temas kanıtı değildir; veri yetersizse `INDETERMINATE` döner.

```powershell
python -m aiforensics demo-depth-contact --out outputs/p5_d01_demo
python -m aiforensics analyze-depth-contact --input outputs/p5_d01_demo/p5_d01_fixture.json --out outputs/p5_d01_check
python scripts/p5_depth_contact_benchmark.py --trials 80
```

Tam veri sözleşmesi, hata modeli, fiziki varsayımlar ve sınırlamalar için [`docs/P5_D01_DEPTH_CONTACT_SUPPORT.md`](docs/P5_D01_DEPTH_CONTACT_SUPPORT.md). Gerçek saha görüntüleri ve Windows kullanıcı kabulü **en son** gerçekleştirilecek.


## P5-D02 — Multi-plane Occlusion & Independent 3D Depth (v0.20.0)

Modelled opaque planar surfaces are intersected against calibrated rays and sorted by metric ray depth. Independent visibility annotations and independent 3D anchors can contradict the **conditional** modeled ordering. Unverified annotations, overlapping boundaries, tied depths or missing scene geometry are `INDETERMINATE`. Transparent surfaces are not treated as hard blockers.

```powershell
python -m aiforensics demo-occlusion --out outputs/p5_d02_demo
python -m aiforensics analyze-occlusion --input outputs/p5_d02_demo/p5_d02_fixture.json --out outputs/p5_d02_check
python scripts/p5_occlusion_benchmark.py --trials 80
python -m pytest -q
```

Full input contract, conditional equations, independent evidence gate and limitations: [`docs/P5_D02_MULTIPLANE_OCCLUSION.md`](docs/P5_D02_MULTIPLANE_OCCLUSION.md). **Real images, camera reference measurements and Windows user acceptance remain deliberately deferred until final validation.** Next stage: **P5-D03 — gravity, physical support and constrained mechanics**.


## P5-D03 — Rigid Body Static Equilibrium (v0.20.0)

```powershell
python -m aiforensics demo-static --out outputs/p5_d03_demo
python -m aiforensics analyze-static --input outputs/p5_d03_demo/p5_d03_fixture.json --out outputs/p5_d03_analysis
python scripts/p5_static_benchmark.py --trials 80 --out outputs/p5_d03_benchmark.json
python -m pytest -q
```

Input JSON includes `gravity_acceleration_world_m_s2`, `support_surfaces`, `objects`, metric center-of-mass or independent `mass_components`, complete contact points, friction, and external forces. No RGB-only equilibrium verdict. Mathematical derivations, LP safeguards, independent-data gate and limitations: [`docs/P5_D03_STATIC_EQUILIBRIUM.md`](docs/P5_D03_STATIC_EQUILIBRIUM.md).

**Policy unchanged:** develop P6, P7 and P8, complete integration and synthetic regression; independent real photo/physical measurement benchmarks and Windows device acceptance come last.

---

## P6-M01 v0.21.0 — Lambertian albedo, BRDF, radiometry and energy conservation

This development adds `src/aiforensics/material_physics.py` and `material_synthetic.py`, with independent train/holdout evaluation of a **known-illumination Lambertian material**. The corresponding engineering note is [`docs/P6_M01_LAMBERTIAN_BRDF_ENERGY.md`](docs/P6_M01_LAMBERTIAN_BRDF_ENERGY.md).

**Commands** (from project root with package installed):

```powershell
python -m aiforensics demo-material
python -m aiforensics demo-material --known-albedo
python -m aiforensics analyze-material --input outputs/p6_m01_demo/p6_m01_fixture.json --out outputs/p6_m01_check
python scripts/p6_material_benchmark.py --trials 80
python -m pytest -q
```

A separate `audit-brdf` CLI checks tabulated BRDF reciprocity and discrete hemispherical energy conservation. The output gives conditional `CONSISTENT`, `INCONSISTENT_UNDER_ASSUMPTIONS`, or `INDETERMINATE` verdicts about **the stated physical model only**. Inputs are calibrated **linear radiance and irradiance**, not arbitrary JPEG pixel values. Unknown light–albedo scale, missing independent surface normal data, and missing provenance cannot justify a confident inference. **Do not interpret these results as AI-image detection.** Real photographic measurements and Windows device acceptance remain intentionally deferred until P6–P8 development is complete.

---

## P6-M02 v0.22.0 — GGX / Cook–Torrance / Schlick single-scattering specular BRDF

New module: `src/aiforensics/microfacet_physics.py`. Controlled physical tests, independently specified `F0`, surface normal, light/view direction and *calibrated linear* radiance/irradiance. `roughness` is known or fitted **only on train** samples; holdout radiances test the projected physical model. This is a separate **specular-only** branch alongside M01 Lambertian, not a claim of full material decomposition from RGB.

```powershell
python -m aiforensics demo-microfacet --out outputs/p6_m02_demo
python -m aiforensics demo-microfacet --known-roughness --out outputs/p6_m02_known
python -m aiforensics analyze-microfacet --input outputs/p6_m02_demo/p6_m02_fixture.json --out outputs/p6_m02_check
python -m aiforensics audit-microfacet-energy --roughness .45 --f0 .04 .04 .04
python scripts/p6_microfacet_benchmark.py --trials 80
python -m pytest -q
```

Detailed mathematics, admissible inputs, limitations and provenance: [`docs/P6_M02_COOK_TORRANCE_GGX.md`](docs/P6_M02_COOK_TORRANCE_GGX.md).

**Project order remains:** P6 physics extensions → P7 sensor noise/PRNU → P8 cross-module statistical evidence and audit → all-system integration → final real images, independent physical measurements and native Windows acceptance. This version does not claim real-world detection accuracy or AI origin determination.

## P6-M03 — Birleşik difüz + speküler malzeme

```powershell
python -m aiforensics demo-combined-material --out outputs/p6_m03_demo
python -m aiforensics demo-combined-material --known-material --proxy --out outputs/p6_m03_proxy_demo
python -m aiforensics analyze-combined-material --input outputs/p6_m03_demo/p6_m03_fixture.json --out outputs/p6_m03_check
python -m aiforensics audit-combined-energy --input outputs/p6_m03_demo/p6_m03_fixture.json --out outputs/p6_m03_energy_audit.json
python scripts/p6_combined_benchmark.py --trials 80
```

**Geliştirme sırası:** P7 sensör fiziği, P8 birleşik istatistiksel kanıt ve en sonunda bağımsız gerçek fotoğraf, metrik ölçüm ve Windows kabulü. Sayısal/sentetik testler gerçek dünya tespit başarımına karşılık gelmez; bu yazılım hiçbir BRDF ihlalinden AI kökeni çıkarmaz.

## P7-S01 v0.24.0 — Poisson shot noise, Gaussian read noise, karanlık akım ve RAW sensör fiziği

Yeni kaynaklar: `sensor_noise.py`, `sensor_synthetic.py`, `scripts/p7_sensor_benchmark.py` ve `tests/test_p7_s01_sensor.py`. Geliştirme mevcut **P1–P6** matematiksel fizik çekirdeklerini korur.

**Fizik modeli:** `Poisson(s+dark_rate*t) + Normal(0, read_noise_e²)` elektronları; elektron/ADU kazancı, sensör full-well doygunluğu, ADC kuantalama/clip; karanlık ve flat-field kalibrasyonuyla ortalama/varyans ve SNR. Ayrı `train`/`holdout` rolleri. Bilinen parametre modu ve sadece train verisiyle kazanç/okuma gürültüsü/karanlık akım kestirimi bulunur. Fiziksel varsayım/provenans veya uncensored RAW kayıt eksikse kesin karar verilmez.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest -q
python -m aiforensics demo-sensor-noise
python -m aiforensics demo-sensor-noise --fit-parameters --out outputs/p7_s01_fit
python -m aiforensics analyze-sensor-noise --input outputs/p7_s01_demo/p7_s01_fixture.json --out outputs/p7_s01_check
python scripts/p7_sensor_benchmark.py --trials 80
```

`outputs/p7_s01_demo` dizininde sentetik `p7_s01_fixture.json`, `p7_s01_report.json` ve `p7_s01_photon_transfer.png` bulunmaktadır. Opsiyonel `summarize-raw-stack` komutu lineer RAW `.npy` dosyasından sabit-piksel **zamansal** varyansı çıkarır; PRNU analizi veya bağımsız photon flux kalibrasyonu yapmaz. Kaynak sözleşmesi, hata durumları ve varsayımlar için [`docs/P7_S01_POISSON_GAUSSIAN_SENSOR_NOISE.md`](docs/P7_S01_POISSON_GAUSSIAN_SENSOR_NOISE.md).

**Gerçek fotoğraf/Windows saha kabulü yine projenin en sonunda.** P7-S02 sensör PRNU/DSNU; ardından P8 istatistiksel kanıt birleşimi geliştirilecek. `INCONSISTENT_UNDER_ASSUMPTIONS`, tek başına yapay zekâ kökeninin kanıtı değildir.

## P7-S02 v0.25.0 — PRNU / DSNU ve RAW sensör parmak izi

P7-S01 sensör shot/read/dark fizik modelinin üzerine, ayrı `dark` / `flat` RAW karelerinden piksel sabit desen haritası (`sensor_fingerprint.py`) ve bağımsız parmak izi eşleştirmesi (`sensor_fingerprint_synthetic.py`) eklendi. Referans ve sorgu için farklı RAW yığınları, train/holdout ayrımı, PRNU/DSNU Pearson korelasyonu ve yüksek-geçiren gürültü haritaları kullanılır. Aynı referans karelerinin holdout olarak yeniden kullanılmasına SHA-256 içerik kontrolü uygulanır.

```powershell
python -m pytest -q
python -m aiforensics demo-sensor-fingerprint --out outputs/p7_s02_demo
python -m aiforensics analyze-sensor-fingerprint --input outputs/p7_s02_demo/p7_s02_fixture.json --out outputs/p7_s02_check
python scripts/p7_fingerprint_benchmark.py --trials 80
python scripts/p7_fingerprint_negative_controls.py
```

Sentetik 80 deneyde 80 doğru eşleşme ve 80 farklı sensör ayrımı elde edildi; birleşik 753 otomatik test geçti. Bunlar gerçek kamerada yanlış alarm oranı veya AI kökeni sınıflandırma başarısı değildir. **Gerçek fotoğraf için kimlik eşikleri kalibre edilmedi**; bağımsız köken/aydınlatma/hizalama güvenceleri bulunmadığında analiz `INDETERMINATE` verir. Ayrıntılar [`docs/P7_S02_PRNU_DSNU_SENSOR_FINGERPRINT.md`](docs/P7_S02_PRNU_DSNU_SENSOR_FINGERPRINT.md) ve [`docs/P7_S02_EXPERIMENT_LOG.md`](docs/P7_S02_EXPERIMENT_LOG.md) içinde.

**Mühendislik sırası:** P8 istatistiksel kanıt birleşimi → sistem genelinde uçtan uca modül entegrasyonu → bütün modüllerin nihai gerçek görüntü / gerçek sensör / Windows kabul testleri. GitHub'a gönderim bu paket kapsamında yapılmadı.

## P8-E01 — Ortak fiziksel kanıt sözleşmesi (v0.26.0)

P1–P7 kapsamında geliştirilen 24 modüle ait bağımsız fiziksel ölçümler yeni
`aiforensics.evidence_contract` API'sine bağlanabilir. Parametrik null model,
ölçüm/model belirsizliği ve hata korelasyonu bağımsız doğrulanmadığında
**hipotez testi yapılmaz** (`INDETERMINATE`). Eski modül raporları tanımlayıcı
SHA-256 izleriyle eklenebilir; eski sentetik `PASS` otomatik olarak gerçek
veri kanıtına yükseltilmez.

```powershell
python -m aiforensics list-evidence-modules
python -m aiforensics analyze-evidence --input examples/p8_e01_evidence.json --out outputs/p8_e01_analysis
python -m pytest -q
```

[Kanıt matematiği ve veri sözleşmesi](docs/P8_E01_EVIDENCE_CONTRACT.md).
P8-E02 kanıt bağımlılıkları, çoklu hipotez kontrolü ve birleştirme;
P8-E03 açıklanabilir kanıt raporu. Gerçek cihaz doğrulaması en son.

## P8-E02 — Dependency-aware evidence aggregation (v0.27.0)

- [Python fusion module](src/aiforensics/evidence_fusion.py) — shared input and calibration lineage, connected dependency components.
- [CLI and examples](examples/p8_e02_fusion.json) — `python -m aiforensics analyze-fusion --input examples/p8_e02_fusion.json --out outputs/p8_e02`.
- [25 synthetic unit and integration tests](tests/test_p8_e02_fusion.py).
- [Mathematical design and failure gates](docs/P8_E02_DEPENDENT_EVIDENCE_FUSION.md).
- [Deterministic synthetic stress benchmark](scripts/p8_fusion_benchmark.py).

**Interpretation:** Within-component Bonferroni and between-component Holm correct conditional hypothesis tests under their declared assumptions; they do **not** establish AI-image origin. Unverified source lineage, independent calibration or hypothesis pre-registration produce an inconclusive/blocked result. Real camera datasets and Windows device validation remain the final acceptance phase.

**Engineering state:** local integrated regression passed 817 tests; GitHub Actions should be independently checked for this commit. P8-E03 combined human-readable reports and overall integration follow.


## P8-E03 — Açıklanabilir fiziksel kanıt raporu (v0.28.0)

`python -m aiforensics explain-evidence --input examples/p8_e03_explainable.json --out outputs/p8_e03`

Çevrimdışı HTML ve JSON: her ölçüm için varsayımlar, belirsizlik, E01 hipotezi, E02 bağımlılık grubu ve karar gerekçesi. **AI köken kararı veya gerçek veri doğrulaması değildir.** [Teknik belge](docs/P8_E03_EXPLAINABLE_REPORT.md).


## P9-I01 — Masaüstü ve modül entegrasyonu (v0.29.0)

`pip install -e ".[dev,desktop]"` ardından `fakeproof-desktop` ile dokuz sayfalı çevrimdışı arayüz çalıştırılır. P1–P7'nin 24 fizik motoru ve E01–E03, ölçüm manifestleriyle CLI köprüsü üzerinden çağrılır. [Kapsam ve sınırlar](docs/P9_I01_DESKTOP_INTEGRATION.md). Gerçek kamera/Windows kullanıcı kabulü son aşamadadır.


## P9-I02 — Etkileşimli çizim ve kalibrasyon editörü (v0.30.0)

Kalibrasyon ve Fiziksel Ölçümler ekranlarından görüntü üzerinde nokta, çizgi, çoklu çizgi, çokgen ve ROI çizilebilir; pan, zoom, düzenleme, undo/redo, piksel ölçümü, SHA-256 kaynak kilidi ve yerel anotasyon JSON saklama desteklenir. Kullanıcı etiketli X/Y/Z çizgi grupları G02 için **doğrulanmamış taslak** oluşturur. [Mühendislik sözleşmesi](docs/P9_I02_INTERACTIVE_ANNOTATIONS.md). Gerçek kamera metrik kabulü son aşamadadır.


## P9-I03 — Modül formları ve güvenli planlama (v0.31.0)

**27 modül** (P1–P7: 24 fiziksel; P8-E01/E02/E03: 3 istatistiksel) için ayrı JSON veri formu ve görüntü seçimi. Her modülün gerçek CLI giriş sözleşmesine uygun örneklerden tipli alan düzenleyici, yapısal doğrulama, bağımlılık sıralaması, SHA-256 kaynağı, kontrollü yürütme ve denetim günlüğü.

`fakeproof-desktop` → **Analiz Planı** → **Modül Formları ve Planlayıcıyı Aç**.

Sentetik şablonlar asla gerçek kamera kalibrasyonu ya da görüntü özgünlüğü doğrulaması değildir; başka modülden otomatik bağımsız ölçüm türetilmez. [P9-I03 teknik belge](docs/P9_I03_MODULE_FORMS_WORKFLOW.md).


## P9-I04 — Görsel Katman, Kanıt ve Rapor Gezgini (v0.32.0)

Masaüstü arayüzünün **Fiziksel Ölçümler / Kanıt İnceleme / Bağımlılık Grafiği / Rapor Dışa Aktarma** sayfalarından P9-I04 gezginini açın. Özgün görüntü, SHA-256 bağlı anotasyon ve kullanıcı tarafından açıkça ilişkilendirilen PNG katmanları birlikte incelenebilir. Yalnız gerçek E03 kayıtlarındaki bulgu ve bağımlılıkları görselleştirir. Kullanıcı bağlantıları `user_asserted_not_verified` durumunda kalır; otomatik doğrulanmış fotoğraf eşleşmesi veya AI kökeni olasılığı üretmez.

Windows çevrimdışı PyInstaller `--onedir` **derleme betiği**: `scripts/build_windows_desktop.ps1`. Betiğin varlığı gerçek Windows cihaz kabulü veya imzalanmış kurulum paketi değildir. [P9-I04 teknik dokümanı](docs/P9_I04_EVIDENCE_REVIEW_PACKAGING.md).


## P9-I05 — Tek kullanıcı akışı (v0.33.0)

Yerel proje seçimi, gerçek kayıtlara bağlı beş adımlı gezinme bandı, seçili görüntü–anotasyon ve koşum–kanıt–rapor yönlendirmesi. Otomatik test PASS, gerçek kamera kabulü değildir. [Teknik belge](docs/P9_I05_UNIFIED_DESKTOP_JOURNEY.md).


## P9-I06 — Birleşik kullanıcı akışı (v0.34.0)

Koyu temalı ana ekranda gerçek proje sayaçları, doğrulanmış görüntü hash önizlemesi, beş aşamalı gezinme ve E01→E02→E03 kontrollü sentetik deney düğmesi. Bütün fiziksel modüller kendi manifest/kalibrasyon gereksinimlerini korur; tek görüntüden otomatik AI kökeni kararı verilmez.

`python scripts/p9_i06_synthetic_e2e.py --workspace outputs/p9_i06_demo`

Ayrıntılar: [P9-I06 teknik notu](docs/P9_I06_FINAL_UI_AND_SYNTHETIC_JOURNEY.md).
