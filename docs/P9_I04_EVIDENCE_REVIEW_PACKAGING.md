# P9-I04 — Görsel katman yönetimi, açıklanabilir bulgu gezgini ve Windows dağıtım altyapısı

## İşlevsel kapsam

- **Görsel Katmanlar:** Proje envanterine eklenmiş görüntü SHA-256 yeniden hesaplanarak açılır. Kullanıcının P9-I02 ile oluşturduğu anotasyon JSON'u, ancak aynı özgün görüntü SHA'sıyla eşleşirse çizilir. Elle eklenen PNG katmanlarının çözünürlüğü özgün görüntüyle birebir aynı olmalıdır. Her görsel katman açılıp kapatılabilir; yakınlaştırma ve pan uygulanır.
- **Kanıt İnceleme:** Yalnız projeye ait gerçek E03 JSON raporları listelenir. E01 ölçümü, belirsizlik, varsayımlar, kaynak/kalibrasyon ve E02 grup/p-değeri, karar gerekçeleri incelenir.
- **Bulgu–görüntü bağlantısı:** Otomatik içerik eşleştirme yapılmaz. Kullanıcı, bir E03 bulgusunu projede kayıtlı görüntüye açıkça bağlayabilir. Kaydın `link_type=user_asserted_not_verified` alanı korunur; bu bağımsız sensör/provenans doğrulaması değildir. Geçersiz hash ve bilinmeyen bulgu reddedilir.
- **Bağımlılık Grafiği:** Yalnız E03 `dependency_groups.shared_evidence.shared_references` ve `explicit_edges` kullanılır. Görünmeyen veya sezilen kenarlar oluşturulmaz. Görselleştirme performansı için ilk 120 düğüm ve 300 kenar çizilir; diğerleri raporun JSON'unda korunur.
- **Rapor Gezgini:** Gerçek E01/E02/E03 çıktıları, SHA-256, sözleşme sürümü ve durumla listelenir. E03 HTML, yerel tarayıcıda açılır. JSON/HTML'de AI olasılığı verilmez; yeni p-değeri üretilmez.

## Windows dağıtım

Çalışan kaynak sürüm:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[desktop,dev]"
fakeproof-desktop
```

**Derleme altyapısı**, `scripts/build_windows_desktop.ps1` içinde `PyInstaller --onedir --windowed` kullanır. Bu adım üçüncü taraf API anahtarı veya bulut API'si istemez. Derleme için Windows bilgisayarında daha önceden kurulu bir Python, Tkinter, PyInstaller ve uygulamanın yerel bağımlılıkları gereklidir. İnternetsiz kurulum isteniyorsa Python wheel paketleri önceden edinilip `pip --no-index --find-links` ile kurulmalıdır. Betik PyInstaller'ı kendiliğinden indirmez.

```powershell
python -m pip install -e ".[desktop]"
# PyInstaller daha önce kurulmuş olmalıdır
powershell -ExecutionPolicy Bypass -File scripts\build_windows_desktop.ps1
```

**Frozen CLI köprüsü:** PyInstaller exe çalışırken `desktop_core.Project.run()` normal `python -m aiforensics` yerine aynı exe'yi `--cli` yönlendiricisiyle başlatır. Bu yolla modüller ayrı bağımsız Windows Python kurulumuna ihtiyaç duymadan çağrılabilir. `desktop_app.main()` bu anahtarı arayüzü açmadan önce kontrol eder ve CLI giriş noktasına aktarır. Normal kaynak çalışmasında davranış değişmez.

**Kabul sınırı:** GitHub Actions üzerindeki Windows Python testleri GUI penceresini gerçek kullanıcı gibi tıklamaz, PyInstaller'ın son kullanıcı makinesindeki davranışını da garanti etmez. Windows 10/11 gerçek cihaz kurulumu, antivirüs kontrolü, tam P1–P8 CLI zinciri ve GUI kabulü **en son** yapılacaktır. PDF üretimi ve kriptografik dijital imza bu pakette uygulanmamıştır.

## Bilimsel güvenlik

Görüntü kaynağı, anotasyon, PNG katmanı ve kullanıcı bağlantıları `unverified` statüsüyle yönetilir. E01/E02/E03 yalnız koşullu fiziksel hipotezleri açıklar. **Tutarsızlık = AI üretimi** veya **p-değeri = AI olasılığı** gibi iddialar yasaktır.
