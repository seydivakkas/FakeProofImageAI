# P7-S01 — RAW sensör gürültüsü: Poisson + Gaussian, kazanç, karanlık akım ve SNR

**Sürüm:** v0.24.0 · **Durum:** Matematiksel çekirdek ve kontrollü sentetik entegrasyon · **Gerçek kamera kabulü:** En son.

## 1. Ölçüm sözleşmesi

Bu modül JPEG veya PNG görüntüye bakarak bir görüntünün yapay zekâ kökenli olup olmadığını tahmin etmez. Gerekli veri, aynı fiziksel sensör, sabit kazanç ve sıcaklık ile, kararlı **RAW doğrusal ADU** alanında bağımsız karanlık/düz-alan pozlamalarının **zamansal** ortalama/varyans ölçümleridir. Flat-field için sensöre ulaşan ışığın oluşturduğu **ortalama fotoelektron sayısı** ayrıca bağımsız kalibre edilmeli veya kontrollü sentetik gerçek olarak verilmelidir. Bir JPEG'in görünür parlaklığını fotoelektron sayısı kabul etmek yasaktır.

**Kaynaklar:** [EMVA 1288 Release 4.0 Linear](https://www.emva.org/standards-technology/emva-1288/emva-standard-1288-downloads-2/) sensör ortalama–varyans ve photon transfer yaklaşımı; [Hamamatsu CCD Noise and SNR](https://hamamatsu.magnet.fsu.edu/articles/ccdsnr.html) Poisson shot/dark/read-noise kaynakları.

## 2. Fiziksel görüntü oluşumu

Her pikselde:

- `P ~ Poisson(s)`: fotoelektron (shot noise), `s`: beklenen ışık kökenli elektron sayısı.
- `D ~ Poisson(d*t)`: termal karanlık elektronları; `d` [e⁻ / piksel / saniye], `t` [s].
- `R ~ Normal(0, sigma_r²)`: okuma gürültüsü, [e⁻ RMS].
- Elektron birikimi: `Q = min(P + D, full_well_e)`.
- ADC kodu: `Y = clip(round(black_ADU + (Q + R)/g), 0, ADC_max)`, `g` [e⁻ / ADU].

`g` e⁻/ADU cinsinden **conversion gain** değeridir; bunun tersi ADU/e⁻ kullanılıyorsa açıkça çevrilmelidir.

### Doygunluk olmayan rejim için momentler

\[
\mu_Y=b+\frac{s+dt}{g},\qquad
\operatorname{Var}(Y)\simeq\frac{s+dt+\sigma_r^2}{g^2}+\frac1{12}.
\]

`1/12` ADU², ADC kuantalamasının yaklaşık uniform/dithered hata modelidir. Çok düşük okuma gürültüsü, düşük etkin bit derinliği, clipping veya korelasyon durumunda **geçersiz olabilir**; yazılım okunabilir kuantalama rejimi dışında fizik kararı üretmez.

SNR (elektron düzlemi; karanlık akım gürültüye dahildir, sinyale dahil değildir):

\[
\boxed{\mathrm{SNR}_{e}=\frac{s}{\sqrt{s+dt+\sigma_r^2}}}.
\]

Yaklaşık ADC SNR hesabında pay `s/g`, paydan `sqrt(Var(Y))` alınır. Pozlama/gain başına kararlı sıcaklık koşulu zorunlu kabul edilir; sensör gürültüsü ve sıcaklık arasında evrensel sabit katsayı uydurulmaz.

## 3. Eğitim / holdout ve belirsizlik

- **known_parameters:** `gain_e_per_adu`, `read_noise_e`, `dark_current_e_per_s`, `black_level_adu`, `full_well_e`, `adc_max_adu` bağımsız sensör kalibrasyonu/sentetik gerçek olarak verilir.
- **fit_train_parameters:** sensörün ilk üç parametresi sadece `role=train` anotasyonlarından, bilinmiş siyah seviye/kapasite/ADC aralığıyla birlikte robust nonlinear least-squares ile kestirilir. Eğitimde poz sıfır *dark*, değişen dark süreleri ve en az üç ayrı aydınlatma düzeyi gerekli; rank/koşul hataları reddedilir. `role=holdout` hiçbir zaman uyarlamada kullanılmaz.
- Test edilen iki momentin ölçüm standart hatası büyük örneklem yaklaşımlarıyla tahmin edilir. Ortalama için `sqrt(v/n)`; varyans için Poisson-Gaussian dördüncü kümülanına dayalı örnek varyansı standart hatası kullanılır. Fit edilmiş parametreler için train Jacobian kovaryansı ilave edilir. Bu yaklaşım yaklaşık ve koşulludur, kalibre edilmiş anlamlılık düzeyi veya p-değeri **değildir**.
- Varsayılan `max(|z_mean|, |z_variance|) <= 2.5`: `CONSISTENT`; `>= 5.0`: `INCONSISTENT_UNDER_ASSUMPTIONS`; aradaki aralık `INDETERMINATE`.
- Raporlanabilir karar için tanımlanmış `RAW`/kararlı sensör koşulları, bağımsız örnek ve kalibrasyon provenansı, unclipped ADC, geçerli kuantalama ve yeterli örnek sayısı gerekli. Kalibrasyon veya ışınım eksikse `INDETERMINATE`.

Z-skorlarının dağılımları tamamen normal değildir; çoklu testler arası bağımlılık ve yanlış alarm kalibrasyonu **P8'de** ele alınacaktır.

## 4. JSON giriş örneği

Tam çalışır örnek: `outputs/p7_s01_demo/p7_s01_fixture.json` (`python -m aiforensics demo-sensor-noise` komutuyla üretilir).

```json
{
  "calibration_mode": "known_parameters",
  "input_domain": "linear_raw_adu",
  "sensor_provenance": "synthetic_ground_truth",
  "stable_temperature": true,
  "temporally_independent": true,
  "uniform_flat_field": true,
  "fixed_gain_mode": true,
  "prnu_or_fpn_controlled": true,
  "sensor": {
    "gain_e_per_adu": 2.0,
    "read_noise_e": 4.5,
    "dark_current_e_per_s": 1.65,
    "black_level_adu": 128.0,
    "full_well_e": 25000.0,
    "adc_max_adu": 16383
  },
  "measurements": [
    {
      "id": "holdout_01",
      "role": "holdout",
      "kind": "flat",
      "expected_photoelectrons": 800.0,
      "exposure_s": 1.0,
      "photoelectron_provenance": "synthetic_ground_truth",
      "sample_provenance": "synthetic_ground_truth",
      "observed_mean_adu": 528.85,
      "observed_variance_adu2": 206.0,
      "n_samples": 4096,
      "saturation_fraction": 0.0,
      "zero_code_fraction": 0.0
    }
  ]
}
```

Bu yalnızca **alan şeması örneği**dir; tek satırla varsayılan `min_holdout=6` eşiği karşılanmaz. Sayısal değerler ölçüm sonucu olarak sunulmaz. Tam fixture otomatik üretilir.

## 5. CLI

```powershell
python -m aiforensics demo-sensor-noise --out outputs/p7_s01_demo
python -m aiforensics demo-sensor-noise --fit-parameters --out outputs/p7_s01_fit
python -m aiforensics analyze-sensor-noise --input outputs/p7_s01_demo/p7_s01_fixture.json --out outputs/p7_s01_check
python scripts/p7_sensor_benchmark.py --trials 80 --out outputs/p7_s01_benchmark.json
```

`p7_s01_report.json` içeriğinde ayrı gözlem durumları, gözlenen/beklenen ADU ortalama-varyansı, yaklaşık z-skorları, kalibrasyon tanısı ve fiziksel varsayımlar yer alır.

### İsteğe bağlı RAW `.npy` yığınından zamansal özet

`stack.npy` boyutu `[T, H, W]`, kodları doğrusal tamsayı ADU ve sabit pozlama/gain olmalı. Aynı pikselin `T` karedeki örnek varyansları ortalanır: böylece sabit piksel deseni sırf **uzamsal** varyansı büyüttüğü için zamansal read noise zannedilmez. Ancak satır gürültüsü, piksel korelasyonları ve geçerli bağımsız örnek sayısı otomatik ölçülmez.

```powershell
python -m aiforensics summarize-raw-stack --npy frames.npy --roi 10 20 120 140 --out outputs/temporal_stats.json
```

Bu komut fotoelektron flux kalibrasyonu **çıkarmaz** ve AI kökeni sonucu **üretmez**.

## 6. Modelin kapsamadıkları

- P7-S02: **PRNU/DSNU**, sensör parmak izi, sıcak piksel, banding/korelasyonlu gürültü ve kalibrasyonlu tekil sensör atfı ayrı modüller olacaktır.
- Bayer CFA/kanallar, demosaicing, ISO gain modları, renk matrisi, gamma, JPEG, sıkıştırma, denoiser ve yeniden ölçekleme bu fizik modelinin dışındadır.
- Poisson yaklaşık bağımsız fotoelektronlar ve Gaussian read noise; uzun pozlama hot-pixel/RTS noise, EMCCD excess noise, nonlinear ADC, CFA cross-talk ve sensörün karanlık akım sıcaklık dinamiği kapsam dışıdır.
- Simülasyon ve kestirim aynı model ailesini paylaşır; testlerde gerçek kamera doğruluğu, PRNU köken atfı, sahte fotoğraf sınıflandırması veya yapay zekâ köken tespit başarımı ölçülmez.

## 7. Geliştirme sırası

**P7-S01 matematiksel çekirdek/sentetik entegrasyon → P7-S02 PRNU/DSNU ve sensör izleri → P8 ölçüm bağımlılığı, hipotez testi ve çok-modüllü kanıt birleşimi → tüm sistem entegrasyonu → bağımsız gerçek fotoğraf ve Windows kabulü en son.**
