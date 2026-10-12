# P3-R02 — Saydam Yüzeylerde Snell Kırılması ve Görünür Yer Değiştirme

## 1. Kapsam / kanıt standardı

Geliştirilen `aiforensics.refraction_geometry` modülü **bağımsız olarak bilinen** kamera, düzlemsel sınır, kırılma indisleri ve nesne 3B koordinatları varsayımında, gözlenen piksellerin beklenen kırılmalı ışın yolu ile uyumunu ölçer. Otomatik su/cam yüzeyi tespiti veya AI üretimi sınıflandırması **yapmaz**. Sentezlenmiş geometrik testler saha verisi değildir; gerçek fotoğraf validasyonu son kabulde yapılacaktır.

### Ortam modeli

- `single_interface`: kamera tarafındaki `n_camera` ve nesnenin bulunduğu `n_layer` ortamı, tek sonsuz/dışarıdan poligonla sınırlandırılmış **düz** arayüz.
- `parallel_slab`: kamera tarafı `n_camera`, kalınlığı `thickness_world` olan levha `n_layer` ve nesne tarafı `n_beyond`. İki yüzey kusursuz paralel.
- İndisler sıfırdan büyük, sonlu ve bilinen sayılardır; **bu modül onları piksellerden öğrenmez**. Dalga boyu / dispersiyon hesaba katılmaz.
- `R_world_to_camera` ve `t_world_to_camera` aynı birimde tanımlanan gerçek dünyaya göre kamerayı belirler; lens distorsiyonu önceden düzeltilmiş olmalı.
- `normal_toward_camera_world` normalinin **kamera tarafındaki ortama bakması gerekir**. Normale göre signed distance kamera için pozitiftir. Nesne tek sınırda karşı tarafta, cam levhada arka yüzeyin ötesinde olmalıdır.

## 2. Snell fizik denklemi

Bir dalga/ışın iki saydam ortam arasında düz bir arayüzde kırıldığında

\[
n_1\sin\theta_1=n_2\sin\theta_2
\]

Burada açılar yüzeyin normaline göre ölçülür. Ortama giren birim yönü `d`, gelen ortama bakan birim normal `n`, `eta=n1/n2`, `c=-n·d` olmak üzere

\[
k=1-\eta^2(1-c^2),\qquad
\mathbf{d}_t=\eta\mathbf{d}+(\eta c-\sqrt{k})\mathbf n.
\]

`k<0` ise **toplam iç yansıma (TIR)** vardır: geçirgen tarafa iletilen geometrik ışın bu modelde yoktur. Yazılım böyle bir ışın icat etmez. Bu vektörel yardımcı işlem önceki `mirror_geometry.refract_direction()` fonksiyonu üzerinden tekrar kullanılır. TIR **yansıma fiziği** açısından anlamlı olsa da cam/su **iletilen görüntü** denetiminde sonuç `INDETERMINATE` olur.

## 3. 3B noktadan gözlenecek piksele ışın yolunu çözmek

Sınır normaline paralel uzaklıklar `h_i>0`, kırılma indisleri `n_i>0` ve kamera ile hedef 3B noktanın yüzeye paralel izdüşümleri arasındaki uzaklık `rho` olsun. Paralel katmanlarda teğetsel optik momentum

\[
q=n_i\sin\theta_i
\]

korunur. Her ortamdaki teğetsel ilerleme

\[
\Delta_i=\frac{h_i q}{\sqrt{n_i^2-q^2}}
\]

olduğu için sayısal çözüm şu **tek boyutlu, monoton** eşitliği kullanır:

\[
\boxed{\rho=\sum_{i=1}^{m}\frac{h_i q}{\sqrt{n_i^2-q^2}},\quad
0\le q<\min_i n_i.}
\]

`scipy.optimize.brentq` ile `q` çözülür. Ardından katmanların ön ve arka kesişim noktaları, kameradan çıkan ışın ve bu ışının görüntü koordinatı hesaplanır:

\[
\mathbf u_{\rm expected}=\pi\!\big(K,R,t;\ C+\hat{(M_1-C)}\big).
\]

