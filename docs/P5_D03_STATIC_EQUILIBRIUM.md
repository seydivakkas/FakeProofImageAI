# P5-D03 — Yerçekimi, kütle merkezi ve statik denge kanıtı (v0.20.0)

## Kapsam ve dürüst kanıt sınırı

D03, yalnızca dışarıdan sağlanan **bağımsız metrik 3B veriler** için rijit cisimlerin statik denge **fizibilitesini** sorgular. Görüntüden kütle, kütle dağılımı, Coulomb sürtünme katsayısı, görünmeyen temas veya dış kuvvet **türetmez**. Üretilmiş bir görüntü de fiziğe uygun olabilir; fiziksel tutarsızlık tek başına AI kökeni kanıtı değildir. Gerçek fotoğraf ve gerçek kuvvet/kalibrasyon ölçümleri **son nihai doğrulama fazına** bırakılmıştır.

## Denklem

Dünya koordinatında kütle merkezi `c`, kütle `m`, yerçekimi ivmesi `g`, her bir noktasal desteğin tepki kuvveti `f_i`, temas noktası `p_i`, diğer dış kuvvetler `F_j` ve uygulama noktaları `q_j` için:

\[
\sum_i f_i + m g + \sum_j F_j = 0
\]

\[
\sum_i (p_i-c)\times f_i + \sum_j (q_j-c)\times F_j + \tau_{ext} = 0
\]

Temas başına ters tepki/çekme yasağı (unilateral) ve Coulomb sürtünmesi:

\[
N_i = n_i^T f_i \ge 0, \qquad
\|f_i - N_i n_i\|_2 \le \mu_i N_i.
\]

`reaction_normal_world` tepki yönüdür; destek düzleminin normaline paralel veya antiparalel olabilir. Noktalar sonlu destek poligonlarının içinde kalmalı. Kütle bileşenleri verilirse:

\[
m=\sum_k m_k,\qquad c=\frac{\sum_k m_k c_k}{m}.
\]

Uniform yerçekimi potansiyeli altında bağımsız bileşenler aynı toplam kuvveti `c` üzerinden uygular.

## Matematiksel güvenlik: iki taraflı sürtünme konisi

Doğrudan konik programlama bağımlılığı getirmeden `scipy.optimize.linprog` ile **iki** doğrusal fizibilite problemi kuruldu:

1. **İç yaklaşık koni** (`cone_sides=16` varsayılan): Coulomb dairesel konisinin içinde kalan çokgenle kurulmuş geçerli reaksiyon kuvvetleri. Altı bağımsız statik denge eşitliği de sağlanıyorsa, bu fiziksel model içinde **yapılabilir bir denge örneğidir** → `CONSISTENT`.
2. **Dış yaklaşık koni**: Gerçek dairesel Coulomb konisini tümüyle kapsayan teğetsel yarı-düzlemler. Bu daha **gevşek** modelde bile fizibilite yoksa, gerçek modelde de yoktur → `INCONSISTENT_UNDER_ASSUMPTIONS`.
3. Arada kalan, sayısal olarak çözülemeyen veya yetersiz/bağımsız olmayan veri içeren durumlar → `INDETERMINATE`.

Doğrusal programlama çözümü **saha veya gerçek dünya doğrulaması değildir**. Yüksek sayısal koşul sayısı, ideal rijitlik dışı reaksiyon, dinamik ivmelenme, ekstra gizli destek ve ayrık sürtünme gibi şartlar model dışındadır. Model uygunluğu şartlıdır.

## Giriş JSON sözleşmesi

```json
{
  "gravity_acceleration_world_m_s2": [0, 0, -9.81],
  "support_surfaces": [
    {
      "id": "ground",
      "normal_world": [0, 0, 1],
      "offset_world": 0,
      "polygon_world_xyz": [[-3,-3,0],[3,-3,0],[3,3,0],[-3,3,0]]
    }
  ],
  "objects": [
    {
      "id": "chair",
      "geometry_provenance": "synthetic_ground_truth",
      "all_contacts_declared": true,
      "mass_kg": 10,
      "center_of_mass_world_xyz": [0,0,1],
      "contacts": [
        {"support_id":"ground", "point_world_xyz":[-0.5,-0.5,0],
         "reaction_normal_world":[0,0,1], "friction_coefficient":0.6}
      ],
      "external_forces": [
        {"force_world_newton":[0,0,0], "application_point_world_xyz":[0,0,1]}
      ],
      "external_torque_world_newton_metre": [0,0,0]
    }
  ]
}
```

