# P8-E01 — Evidence Contract / Kanıt Sözleşmesi

## Durum
Geliştirilmiş matematiksel çekirdek; otomatik ve kontrollü sentetik testler mevcut. **Gerçek veriyle eşik kalibrasyonu, çoklu hipotez testi ve sahada yanlış alarm ölçümü henüz yoktur.**

## Kapsam
P1-G01…G04, P2-S01…S05, P3-R01…R03, P4-O01…O04, P5-D01…D03, P6-M01…M03, P7-S01…S02 olmak üzere 24 modül tanımlıdır. Her modülün mevcut raporundan *gözlemler ve açıklayıcı metrikler* kayıpsız ilişkilendirilebilir; ancak kalibre edilmemiş eski metriklere otomatik p-değeri atanmaz.

## Kanıt nesnesi
- `schema_version=p8.e01.v1`, `module_id`, `observation_id` ve `unit`.
- `measured`, `predicted` ve birimleri aynı olan bir **scalar holdout artığı**.
- `assumptions=[{name,status,source}]`: varsayımlar fiziksel kaynakla belgelenmiş olmalı.
- `provenance={source_id, calibration_id, split, independent_of_training, external_reference_verified}`: eğitim, kalibrasyon ve test ayrımı.
- `uncertainty={measurement_std,prediction_std,error_correlation}`: nokta tahmini değil, açık hata modeli.
- `test={null_distribution,alpha,pre_registered,distribution_independently_checked}`: kullanılan hipotez testinin kalibrasyon önkoşulları.
- Çıktı `standardized_effect`, `p_value_two_sided`, artık belirsizliği, 95% tanımlayıcı aralık, durum ve `NO_AI_ORIGIN_CONCLUSION`.

## İstatistiksel hipotez

\[
r = y_{observed}-y_{predicted}, \quad \sigma_r^2=\sigma_m^2+\sigma_p^2-2\rho\sigma_m\sigma_p.
\]

Doğrulanmış bağımsız kalibrasyon ve normal artık sıfır hipotezi altında
\[
H_0:r\sim\mathcal{N}(0,\sigma_r^2), \quad z=\frac{r}{\sigma_r}, \quad p=\mathrm{erfc}(|z|/\sqrt{2}).
\]

`p<alpha` ancak belirtilen model ve varsayımlar altında bir **tutarsızlık** iddiasıdır. `p>=alpha` modelin doğru olduğunu veya görüntünün gerçek olduğunu göstermez. P-değerleri **AI ile üretilmiş görüntü olasılığı** değildir.

## Güvenlik kapıları
Bir aşağıdaki koşul sağlanmazsa standartlaştırılmış efekt ve p-değeri **null** kalır, `INDETERMINATE` raporlanır:
- bilinmeyen veya desteklenmeyen fiziksel varsayımlar
- eğitim verisi ve holdout sızıntısı
- bağımsız doğrulanmayan fiziksel kalibrasyon
- sabit ölçüm/sunum birimi veya varyansın tekil olması
- bilinmeyen ölçüm–model hata korelasyonu
- dağılımın bağımsız kontrolünün bulunmaması veya testin önceden belirtilmemesi
- `real_unverified` girdileri; gerçek saha kabulü daha sonra yapılacaktır.

## Birden fazla testin birleştirilmesi
`P8-E01` **birleştirme yapmaz**. Çoklu hipotez düzeltmesi, bağımlı modüllerin ortak girdileri ve etkileşimleri `P8-E02` kapsamında olacaktır. İstatistiklerin yalnızca listelenmesi toplam kanıt gücü değildir.

## Eski modül adaptörü
`normalize_legacy_report` eski raporu SHA-256 özetiyle **tanımlayıcı kanıt** olarak bağlar; eski `PASS` değerini otomatik istatistiksel onaya yükseltmez. Bu sınırlama tasarım gereğidir.

## CLI
```powershell
python -m aiforensics list-evidence-modules
python -m aiforensics analyze-evidence --input examples/p8_e01_evidence.json --out outputs/p8_e01_analysis
python -m pytest -q
```

## Geliştirme sırası
P8-E01 kanıt sözleşmesi → P8-E02 bağımlılık/çoklu kanıt → P8-E03 açıklanabilir rapor → sistem genelinde entegrasyon → **en son** gerçek fotoğraf/kamera ölçümleri ve Windows kabulü.
