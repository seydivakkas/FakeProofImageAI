> Geliştirme politikası (2026-10-10): Önce P2–P8 ve kalan kod iyileştirmeleri, sentetik matematiksel testler ve hata senaryoları; gerçek kamera verileri ve saha benchmark/nihai kabul en son. Mevcut HOLD notları geliştirme önceliği değil, son doğrulama borcudur.

# Physics-first roadmap

| Paket | Alan | Durum |
|---|---|---|
| P0 | Matematiksel görüntü modeli ve deney altyapısı | İlk iskelet; tam kabul açık |
| P1 / G01 | Sonlu VP kestirimi ve ölçüm | İlk implementasyon; gerçek dünya validasyonu açık |
| P1 / G02–G04 | Diklik, eş aralık, homografi | Sentetik matematiksel testler mevcut; semantik otonomi ve gerçek kamera doğrulaması son fazda |
| P2 / S01 | Nesne–gölge eşleşmelerinden görüntüdeki ışık izdüşümü | Sentetik regresyon mevcut; gerçek veri doğrulaması son fazda |
| P2 / S02–S05 | Çoklu ışık, 3B ışık/güneş, umbra–penumbra ışınım profilleri | Sentetik matematiksel testler mevcut; gerçek veri en sonda |
| P3 / R01–R03 | Düzlem ayna, Snell kırılması ve çoklu ayna zinciri | Sentetik testler mevcut; gerçek görüntü kabulü son fazda |
| P4 | Optik, distorsiyon, alan derinliği, FoV ve vinyet | Sentetik matematiksel testler mevcut |
| P5 | D01 temas, D02 çoklu düzlem/örtüşme, D03 statik denge | Sentetik çekirdek mevcut, gerçek kabul en son |
| P6 | Malzeme ve fotometri | Bekliyor |
| P7 | Sensör gürültüsü ve PRNU | Bekliyor |
| P8 | Belirsizlik, hipotez testi, rapor | Başlangıç alanları; kalibrasyon açık |

## G01 matematiksel sözleşme

Giriş: N adet `x1,y1,x2,y2` çizgi parçası, `height,width`, piksel eşiği.
Çıkış: M adet sonlu VP hipotezi; her biri inlier indeksleri, residual,
açısal çeşitlilik, bootstrap kararlılığı. Etiket: `NO_AI_ORIGIN_CONCLUSION`.

- Çizgi `l=(a,b,c)`, normalizasyon `sqrt(a²+b²)=1`.
- VP `v=(x,y,1)` için `r=lᵀv`, birim piksel.
- RANSAC farklı yönlere ait çizgileri aykırı gözlem sayar, *sahte* saymaz.
- Model sayısı üç ile sınırlıdır; görüntü sınıflandırılmıyor.
- Yerel sentetik benchmark bilinen ground-truth VP'ye karşı ölçüm sağlar.

## G01 sonrasında yürütülecek kabul planı

1. Kare görünüşten projeksiyon, radial distorsiyon ve iki/üç VP üretimini test et.
2. Güç/duyarlılık ve eşik kalibrasyonu için farklı kameralar, çözünürlükler,
   fotoğraf türleri içeren gerçek validasyon seti edin.
3. Düşük yanlış alarm hedeflerini **önceden** veriyle belirle; bilinen etiketi
   ölçüm sırasında kullanma.
4. `RANSAC + Huber` ile ablation (RANSAC-only, LS-only), sağlamlık eğrileri.
5. Başarılı sonuçları ekran görüntüsü değil ölçülen JSON ve yeniden üretilebilir
   çalıştırma komutlarıyla paylaş.


### v0.7 — P2-S02 implementation

- Multiple robust projected shadow-ray families, exclusive assignment and ambiguity rejection: IMPLEMENTED / SYNTHETIC TESTED.
- Unknown-source real-world calibration: DEFERRED TO FINAL VALIDATION.
- P2-S03 plane/3D light geometry: NEXT DEVELOPMENT.
- P2-S04 sun azimuth/elevation, P2-S05 penumbra/lighting: LATER DEVELOPMENT.


## v0.8.0 — P2-S03

P2-S03 3B alıcı düzlem/kamera ve nesne-gölge eşleşmelerinden metrik ışık konumu (uygun gözlemlenebilirlikte) veya yalnız kaynak yönü hesaplama: sentetik geliştirme tamamlandı. S02 aday ailelerinden S03'e opsiyonel geçiş eklendi. Gerçek bağımsız kalibrasyon/veri benchmark'ı en son kabul aşamasında kalıyor. Sonraki modül P2-S04: güneş yüksekliği ve gölge boyu geometrisi.

