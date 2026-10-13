# P8-E02 — Bağımlı kanıtların güvenli istatistiksel değerlendirmesi

## Veri sözleşmesi

Girdi P8-E01'in \`schema_version: "p8.e01.v1"\` ve ham \`records\` alanlarını taşır. P8-E02, E01 testlerini **yeniden hesaplar**; dışarıdan gönderilen p-değerleri kabul edilmez.

Her kayıtta \`lineage\` şu alanları kapsamalıdır: \`raw_asset_id\`, \`calibration_asset_id\`, \`reference_id\`, \`holdout_batch_id\`, \`feature_family_id\`, \`model_family_id\`.

\`fusion\` yapılandırması: \`familywise_alpha\`, \`plan_pre_registered\`, \`dependency_audit_verified\`, \`dependence_unknown\`, \`declared_edges\`. Açık kenarlar \`left\`, \`right\` ve \`reason\` ister.

## Bağımlılık grafiği

E02, ortak lineage kimliğine sahip ölçümleri birleştirir. Ayrıca E01 \`provenance.source_id\` ve \`calibration_id\` ortaklıklarını görmezden gelmez. Bildirilen açık bağımlılık kenarları, gizli ortak parametre ya da model paylaşımını belirtir. Bağlı bileşenleri birbirinden bağımsız saymak gerekmez.

Eksik lineage, bağımsız kalibrasyon, kaydedilmemiş hipotez planı veya doğrulanmamış bağımlılık denetimi durumlarında kesin birleşik iddia kurulmaz.

## İstatistiksel yöntem

Geçerli marjinal p-değerleri \`p_i\` olmak üzere, bir bağımlılık grubundaki tüm koşullu sıfır hipotezleri doğruysa:

\[
p_{\mathrm{group}}=\min(1,m\min_i p_i).
\]

Bu **Bonferroni birlik üst sınırı**, keyfi bağımlılık altında grup çapındaki *intersection null* hipotezine ilişkin geçerliliği korur. Grubun reddi, yalnızca gruptaki **en az bir** sıfır hipotezinin koşullu olarak reddedilebileceğini belirtir; hangi alt kanıtın bağımsız olduğunu veya AI kökenini söylemez.

Kullanılabilir \`G\` grubun p-değerleri küçükten büyüğe sıralanır. Holm düzeltilmiş p-değeri:

\[
p^\mathrm{Holm}_{(j)} = \min(1,\max_{k\le j}((G-k+1)p_{(k)})).
\]

E01 marjinal sıfır dağılımı varsayımları ve önceden belirlenmiş değerlendirme ailesi geçerliyse, Holm test edilen grup hipotezleri üzerinde *family-wise error rate* kontrolünü keyfi bağımlılıkta sağlar. Bu bir **AI üretimi olasılığı** değildir.

## Güvenli belirsizlik

- Birbiriyle ilişkili bir gruptaki herhangi bir kayıt eksik veya geçersizse bütün grup \`NOT_TESTED\` kalır.
- \`plan_pre_registered=false\`, \`dependency_audit_verified=false\` ya da \`dependence_unknown=true\` ise birleşim \`NOT_PERFORMED\` olur.
- Bazı gruplar değerlendirilemezse \`overall_state=INDETERMINATE\`; varsa kalan grup testleri yalnız açıklayıcı değerlendirmedir.
- Her durumda \`decision=NO_AI_ORIGIN_CONCLUSION\`.

Yalnız JSON bayraklarını \`true\` yapmak gerçek bağımsız kalibrasyonun yerini **tutmaz**. Sentetik regresyon sonuçları gerçek sensör veya fotoğraf doğruluğu göstermez.

## Çalıştırma

\`\`\`powershell
python -m aiforensics analyze-fusion --input examples/p8_e02_fusion.json --out outputs/p8_e02
python scripts/p8_fusion_benchmark.py --trials 80
python -m pytest -q
\`\`\`

Sonraki adım P8-E03: insanın inceleyebildiği birleşik raporlar; gerçek fotoğraf, saha kalibrasyonu ve Windows kabulü bütün özellikler tamamlandıktan sonra.