**Kırılmasız referans pikseli** ayrıca `π(K,R,t; X_object)` olarak hesaplanır. İkisi arasındaki iki boyutlu fark `modeled_pixel_shift_xy`, Öklid büyüklüğü ise `modeled_pixel_shift_norm_px` alanındadır. Bunlar **beklenen model kaymasıdır**, bağımsız fotoğraf ölçümü değildir. Düz yüzey ve sabit indis olmayan sahnelere genelleştirilmez.

### Su yüzeyi

Örnek (standart değer **değil**, sentetik kurulum): kamera tarafı `n_camera=1.0`, su `n_layer=1.333` ve `single_interface`. Belirli bir 3B nokta, suya giren kamera ışınının kırılmasını sağlayacak şekilde görüntüde kayar.

### Cam levha

Örnek: `n_camera=1.0`, `n_layer=1.5`, `n_beyond=1.0`, `thickness_world=0.65`. Paralel yüzeyli cam levhadan çıkan ışın geliş ışınına paralel olabilir; **yine de yanal kayma sıfır değildir**. Sadece açısal yön test eden bir yöntem bu etkiyi kaçırır. Cam yüzeylerin paralel değilse bu model geçerli değildir.

## 4. Gözlem ve geometrik karar

Her doğrulanmış nesne–piksel eşleşmesinde

\[
r_{px}=\|u_{observed}-u_{expected}\|_2
\]

hesaplanır. Eşik varsayılan `3.0 px` ve deneme amaçlıdır; saha yanlış alarm düzeyine göre **kalibre edilmedi**.

- `CONSISTENT_UNDER_ASSUMPTIONS`: eşleşme modeli piksel toleransında karşılar.
- `INCONSISTENT_UNDER_ASSUMPTIONS`: geçerli eşleşme model dışındadır; bu **AI kaynak kanıtı değildir**.
- `INDETERMINATE`: yüzeye ulaşmama, hatalı nesne tarafı, görüş alanı dışında kalma, fiziksel levha poligonu dışında kesişme, TIR ya da yetersiz bağımsız eşleşme.

`traced_world_error` gözlenen piksel ışınının fiziksel arayüzlerden geri izlenmesiyle aynı eşleşmeden hesaplanır. **`r_px` ile bağımsız ikinci istatistiksel kanıt değildir**, ayrı çarpılarak güven oluşturulmaz. `snell_law_numerical_residual` çözülen ışınların Snell yasasını ne kadar doğru uyguladığının sayısal kontrolüdür; gözlemin ikinci ölçümü değildir.

## 5. Giriş manifesti

`demo-refraction` komutunun ürettiği `p3_r02_fixture.json` tam, yeniden kullanılabilir giriş örneğidir. Özet:

```json
{
  "image_shape_hw": [720, 1280],
  "camera": {
    "K": [[860,0,640],[0,860,360],[0,0,1]],
    "R_world_to_camera": [[1,0,0],[0,1,0],[0,0,1]],
    "t_world_to_camera": [0,0,0]
  },
  "interface": {
    "model": "single_interface",
    "point_world": [0,0,3],
    "normal_toward_camera_world": [0,0,-1],
    "n_camera": 1.0,
    "n_layer": 1.333
  },
  "correspondences": [
    {"id": "landmark1", "object_world_xyz": [1.0, 0.3, 7.0], "observed_xy": [750.0, 396.0], "confidence": 1.0}
  ]
}
```

**Bu tek örnekteki `observed_xy` bir doğrulanmış fiziksel ölçüm değildir.** İleri izleme sonucu ve gerçek uyumu otomatik üretilmiş demo dosyasında incelenmelidir.

Paralel levha için `model`=`parallel_slab` yapıp `thickness_world` pozitif ve `n_beyond` ekle. İsteğe bağlı `polygon_world` ilk düzlemdeki açıklığı tanımlar; ikinci yüzeyde aynen normal doğrultusunda kaydırılmış poligon kullanılır.

## 6. Komutlar (PowerShell)

```powershell
python -m aiforensics demo-refraction --out outputs/p3_r02_water
python -m aiforensics demo-refraction --model parallel_slab --out outputs/p3_r02_glass
python -m aiforensics analyze-refraction --input outputs/p3_r02_water/p3_r02_fixture.json --image outputs/p3_r02_water/p3_r02_fixture.png --out outputs/p3_r02_analysis
python scripts/p3_refraction_benchmark.py --trials 80 --out outputs/p3_r02_benchmark.json
pytest -q
```

