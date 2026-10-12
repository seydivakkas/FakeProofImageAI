# P1-v0.5: gerçek fotoğraf deney protokolü ve kanıt sınırları

## Neler yeni?

- G03b: bölge poligonu ile `floor` / `facade` / `wall` / `unknown` girişi; görüntü genelinden algılanmış çizgilerin ilgili bölgeye filtrelenmesi; dörtgen şekil/tekstür adayları; tekrar grupları; açıklamalı PNG ve JSON.
- G04-pair: iki fotoğraftan SIFT eşleştirme, mekânsal eşsizlik filtresi, öğrenmeden ayrı tutulan eşleşmelerle homografi testleri; hatalı eşleşmeler ile geometrik uyumsuzluğun ayrılması.
- G02: özgün York Urban `cameraParameters.mat` ve *bağımsız insan etiketli* üç Manhattan doğru ailesinden güvenli G02 manifest üretme. Gerçek fotoğraf ve referans kalibrasyon bu oturumda sağlanmadığı için **HOLD**.

## G02 — gerçek bağımsız kamera verisi (HOLD)

Kaynak: https://www.elderlab.yorku.ca/resources/york-urban-line-segment-database-information/

1. Özgün `YorkUrbanDB` fotoğraflarını ve `cameraParameters.mat` dosyasını resmî kaynaktan indir. Bu dosyalar mevcut pakete **dahil değil**.
2. Özgün kamera referansı `focal`, `pixelSize` ve `pp` değerleriyle `K = [[focal/pixelSize,0,pp[0]],[0,focal/pixelSize,pp[1]],[0,0,1]]` şeklinde okunuyor. Görüntü çözünürlüğünün ve optik distorsiyon düzeltmesinin tutarlılığını kontrol et.
3. `orthogonal_groups` için üç ayrı fiziksel Manhattan doğru ailesini bağımsız görüntü incelemesiyle etiketle. **Bu grupları doğrulayacağın K matrisinden türetilmiş kaçış noktalarıyla seçme; bu veri sızıntısıdır.**
4. Yanındaki etiket JSON'una `group_label_provenance="human_independently_annotated"` ve her grupta en az altı `[x1,y1,x2,y2]` segmenti koy.
5. Aşağıdaki komutla fotoğrafın yanına manifest oluştur, ardından gerçek G02 doğrulama komutuyla bağımsız `K` hatasını, üç ayrı holdout çizgi grubunun hata değerlerini hesapla.

```powershell
python scripts/prepare_york_manifest.py --image data/external/YorkUrbanDB/P000/P000.jpg --camera-parameters data/external/YorkUrbanDB/cameraParameters.mat --labels data/annotations/P000_lines.json
python -m aiforensics validate-g02-batch --inputs data/external/YorkUrbanDB/P102/P000.g02_manifest.json --out outputs/york_validation
```

Yukarıdaki `P000` yalnızca klasör şeması örneğidir; indirilen özgün veri kümesindeki gerçek fotoğraf ID'sini kullan.

**G02 kabul ölçütleri:** Resmî orijinal fotoğraf SHA256; bağımsız K; en az iki gruptan fazla gerçek fotoğraf örneği (ilk raporda istatistiksel dağılımlar için daha fazla örnek gerekir); fiziksel etiket doğrulaması; kalibrasyondan ayrılmış çizgiler; önceden belirlenmiş FPR/ölçüm protokolü; gerçek kamera referansına dayalı focal/principal hata dağılımları. Mevcut durum: **gerçek çekim G02 ölçümü yok**.

## G03b — düzlem bölgesi ve mimari eleman tekrar analizi

Giriş poligonunun semantik etiketinin güvenilir olması için gerçekten bağımsız incelenmiş bir açıklama gereklidir. Sadece `human_verified` veya `independent_dataset_annotation` beyanı bulunması, kriptografik/bilimsel doğrulama sağlamaz. G03b yalnızca verilen sınıfları bölge analizi için kullanır; kendi başına zemin veya cephe sınıflandırıcısı eğitilmiş değildir.

```powershell
python -m aiforensics analyze-g03-regions --input data/architectural/scene_regions.json --out outputs/scene_regions
```

Dörtgen konturlar, yaklaşık en-boy oranı ve yerel desen eşleşmeleri üzerinden tekrar *adayları* üretir. Tek kareden 3B eşit aralık, duvar/zemin semantiği veya fotoğraf kökeni kesinleşmez. Gerçek zemin-cephe semantik IoU, pencere/kolon eşleşme precision/recall ve gerçek yanlış alarm oranı **henüz ölçülmedi**.

## G04 — gerçek içerik, kontrollü ikinci perspektif

İnternet gerekmeden gerçek çekim içeriği `skimage.data.rocket()` ile ikinci görüntüye **bilinen bilgisayar homografisi** uygulanarak sonuç üretilir. Bu yöntem gerçek fotoğrafın bir kamera ile yeniden çekildiği anlamına gelmez; *ground truth* yalnız uygulanan dijital dönüşümdür.

```powershell
python -m pip install -e ".[dev,benchmark]"
python scripts/real_photo_experiments.py
```

Kontrol testi olarak `skimage.data.stereo_motorcycle()` içindeki **iki ayrı gerçek kamera çekimi** kullanılır. Derinliği değişken ve düzlemsel olmayan bu sahnede tek homografi tüm fotoğrafı açıklayamaz. Bu test, bağımsız düzlem GT içermez; algoritmanın eşleşme aykırılarını fizik ihlali sanmaması için bir stres testidir.

G04-pair ayrıca iki gerçek fotoğrafla `validate-g04-pair` komutunu destekler; bağımsız düzlem etiketi veya gerçek homografi bulunmadan sadece görünüş geometrisi tanımlayıcıları sağlar. Çok az sayıdaki hatalı SIFT eşleşmesi ortalama hatayı yükseltebilir. Bu nedenle tüm eşleşmelerin RMSE'si, median ve %3 piksel içindeki oran ayrı sunulur; aykırı eşleşmeler fizik yasası ihlali sayılmaz.

## Karar / sonraki iş

- P1 G01–G04 sentetik test: **PASS**.
- G03 gerçek içerikli (tuğla/fırlatma alanı) algoritma testi: **MEASURED, GT yok**.
- G04 gerçek içerikli kontrollü dönüştürme: **MEASURED, ikinci çekim değil**.
- G02 bağımsız gerçek kamera `K`: **HOLD / NOT_MEASURED**.
- G03 semantik yer doğruluğu ve mimari eleman eşleme precision/recall: **HOLD / NOT_MEASURED**.
- P2 fiziksel aydınlatma ve gölge: **henüz başlanmadı**. P1 saha kabulü sonrasında ilk iş P2-G01 gölge doğrusallığı ve ışık kaynağı kestirimi.