## v0.10.0 — P2-S05

- Uniform disk / uniform strip kaynak geometrisinin kesit boyunca görünen ışık oranı: IMPLEMENTED.
- Koşullu açısal ışık kaynağı çapı, sabit kaynak hipotezinde çoklu yüksekliğe sahip kenar tutarlılığı ve belirsizlik yönetimi: IMPLEMENTED / SYNTHETIC TESTED.
- Sonlu dairesel örtücü için alıcı düzleminde umbra–penumbra bölgesi analitik sınırları: IMPLEMENTED / SYNTHETIC TESTED.
- Kalibre LINEAR `.npy` görüntü ve kullanıcı transect anotasyonu üzerinden 1D örnekleme, rapor ve overlay: IMPLEMENTED / SYNTHETIC TESTED.
- Otomatik gölge segmentasyonu, farklı ışık kaynakları için geniş açılı radyometrik model, kalibrasyonlu gerçek fotoğraf ölçümü: FINAL DEVELOPMENT / FINAL VALIDATION BACKLOG.
- Sıradaki mühendislik alanı: P3 düz ayna, yansıma geometrisi ve Snell kırılması; gerçek fotoğraf ölçümleri en sonda.


## v0.11.0 / P3-R01
- Planar mirror specular virtual-image geometry (K/R/t known externally), 3D polygon/normal checks, annotated pixel reprojection and correlated angular normal evidence.
- Snell refraction helper isolated from mirror consistency. Synthetic positive/negative regressions and CLI provided.
- P3-R02 refraction geometry now implemented and synthetic-tested; real-image ground-truth measurements remain final validation work.


## v0.12.0 / P3-R02
- Snell refraction across a single planar transparent interface and exactly parallel plane-plate modeled by monotone conserved tangential momentum solve: IMPLEMENTED / SYNTHETIC TESTED.
- Critical angle / total internal reflection on ray forward tracing, finite polygon aperture constraints and invalid-medium geometry: fail-closed.
- Known 3D object to predicted pixel, observed pixel to target-depth ray trace and theoretical apparent displacement: IMPLEMENTED.
- Transparent object segmentation, curved/nonparallel surface tracing, measured refractive indices/3D ground truth and camera field acceptance: LATER DEVELOPMENT / FINAL VALIDATION.
- Next P3-R03 multiple specular-reflection paths, then P4 camera lens optics.

## v0.13.0 / P3-R03

- Ordered finite 2D/3D planar mirror chains using independent K/R/t and 3D object annotations: IMPLEMENTED.
- Consecutive virtual-image points, observed inverse ray tracing, finite convex polygons, explicit reflective side, supplied-mirror occlusion and model-relative residuals: IMPLEMENTED / SYNTHETIC TESTED.
- Two-mirror controlled 60-seed stress benchmark and independent constructed three-mirror path regression: SYNTHETIC PASS. Four-bounce and repeated mirrors require further dedicated physical tests; repeated mirror IDs currently fail closed.
- Order discovery, scene occluders, automatic mirror/object detection, visual Fresnel/rough reflections and independent field acceptance: LATER DEVELOPMENT / FINAL VALIDATION.
- Next planned P4 optics: radial/tangential camera distortion, PSF, depth of field and image formation; real photo validation postponed until full development is complete.


## v0.17.0 / P4-O04 — Fotometrik vinyet

- P4-O03 kamera K ile cos⁴ ideal doğal ışınım düşüşü ve kaymış merkezli fenomenolojik log-radyal artık: IMPLEMENTED / SYNTHETIC TESTED.
- Düz-alan linear/dark-corrected örnek bölgelerinde rol bazlı train/holdout, pozlama kazancı, radyal parametreler, Jacobian koşul testi, kovaryans yaklaşımı ve güvenli düzeltme kazancı: IMPLEMENTED.
- Doğrusal `.npy` görüntülerden çakışmayan ROI örnekleme, CLI görsel raporu ve tekrar üretilebilir sentetik stres benchmark: IMPLEMENTED.
- Bir fotoğrafın merkez/kenar parlaklığından sahtecilik veya gerçek lens optiği hakkında kesin hüküm YOK.
- Gerçek RAW kalibre flat-field, dalga boyu/diyafram bağımlılığı, ISO/ISP/vinyet düzeltme zinciri ve bağımsız sensör model kabulü: FINAL VALIDATION.
- Sonraki fiziksel geliştirme: P5, 3B sahne/nesne derinliği, temas, yerçekimi; ardından P6 malzemeler, P7 sensör, P8 kanıt istatistiği.