Çıktı: `p3_r02_report.json`, isteğe bağlı `p3_r02_overlay.png`, kontrollü benchmark `p3_r02_benchmark.json`. Analiz raporu kaynak manifestin SHA-256 kimliğini de içerir. Hesaplar piksel koordinatlarına uygulanır; görüntü üzerindeki sarı/mavi işaretler modelin beklediği yeri, yeşil/kırmızı gözlenen işaretlerin koşullu uyumunu gösterir.

## 7. Negatif kontroller ve bilinen eksikler

- TIR: cam→hava kritik açı üstü ışında iletilen ışın bulunmuyor.
- Eşit indisli ortamlar: doğrultu ve konumda **kırılma kayması sıfır**.
- Döndürülmüş dünya koordinatları: matematiksel çözüm değişmez.
- Nesne yanlış tarafta / normal ters / geçersiz indislere: fail-closed davranış.
- Kısıtlı arayüz açıklığı: geçersiz kesişimler `INDETERMINATE`.
- Bozulmuş eşleşmeler: açıkça uyumsuz olarak raporlanır.

**Modellenmeyenler:** prizma ve kama camları, eğri/oynak su yüzeyleri, çok katlı genel üçgen ağlar, Fresnel yansımaları, çift görüntü, gerçek lens distorsiyonu, kromatik dispersiyon, emilim, bulanıklık, doğal ışık yayılımı, belirsizlik kalibrasyonu, otomatik segmentasyon / landmark discovery.

**Nihai kabul:** bağımsız gerçek kamera ölçümleri, düzlem normalinin/kalınlığın/indislerin gerçek ölçümü, anotasyon kalitesi, sapma toleransı/yanlış alarm dağılımı ve Windows cihaz testi proje sonunda yapılacak.

## 8. Opsiyonel kırılma indisi kestirimi — eğitim ve holdout ayrı

Bu modül yalnızca **tek arayüz** için, dışarıdan doğru olarak sağlanmış `K/R/t`, düzlem normal/konumu, kamera tarafındaki `n_camera`, nesne 3B noktası ve gözlenen piksel üzerinden `n_layer` kestirir. **Paralel levha için bu yordam kullanılmaz.**

Kamera merkezinden gözlenen piksele giden ışının düzleme kesişimi `M` olsun. Kamera–M gelen rayının ve M–P çıkan rayının düzlem teğetine göre büyüklükleri `sin θ_i`, `sin θ_t` ise:

\[
\boxed{\hat n_{layer}=n_{camera}\frac{\sin\theta_i}{\sin\theta_t}}
\]

Ancak ışınların teğetsel azimutları farklıysa, kırılma düzlemi varsayımı sağlanmaz. Geliş açısı normale fazla yakınsa oran kararsız kalır; **ölçümden kaçınırız**. Hatalı eğitim noktalarının sınırlı etkisi için log indislerde medyan/MAD kullanılır. Aynı noktaların fit performansını başarılı kanıt olarak yeniden saymayız.

Manifestte zorunlu disjoint alanlar:

```json
"index_fit": {
  "train_ids": ["point_000", "point_001", "point_002", "point_003"],
  "holdout_ids": ["point_004", "point_005", "point_006", "point_007"]
}
```

```powershell
python -m aiforensics demo-refraction --out outputs/p3_r02_water
python -m aiforensics estimate-refraction-index --input outputs/p3_r02_water/p3_r02_fixture.json --out outputs/p3_r02_index
```

`demo-refraction`, `single_interface` için bölünmüş eğitim/holdout ID'lerini kendisi üretir; `n_layer` manifestte bulunsa bile kestirim sırasında **fit için kullanılmaz**. `estimated_n_layer` yalnız eğitim ID'lerinden elde edilir; rapordaki koşullu `state` **yalnız holdout noktalarının** reprojeksiyon değerlendirmesinden gelir. Bu bağımsız veri kümesi değildir; aynı sentetik kamera/sahne üreticisindeki, ayrı noktalardan oluşan kontrollü holdout'tur. Gerçek görüntü için indeks doğrulaması yapılmadı.

İndis kestirimi için 3B nesne ve arayüz geometrisinin gerçekten **bağımsız** bilinmesi gerekir. Bilinmeyen geometriyi ve indisi aynı eşleşmelerden eş zamanlı fit ederek aynı örneklerde doğrulamak kabul edilemez.
