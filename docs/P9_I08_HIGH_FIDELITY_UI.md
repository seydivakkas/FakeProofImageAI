# P9-I08 — Yüksek sadakatli Tkinter arayüzü, mevcut fizik motorlarıyla

## Tamamlanan kod

Yeni ui_polish.py arayüz katmanı sekiz P1–P8 grubunu yalnızca gerçek çalışma kayıtlarından özetler. Her kartta çalışma sayısı, başarılı ve başarısız koşum durumu bulunur; bu durumlar bağımsız fiziksel doğrulama değildir.

Ana ekran: sekiz modül kartı, SHA-256 doğrulamalı gerçek dosya önizlemesi, kayıtlı analiz geçmişi, kayıtlı E03 kanıt özetleri ve E01→E03 kontrollü sentetik deneme eylemi.

Kalibrasyon: daha büyük kaynak görüntü önizlemesi, anotasyon editörü, kalibrasyon JSON girişi ve G02/G04/O01 modül kısayolları.

Fiziksel Ölçümler: görüntü, katman gezgini, P1–P7 araçları, gerçek koşum geçmişi ve E03 belirsizlik inceleme bağlantısı.

Kanıt İnceleme: kaynaklı E03 bulgularını modül, durum ve bağımlılık grubuyla gösteren tablo; kanıt, bağımlılık ve rapor gezgini kısayolları.

## Özellikle yapılmayanlar

- Sahte hata grafiği, güven yüzdesi, kamera kimliği veya AI köken olasılığı yok.
- Boş projede E03/p değeri verilmez.
- Kaydedilmiş kalibrasyon, bağımsız kamera kabulü sayılmaz.
- Fotoğrafın yüklenmesi bütün fizik motorlarına otomatik gerekli ölçümleri sağlamaz.
- Mevcut Tkinter tasarımı referans maketlerin piksel düzeyinde birebir kopyası değildir.

## Test planı

pytest ve Windows/Ubuntu CI matrisinin yanı sıra, daha önce kurulan iki çözünürlüklü Tkinter screenshot CI betiği gerçek ekranı Ubuntu/Xvfb üzerinde yakalar. Screenshot karşılaştırması ergonomik Windows son kullanıcı kabulü değildir.

## Açık kalite kapısı

1366×768 ve 1920×1080 ekranlardaki tek tek görsel düzen, DPI ve odak sırası kontrol edilmeli; ardından eksik perspektif/kamera matrisi inspector, ölçüm artık grafikleri ve gelişmiş bulgu/graph etkileşimleri değerlendirilmelidir. Gerçek fotoğraf, bağımsız kamera ve Windows 10/11 gerçek cihaz kabulü sona kalır.

Kapsam dışı ayrıca PDF imzalama ve gerçek fotoğraftan AI köken sınıflandırmasıdır.
