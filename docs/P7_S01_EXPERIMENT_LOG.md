# P7-S01 — Sentetik sensör gürültüsü deney günlüğü (v0.24.0)

**Bu dosyadaki sayılar yalnızca simüle edilmiş Poisson–Gaussian RAW sensör örneklerine dayanır.** Proje, gerçek kamera verilerinde yanlış alarm veya yapay zekâ görüntüsü tespit başarı oranı iddia etmez.

## Çalışma düzeni

- Kod: `src/aiforensics/sensor_noise.py`, `src/aiforensics/sensor_synthetic.py`, `scripts/p7_sensor_benchmark.py`.
- Koşu: `python scripts/p7_sensor_benchmark.py --trials 80 --seed 310100 --out outputs/p7_s01_benchmark.json`.
- 80 bağımsız kontrollü rastgele tohum; 40'ı `known_parameters`, 40'ı `fit_train_parameters`.
- Her koşuda 14 *train*, 24 *holdout* koşul, her koşulda 4.096 simüle edilmiş bağımsız RAW ADU örneği.
- Her koşudaki son üç holdout'ta ortalama 22 ADU veya varyans yüzde 55 kasıtlı değiştirildi.
- Gerçek model: 2.0 e⁻/ADU, 4.5 e⁻ RMS read noise, 1.65 e⁻/s dark current; black=128 ADU; 25.000 e⁻ full well; ADC ceiling 16.383 ADU.
- `fit_train_parameters` ilk üç parametreyi yalnız training istatistiğinden kestiriyor. Bilinen kara seviye ve full-well değerleri bağımsız tanımlanıyor.
- Göreli model residual'ları: `z<=2.5` koşullu uyum; `z>=5` koşullu tutarsızlık; arası/eksik provenans belirsiz.

## Sonuçlar

| Ölçüm | Değer |
|---|---:|
| Tamamlanan kontrollü deneme | 80 / 80 |
| Holdout sayısı | 1.920 |
| Kasıtlı değiştirilen holdout | 240 |
| Saptanan kasıtlı bozulma | 240 / 240 |
| Bozulmamış holdout | 1.680 |
| Bozulmamışta kesin yanlış ihlal | 0 |
| Bozulmamışta belirsiz | 35 |
| Bozulmamışta koşullu uyumlu | 1.645 |
| Kazanç kestirimi medyan mutlak hata (fit modu, 40 deneme) | 0,0001894 e⁻/ADU |
| Kazanç kestirimi p90 mutlak hata (fit modu) | 0,0003926 e⁻/ADU |
| Tüm eski/yeni otomatik regresyon testleri | 705 / 705 |

**Negatif kontrollerin tamamında** işlenmiş JPEG girdisi, bağımsız fotoelektron referansı eksikliği, sıcaklık kontrolü eksikliği, saturasyon, bilinmeyen sensör parametre provenansı veya PRNU/FPN'nin kontrol edilememesi için `INDETERMINATE` döndü.

## Kritik bilimsel sınırlar

Bu koşular, **aynı model ailesinden üretilen sentetik veri** ile matematiksel uygulama regresyonunu kontrol eder. İncelenen sensörlerde PRNU, DSNU, satır/sütun korelasyonu, analog kazanç değişimi, CFA, nonlineer ADC, gerçek sıcaklık bağımlılığı ve kamera ISP zinciri bulunmaz. Teorik moment varyansı için kullanılan z-skorları tam bir yanlış alarm olasılığı veya P8'de kalibre edilmiş bir istatistiksel test değildir. Eğitim kovaryansı yerel analitik yaklaşımdır. Bağımsız gerçek kamera ve Windows native kabulü **geliştirmeler tamamlandıktan sonra** yapılacaktır.