**Önemli:** Örnek tek temas noktası daha çok olumsuz fizibilite için temsilidir; dört temaslı örnek için `outputs/p5_d03_demo/p5_d03_fixture.json` dosyasına bakın. `geometry_provenance` gerçek bir ölçümün doğruluğunu **kanıtlamaz**; kullanıcı tarafından beyan edilen kaynağıdır. `image_only` veya bulunmayan kaynak kesin denge kararı verdirmez. `all_contacts_declared=true` (ve tüm kuvvetlerin bilindiği varsayımı) verilmedikçe tutarlılık değerlendirmesi `INDETERMINATE` kalır.

Bileşen bazlı kütle dağılımı `mass_components: [{"mass_kg":6,"center_world_xyz":[...]}]` ile girilebilir. Birlikte verilen bağımsız toplam kütle veya COM bu dağılımla uyuşmazsa koşullu çelişki olarak ayrı raporlanır. `center_of_mass_uncertainty_radius_world` veya `external_force_uncertainty_newton` sıfırdan büyükse henüz aralık tabanlı sağlam mekaniğe geçilmediği için **kesin karar verilmez**.

## CLI

```powershell
python -m aiforensics demo-static --out outputs/p5_d03_demo
python -m aiforensics analyze-static --input outputs/p5_d03_demo/p5_d03_fixture.json --out outputs/p5_d03_check
python scripts/p5_static_benchmark.py --trials 80 --out outputs/p5_d03_benchmark.json
python -m pytest -q
```

JSON raporu, her nesne için `state`, `reasons`, `required_contact_wrench`, `inner_solver_status`, gerektiğinde `outer_solver_status` ve denge tanığı `witness_contact_forces_world_newton` bilgilerini içerir. `NO_AI_ORIGIN_CONCLUSION` kararı tüm raporlar için geçerlidir.

## Tamamlanan sentetik senaryolar

- Tek ve çoklu destek düzlemi; kütle merkezi destek içi/kenarı/dışı.
- Kayma ve devrilme yükleri; dış kuvvetin uygulama yeri ve dış moment.
- Bilinen Coulomb sürtünme ve sürtünmesiz durum.
- Negatif normal reaksiyon gerektiren imkânsız kuvvet dengesi.
- Doğrulanmamış/geometrisi eksik verilerde abstention.
- Kütle bileşenlerinden COM üretimi; hatalı kütle/COM çelişkisi.
- Belirsiz COM ve kuvvet parametrelerinde abstention.
- Önceki P1/P2/P3/P4/P5-D01/D02 otomatik regresyonlarını koruma.

## Açık sınırlamalar / sıradaki işler

* Gerçek zamanda dinamik denge, ivme, açısal momentum ve hareket denklemleri dahil değil.
* Rijit olmayan malzeme, dağıtılmış basınç, temas yüzeyinin deformasyonu, yapışma, mıknatıs veya bilinmeyen gizli destek dahil değil.
* Sürtünme katsayısı bağımsız verilmezse fotoğraftan çıkarılmıyor.
* Belirsizlik aralıklarının tamamı için doğrulanmış robust equilibrium testleri ileride geliştirilebilir.
* 3B temas noktaları P5-D01 ve örtüşmeler P5-D02 ile aynı dünya koordinatlarında sunulabilir, ancak D03 **fotoğraftan kendiliğinden 3B ağırlık merkezi oluşturmaz**.
* P5 nihai gerçek görüntü/saha ölçümü ve Windows kabulü, kullanıcının belirlediği geliştirme sırasına göre projenin **son safhasındadır**.