## v0.18.0 — P5-D01

- [x] Mathematical camera-ray/support-plane 3D candidate reconstruction and finite support region
- [x] Conditional independent 3D anchor/known rigid upright height and static COM tests
- [x] Lens O01 distort/undistort forward/back compatibility, uncertainty/abstention, CLI
- [x] Synthetic regression and stress benchmark
- [ ] Automatic ground plane/true 3D depth from unconstrained real images (not identifiable without new assumptions)
- [x] P5-D02 — Multi-plane occlusion ordering and independent object/scene depth constraints (synthetic tests only)
- [ ] P5-D03 — Gravity, center-of-mass and support/contact hypotheses
- [ ] P6–P8 — Material/photometry, sensor forensics, probabilistic evidence fusion
- [ ] Final independently calibrated real camera/photo and Windows user acceptance (intentionally last)


## v0.19.0 — P5-D02
- [x] Multiple independently declared finite convex 3D planes and calibrated pixel rays.
- [x] Opaque nearest-hit ordering, transparent and single-sided polygon flags, near-tie abstention.
- [x] Independent visibility annotation and 3D metric anchor holdout checks, boundary/pixel noise guard.
- [x] Optional same-camera P5-D01 contact integration and reproducible synthetic benchmark.
- [ ] Final independent real-camera and true depth/occlusion references (project end).


## v0.20.0 — P5-D03

- Rijit cisim statik kuvvet/moment dengesi, bağımsız kütle merkezleri, temas destek poligonları, unilateral normal kuvvet ve Coulomb sürtünmesi: sentetik testli.
- Konservatif iç sürtünme konisi ve gevşetilmiş dış koni, LP çözümü: yeterli sertifika yoksa abstention.
- Yetersiz/tek görüntüden varsayılan COM, eksik temas veya kuvvetlerin belirsizliği kesin fiziksel kanıt yapılmaz.
- P6 malzeme ve fotometri, P7 sensör/PRNU, P8 istatistiksel birleşim geliştirilecek. Gerçek dünya ve Windows kabulü projenin sonunda.

## v0.21.0 / v0.22.0 — P6 materials

- [x] P6-M01 Lambertian diffuse, independent albedo/irradiance and BRDF energy audit (synthetic).
- [x] P6-M02 Cook–Torrance specular with isotropic GGX, Smith, Schlick and independent train/holdout roughness (synthetic).
- [x] P6-M02 numerical quadrature with sharp-lobe abstention; measured and modelled linear radiance, no AI-origin decision.
- [x] P6-M03 energy-bounded diffuse/single-scatter GGX BRDF mixture, illumination ambiguity, conditional phenomenological multiscattering proxy, multi-surface holdout; controlled synthetic tests only.
- [ ] P7 sensor noise / PRNU code and synthetic verification.
- [ ] P8 uncertainty, dependence-aware evidence fusion and statistical audit.
- [ ] System-wide integration before independent real photographic reference measurements and Windows acceptance, which remain final.

## v0.23.0 — P6-M03
- [x] Mathematically bounded convex diffuse/specular mixture and optional characterized proxy.
- [x] Multi-surface holdout, training-only albedo estimation, gamma/lighting-provenance and nonidentifiability guards.
- [x] Sampled hemisphere energy audit with sharp-lobe abstention, regression and synthetic stress benchmarks.
- [ ] True microfacet multi-bounce transport is not implemented; proxy not a physically validated replacement.
- [ ] P7 sensor noise/PRNU and P8 evidence fusion; independent real-camera and Windows acceptance at end.

## v0.24.0 — P7-S01 RAW sensor noise

- [x] Poisson photo/dark electron counts, Gaussian electronic read noise, electron/ADU gain, full-well and ADC clipping simulation.
- [x] Unsaturated RAW temporal mean/variance and SNR, quantization approximation with validity gates.
- [x] Train-only gain/read/dark fitting with photon/exposure identifiability checks and local covariance; holdout comparison with uncertainty guard band.
- [x] Optional `.npy` temporal stack per-pixel variance extraction (NOT pooled spatial PRNU).
- [x] Synthetic fixture, CLI, regression and stress experiments with negative controls.
- [ ] P7-S02: PRNU/DSNU, fixed-pattern noise, sensor fingerprints and calibration limitations.
- [ ] P8: statistical evidence dependencies, multiplicity and independent calibration.
- [ ] Final actual camera/RAW measurements and native Windows acceptance **after** development/integration.
