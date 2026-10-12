# FakeProofImageAI

**Physics-first image forensics** — Türkçe teknik proje; matematiksel geometrik, fotometrik ve sensör tabanlı kanıtlar.

## Amaç
Görüntülerdeki gözlemleri fiziksel model → matematiksel kısıt → ölçüm artığı → belirsizlik/istatistiksel kanıt zinciriyle değerlendirmek. **Fiziksel tutarsızlık, görüntünün yapay zekâyla üretildiğini tek başına kanıtlamaz.**

## Geliştirme ve doğrulama ayrımı
- P1–P7: yerel proje paketlerinde fizik motorları ve sentetik testler geliştirilmiştir; uzak depoya kaynak aktarımı iş paketi bazında yürütülecektir.
- P8-E01: ortak kanıt şeması, belirsizlik ve koşullu hipotez testleri — geliştirme aşamasında.
- P8-E02: bağımlı kanıtların temkinli birleşimi — planlandı.
- P8-E03: açıklanabilir birleşik kanıt raporu — planlandı.
- **Gerçek kamera verisi, bağımsız saha ölçümü, yanlış pozitif kalibrasyonu ve Windows kabulü: tüm özellik geliştirmelerinden sonra.**

## İş paketleri
Ayrıntılı durum ve arşiv kayıtları `docs/work-packages/` ve `docs/ROADMAP.md` altında sürüm bazında izlenecektir. Önceden tamamlandığı bildirilen sentetik testler, gerçek veri validasyonu sayılmaz.

## Mühendislik ilkesi
`CONSISTENT_UNDER_ASSUMPTIONS`, `INCONSISTENT_UNDER_ASSUMPTIONS`, `INDETERMINATE` ayrımı korunur. İstatistiksel anlamlılık, AI kökeninin posterior olasılığı değildir. Tekrarlanan ölçümler ve modüller arası bağımlılıklar hesaba katılmadan kanıtlar toplanmaz.

> Depo aşamalı olarak senkronize edilir; bir modülün GitHub'da bulunması ve sentetik testlerden geçmiş olması iki ayrı kabul kriteridir.
