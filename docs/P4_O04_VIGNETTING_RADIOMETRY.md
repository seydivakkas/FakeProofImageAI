# P4-O04 — Radyometrik Vinyet, cos⁴ Yasası, Düz-Alan Kalibrasyonu

**Sürüm:** 0.17.0 · **Durum:** Kontrollü/sentetik kod doğrulaması · **Gerçek fotoğraf kabulü:** En son

## 1. Amaç ve ölçülebilir sözleşme

P4-O04, **aynı pozlama ve sabit aydınlatılmış, radyometrik olarak doğrusal, siyah seviyesi çıkartılmış bir düz-alan hedefi** için görüntü düzlemindeki göreli aydınlatma düşüşünü inceleyen koşullu fizik motorudur. Ham bir JPEG'deki merkez/kenar parlaklık farkından gerçek optik vinyeti veya görüntünün AI tarafından üretilip üretilmediğini iddia **etmez**.

Girdi:

- Önceden kalibre edilmiş `K` (P4-O03); `image_size_wh` ve P4-O01 uygulandıktan sonra geçerli **undistorted** nokta koordinatları.
- Bağımsız düz-alan referansı (`reference_linear`) ve her bölgede `observed_linear`, `sigma_linear`.
- Tekrarlanmayan benzersiz `train` / `holdout` bölgeleri ve kaynak kanıt etiketleri.
- Bilinen/koşullu optik model (`cos4_only`, `fit_radial` ya da `fit_radial_and_center`).

Çıktı: cos⁴ referansı, radyal artık ve optik gölgeleme merkez kayması, eğitim kalitesi, eğitimden ayrı bölgelerde öngörülen ışınım ve standartlaştırılmış artık hata, `CONSISTENT` / `INCONSISTENT_UNDER_ASSUMPTIONS` / `INDETERMINATE`, açıklama ve `NO_AI_ORIGIN_CONCLUSION`.

## 2. Model

Kamera düzlemi koordinatları

\[
\tilde y=(v-c_y)/f_y,\qquad
\tilde x=(u-c_x-s\tilde y)/f_x
\]

ile tanımlanır. Burada `s=K[0,1]` piksel skew parametresidir. İdeal doğal aydınlatma düşüşü:

\[
\theta=\operatorname{atan}\sqrt{\tilde x^2+\tilde y^2},\qquad
G_{\mathrm{cos4}}=(1+\tilde x^2+\tilde y^2)^{-2}.
\]

Optik gölgelemenin, baş optik eksenden kaymış merkezi `c=(d_x,d_y)` olabilir. Merkezden ölçülen `r²=(x-d_x)²+(y-d_y)²`, `r₀²=d_x²+d_y²`. Ek geometrik/optik merkezî düşüşü koşullu olarak

\[
G_{\mathrm{rad}}=\exp\{a_2(r^2-r_0^2)+a_4(r^4-r_0^4)\}
\]

ile temsil ediyoruz. Böylece kamera ana noktasındaki **göreli kazanç tam olarak 1** olur.

\[
\boxed{\hat I(u,v)=I_{\mathrm{ref}}(u,v)\cdot e^b\cdot G_{\mathrm{cos4}}(u,v)\cdot G_{\mathrm{rad}}(u,v)}
\]

`b` sabit ışınım/pozlama kazancını (train üzerinde) taşır. Radyal log düzeltme **kanuni tek gerçek lens modeli** değil, kullanılabilecek bir fenomenolojik yakınsamadır. Ayrı lens-sensör sistemleri farklı roll-off gösterebilir; cos⁴ geometrik limit mutlaka görülmez. Sıkışma/filtre mekanik kesilmesi, diyafram kaynaklı bokeh, çevresel renk kayması, sensör mikro-mercekleri ve ISP yeniden aydınlatması kapsam dışıdır.

## 3. Fit/bağımsız doğrulama

