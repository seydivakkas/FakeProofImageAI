# P8-E03 — Açıklanabilir birleşik kanıt raporları

E03, **P8-E01** tekil fiziksel hipotez testlerinin ve **P8-E02** bağımlı kanıtların Bonferroni/Holm koşullu grup düzeyinde değerlendirmelerinin açıklama katmanıdır. E03 yeni p-değeri veya AI köken olasılığı **hesaplamaz**.

## Girdi ve hesaplama

Tek girdi E01 sözleşmesindeki ham ölçüm manifestidir (\`schema_version=p8.e01.v1\`, ayrıca E02 \`fusion\` ve \`lineage\` alanları). E03, E01 ve E02'yi **tekrar çalıştırır**; dışarıdan verilmiş özet/p-değerlerini kullanmaz.

\`\`\`powershell
python -m aiforensics explain-evidence --input examples/p8_e03_explainable.json --out outputs/p8_e03
\`\`\`

Çıktılar: \`p8_e03_explainable_report.json\` ve \`p8_e03_explainable_report.html\`. HTML JavaScript veya sunucu gerektirmez, dış bağlantılı varlık yüklemez, gömülü kullanıcı içeriğini HTML-escape ile işler. JSON bütün ölçümleri içerir; HTML'de 250 ölçümlük varsayılan görünüm sınırı gerekçesiyle birlikte belirtilir.

## Alanlar

Her kayıt: ölçülen, beklenen, artık, birim, ölçüm ve model belirsizlikleri, E01 testinin sıfır hipotezi ve tekil p-değeri, varsayımlar ve kaynakları, köken (holdout/kalibrasyon), E02 grup kimliği, grup Bonferroni p-değeri, Holm düzeltilmiş grup p-değeri, açıklamalar ve engelleme gerekçeleri. Gruplar: ortak kaynak/referans/kalibrasyon kimlikleri ve açık bağımlılık kenarları.

Bir grup reddedilirse **yalnızca en az bir koşullu fiziksel hipotezine aykırılık** sonucuna varılır; AI kökenine veya görüntünün özgünlüğüne dair çıkarım yapılmaz. \`NO_COMPONENT_NULL_REJECTED\` özgünlük kanıtı değildir. \`INDETERMINATE\` ve \`NOT_TESTED\` durumları korunur.

Kaynak SHA-256, kaynak kimliğidir; doğrulanmış kamera kökenini veya bağımsız kalibrasyonu kanıtlamaz. Rapor dosyaları kaynak kimlikleri barındırabilir; kullanıcı tarafından paylaşılmadıkça yerel kalırlar.

**Nihai gerçek kamera, gerçek fotoğraf, bağımsız ölçüm, hata oranı kalibrasyonu ve gerçek Windows cihaz kabulü tüm geliştirmelerden sonra.**
