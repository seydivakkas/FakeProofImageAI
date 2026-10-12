# P7-S02 — PRNU, DSNU ve kontrollü RAW sensör parmak izi

**Sürüm:** v0.25.0 · **Geliştirme aşaması:** sentetik matematiksel/entegrasyon doğrulaması · **Gerçek sensör eşleşmesi ve cihaz kabulü:** en son aşamada.

## 1. Fiziksel ölçüm sözleşmesi

P7-S01 zamansal sensör gürültüsü (Poisson shot, Gaussian read, karanlık akım, kazanç/ADC) üzerine, **zaman içinde sabit kalan piksel desenleri** eklenmiştir. Girdi JPEG, demosaiced RGB, kırpılmış/hizası değiştirilmiş fotoğraf veya tek kare değildir. Referans için ayrı **karanlık** ve **tekdüze aydınlatılmış düz-alan** RAW kare yığınları; sorgu içinse **bağımsız** karanlık/düz-alan RAW yığınları gerekir. Tüm karelerde kamera modu, kazanç, pozlama, sıcaklık, native piksel hizası ve CFA kanal yapısı uyumlu olmalıdır.

Kullanılan fiziksel beklenti (ADU):

\[
\mathbb{E}[D_p] = b + \frac{d_p}{g}, \qquad
\mathbb{E}[F_p] = b + \frac{d_p + s(1+k_p)}{g}
\]

- `b`: ADC siyah seviyesi (ADU), `g`: elektron/ADU dönüşümü (P7-S01 ile aynı birim).
- `d_p`: pikselin verilen pozlamadaki beklenen karanlık elektron yükü.
- `s`: uzaysal tekdüze aydınlatmanın ortalama fotoelektron katkısı.
- `k_p`: PRNU duyarlılık sapması, boyutsuz (sıfır uzaysal ortalamalı).
- `d_p - mean(d_p)`: DSNU sabit karanlık ofset deseni (elektron).

Her pikselle ilgili hesaplar `T` kare boyunca **önce zamansal ortalama** alınarak yapılır. Böylece kareler arası rastgele dalgalanma ile pikselden piksele sabit desen birbirine karıştırılmaz:

\[
\widehat{\mathrm{DSNU}}_p = g(\overline D_p-\langle\overline D\rangle_{pixels})
\]

\[
\widehat{\mathrm{PRNU}}_p = \frac{\overline F_p-\overline D_p}{\langle\overline F-\overline D\rangle_{pixels}}-1.
\]

`DSNU` değerinin mutlak düzeyi kamera siyah seviyesi ve pozlama/sıcaklık bilinmeden başka bir pozlamayla karşılaştırılamaz. PRNU düzeltilmiş fotoelektron cevabı, aydınlatmanın uzaysal tekdüzeliği dışarıdan doğrulanmadıysa gerçek sensör kazancı olarak yorumlanamaz.

## 2. Parmak izi karşılaştırması

İki **ayrı veri kümesi** üretilir: kalibrasyonda kullanılan `reference.npz`, kimlik gözlemi için `same_sensor.npz` veya `wrong_sensor.npz`. Sorgu verisi referans haritasının öğrenilmesinde kullanılmaz. Aynı ham karanlık+düz-alan veri yığınlarının yeniden kullanılmasına SHA-256 tabanlı sızıntı kontrolü uygulanır.

PRNU ve DSNU haritalarında aydınlatma/karanlık düşük frekanslı gradyanların etkisini azaltmak için `sigma=3 native pixel` Gaussian high-pass işlenir. Her harita için Pearson korelasyonu ayrı raporlanır:

\[
\rho(X,Y)= \frac{\langle(X-\bar X)(Y-\bar Y)\rangle}
{\sqrt{\langle(X-\bar X)^2\rangle\langle(Y-\bar Y)^2\rangle}}
\]

