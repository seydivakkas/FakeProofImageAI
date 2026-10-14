# P9-I03 — Modül veri formları, önkoşullar ve güvenli çalışma planlayıcısı

**Sürüm:** v0.31.0 · **Kapsam:** Windows-first, offline Tkinter · **Doğrulama:** Sentetik kod testleri

## 1. Modül formları

`src/aiforensics/workflow_planner.py` modülündeki `FORM_CATALOG` **24 fiziksel P1–P7 modülünü ve P8-E01/E02/E03** adımlarını mevcut `desktop_core.COMMANDS` listesiyle birebir eşler. G01 doğrudan görüntü seçimini kullanır; diğer 26 modül kendi JSON ölçüm manifestini ister. Kullanıcı modül seçer, uygun manifesti yükler ya da **sentetik örnek** oluşturur. JSON alanları iç içe form ağacında veri tipi bozulmadan düzenlenebilir: `string`, `integer`, `number`, `boolean`, `array`, `object`, `null`. Kaydetme işlemi atomiktir. 32 MB JSON sınırı uygulanır.

Sentetik örnekler **bağımsız kamera kalibrasyonu**, gerçek sensör kanıtı, gerçek dünya veri doğrulaması değildir. G02/G03/G04 ve E01/E02/E03 için örnekler paket içinde `demo_forms` altında sunulur; diğer fizik modüllerinin sentetik sahneleri mevcut motorların `*_synthetic.py` fonksiyonlarından yeniden üretilir. P7-S02, örnek manifest ile birlikte **gerekli üç bağımsız sentetik NPZ kare yığınını** oluşturur. NPZ dosyaları eksik veya izin verilmeyen göreli yol kullanıyorsa plan bloke edilir.

## 2. Ön kontrol ile bilimsel geçerlilik ayrımı

Form katmanı önce dosyanın varlığını, JSON kökünün nesne olduğunu, seçili modülün üst düzey zorunlu anahtarlarını, boyut ve türleri denetler. `READY`, **komutun çağrılması için asgari sözdizimsel/yapısal koşulların sağlandığı** anlamına gelir; metrik doğruluk, kalibrasyon güvenilirliği, hipotez dağılımı veya gerçek fotoğraf kökeninin doğrulandığı anlamına **gelmez**. Bunların bilimsel/istatistiksel denetimleri ilgili P1–P8 motorlarında kalır.

Tek bir görüntüden tüm 3B, BRDF veya RAW sensör parametreleri otomatik üretilmez. Arayüz, G01 görüntü girişi hariç **bağımsız manifest** ister. Bir modülden çıkan sonuç, diğer modüle otomatik `verified` kalibrasyon olarak geçirilmez (`automatic_upstream_data_reuse=false`).

## 3. İş akışı planlayıcı

`build_execution_plan()` yalnız **seçilmiş** modüller arasında izin verilen tercih bağlantılarını topolojik sıralar. Örneğin P8-E01 → E02 → E03 iş sırası uygundur; fakat E02/E03 kendi E01 hesaplarını yaptığından tek başına kullanıldıklarında diğer modüllerin çalıştırılması gerekmez. Diğer fizik motorları yalnızca kullanıcı tarafından bağımsız girdileri sağlandığında hazır olur. Dairesel bağımlılık, yinelenen modül, eksik manifest, uygun olmayan görüntü uzantısı ve kayıp NPZ bloklanır.

`execute_plan()` her adımın kaynak dosya SHA-256 değerini yürütmeden **yeniden** karşılaştırır. Farklıysa `INPUT_CHANGED` raporlayarak adımı durdurur; alttaki izinli `Project.run` köprüsü `subprocess(shell=False)` kullanır. Başarısız adımın devamında çalışan başka modüllere sahte başarı yazılmaz. GUI'de sonraki adıma geçmeden durdurma isteği mevcuttur; çalışan işlemi zorla kapatmaz. Her çalışma ayrı `execution.json` ile kayıtlıdır.

## 4. Masaüstü bağlantısı

`fakeproof-desktop` → **Analiz Planı** → **Modül Formları ve Planlayıcıyı Aç**.
Ayrıca Kalibrasyon ve Fiziksel Ölçümler sayfalarından ilgili P1/P5 modülüyle açılabilir. Planlar `project/manifests/p9_i03_execution_plan.json` dosyasına, yürütme sonuçları `p9_i03_execution_result.json` dosyasına kaydedilir. Kullanıcının düzenlediği JSON ayrıca açık hedef dosyasına atomik yazılır.

## 5. Sınırlar ve sonraki iş

Bu aşama, daha önce üretilmiş ve ayrı belgelenmiş fizik motorlarının **tüm girişlerini otomatik fotoğraftan türettiğini** veya bütün kullanıcı anotasyonlarını otomatik kalibrasyona dönüştürdüğünü iddia etmez. Her modülün en içteki özel bilimsel koşulları motorun kendi raporunda denetlenir; form katmanı tüm bilimsel eşdeğerlik ilişkilerini kurmaz.

P9-I04: gelişmiş overlay/kanıt gezgini, PDF dahil rapor akışı, masaüstü dağıtımı. Tüm özellikler tamamlandıktan sonra **gerçek fotoğraf, bağımsız kamera ölçümü, istatistiksel yanlış alarm kalibrasyonu ve gerçek Windows cihaz kabulü** uygulanacak. `NO_AI_ORIGIN_CONCLUSION` korunur.

## Kullanım

```powershell
python -m pip install -e ".[desktop,dev]"
fakeproof-desktop
python -m pytest -q
```