- `cos4_only`: Train üzerinde yalnız `b` kestirimi. Radyal artık sıfır.
- `fit_radial`: Train üzerinde `b,a2,a4` sağlam en küçük kareler (soft-L1) ile kestirilir; optik gölgeleme merkezi ana noktaya sabittir.
- `fit_radial_and_center`: `b,a2,a4,d_x,d_y` eğitim bölgelerinden kestirilir; her iki eksende yeterli kapsama gerekir. Merkez shift tek görüntüden kendiliğinden gözlemlenebilir değildir: bağımsız uniform düz-alan varsayımına bağlıdır.
- Geometrik çeşitlilik, Jacobian sırası, sınır değerler ve eğitim/test ayrımı aranır. Yetersiz gözlemlenebilirlik `INDETERMINATE`.
- Holdout için hata: `r_i = I_observed - I_expected`, birleşik tahmini standart sapma `σ_total = √(σ_measure² + σ_fit²)`; `σ_fit` eğitimdeki lokal Jacobian kovaryansının **asimptotik koşullu** yaklaşımıdır; kesin kalibre edilmiş güven aralığı değildir.
- Varsayılan karar eşiği `|r_i/σ_total| > 3.5` ve en az 12 holdout. Bağımsız bölgeler ile piksel korelasyonları bu basit sigma modelini bozabilir. Çoklu karşılaştırmalar için FPR otomatik kalibre edilmemiştir.
- Göreli kazancı düzeltirken en fazla 8× amplifikasyona izin verilir; aşırı düşük kenar ışınımı güvenli fiziksel geri kazanım olarak kabul edilmez.

## 4. Kritik sınırlar

1. Düz-alan sahnede gerçek ışınımın sabitliği bağımsız ölçülmelidir; yerel yüzey dokusu, yansıma ve çevresel aydınlatma tümünü bozabilir.
2. İşlenmiş JPEG/PNG, otomatik pozlama, tone-map, gamma, HDR, local contrast ve lens shading correction uygulandığında `observed_linear` değerinin ışınım karşılığı belirsizdir. **Raw + doğrusal kalibrasyon veya eşdeğer ölçüm** gerekir.
3. `K` ve nokta koordinatları aynı kırpma/ölçek sisteminde olmalı; Brown–Conrady görüntüde önce geometrik düzeltme ya da bağımsız eşleştirme gerekir.
4. Bilinen lensin ölçümüne karşı cos⁴ farkı tek başına fiziksel çelişki değildir. Lens görüntüsü fiziksel olarak doğru fakat model yetersiz olabilir.
5. Görüntü işleme ile vinyet giderilebilir veya yapay eklenebilir. Gözlenen fotoğraf parlaklığı ile fotoğraf kökeni arasında doğrudan mantıksal çıkarım yoktur.
6. Farklı renk kanalları, dalga boyları ve diyafram değerleri ayrı ayrı kalibre edilmelidir. Şu an tek bir lineer gri/kanal düz-alan manifesti analizi mevcuttur.
7. P4-O02 defocus, P4-O01 distorsiyon ve P4-O03 görüş alanı ile farklı fiziksel olaylardır; yalnız `K` ve geometrik domain birlikte kullanılır.

## 5. CLI — Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest -q

python -m aiforensics demo-vignetting --out outputs/p4_o04_demo
python -m aiforensics demo-vignetting --fit-center --out outputs/p4_o04_center_demo
python -m aiforensics analyze-vignetting --input outputs/p4_o04_demo/p4_o04_fixture.json --out outputs/p4_o04_check
python scripts/p4_vignetting_benchmark.py --trials 80
```

Kendi *radiometrically linear dark-corrected* `linear_image.npy` girdin ve birbirinden **çakışmayan** dikdörtgen bölgeleri, her bölgenin bağımsız `reference_linear` ve `sigma_linear` ölçümü ile:

```powershell
python -m aiforensics sample-vignetting --npy linear_image.npy --regions my_regions.json --out flat_field_manifest.json
python -m aiforensics analyze-vignetting --input flat_field_manifest.json --out outputs/my_flat_field
```

`sample-vignetting` anotasyonlardan ölçüm üretir ama gerçek düz-alan/kalibrasyon sertifikası vermez. Koşullar sağlanmamışsa `INDETERMINATE` yorumlanmalıdır.

## 6. Bilimsel referanslar

- Edmund Optics, *Relative Illumination, Roll-Off, and Vignetting*: https://www.edmundoptics.com/knowledge-center/application-notes/imaging/sensor-relative-illumination-roll-off-and-vignetting/
- Reiss, M., *Notes on the Cos⁴ Law of Illumination*, JOSA 38, 980–986 (1948), https://doi.org/10.1364/JOSA.38.000980
- OpenCV 4/5 kamera modeli: https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html

**Gerçek cihaz, RAW flat-field ve bağımsız optik ölçümler projenin son kabul aşamasında yapılacaktır.**