Bu yüksek-geçiren işlem gradyanları **tümüyle ortadan kaldırdığını ispatlamaz**. Kamera modelleri arasında ortak işlem artefaktları, satır/sütun desenleri, sıcaklık kayması, sensörün CFA yapısı ve kayıt hattı sahte benzerlik oluşturabilir. Gerçek kamera için bağımsız cihazlardan oluşturulmuş bir referans/impostor havuzu, yanlış eşleşme kalibrasyonu, uygun PCE, hizalama araması ve doğrulama protokolü henüz uygulanmadı.

**Önemli:** `CONSISTENT_UNDER_SYNTHETIC_ASSUMPTIONS` ve `INCONSISTENT_UNDER_SYNTHETIC_ASSUMPTIONS` yalnızca sentetik bağımsız-piksel modeli ve önceden seçilmiş keşifsel korelasyon eşikleri altında kullanılabilir. Diğer girdilerde korelasyon sayıları ölçülebilir ancak kimlik sonucu `INDETERMINATE` olarak kalır. Kullanıcının JSON'da “synthetic_ground_truth” yazması bağımsız köken kanıtı sayılmaz: `analyze-sensor-fingerprint` CLI **her zaman yalnız betimleyici korelasyon** döndürür; sentetik kararı yalnız dahili kontrollü `demo`/`benchmark` üreticileri etkinleştirebilir.

## 3. Yeniden üretilebilir kullanım

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest -q
python -m aiforensics demo-sensor-fingerprint --out outputs/p7_s02_demo
python -m aiforensics analyze-sensor-fingerprint --input outputs/p7_s02_demo/p7_s02_fixture.json --out outputs/p7_s02_analysis
python scripts/p7_fingerprint_benchmark.py --trials 80
python scripts/p7_fingerprint_negative_controls.py
```

NPZ dosyalarının her biri NumPy `allow_pickle=False` ile açılan `dark` ve `flat` dizilerini içerir. Şekil `[T,H,W]`; yalnızca sensörün yerel hizalı sayısal RAW ADU değerleri kabul edilir. `T>=8`, en az 256 piksel, yeterli pozitif düz-alan sinyali ve düşük clipping istenir. Yazılım kareleri otomatik hizalamaz veya JPEG'den sensör deseni çıkarmaz.

**JSON manifest örneği** `outputs/p7_s02_demo/p7_s02_fixture.json` içindedir. Manifestte referans ve sorgu NPZ adları, P7-S01 sensör parametreleri, RAW veri alanı, bağımsız ölçüm ile kamera/aydınlatma sözleşmesi ve veri kökeni iddiası vardır.

## 4. Hata modları ve iddia sınırı

- Doygunluk, sıfır kod, yetersiz aydınlatma veya frame sayısı → geçersiz/gerekçeli `INDETERMINATE`.
- Farklı sensör çözünürlüğü, doğrudan resize/crop veya hizalama eksikliği → `INDETERMINATE`.
- Referansla aynı RAW karelerin sorguya verilmesi → sızıntı olarak reddedilir.
- Işık, sıcaklık, sabit kazanç veya ham veri kökeni eksikliği → **kesin sensör sınıfı verilmez**.
- Yüksek korelasyon, yeniden kodlanmış görüntülerin özgünlüğünün kanıtı değildir. Düşük korelasyon da görüntünün AI üretimi olduğunu göstermez.

## 5. Kaynaklar / kavramsal dayanak

- EMVA 1288 Release 4.0 (Linear/General), sensörün zamanla değişen gürültüsüyle uzaysal DSNU/PRNU tanımlarını ayırır: <https://www.emva.org/standards-technology/emva-1288/>
- Lukáš, Fridrich, Goljan (2006), “Digital Camera Identification from Sensor Pattern Noise”, IEEE T-IFS, DOI: `10.1109/TIFS.2006.873602`. Bu paket çalışmanın gerçek fotoğraf denoising/PCE ve gerçek cihaz kabul başarımını **uyguladığını iddia etmez**.

### Sonraki iş

P8 birleşik istatistiksel kanıt motoru ve bütün modül entegrasyonu; **bundan sonra** bağımsız gerçek sensör ölçümleri, false-match/false-nonmatch kalibrasyonu ve gerçek Windows kabulü.
