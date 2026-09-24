# RetroChat 98 / FutureChat 2058

1998 internet kültürü ile kurgusal bir 2058 geleceği arasında geçiş yapılan, Gemini destekli Türkçe sohbet deneyimi. Aynı soruyu iki döneme sorup yanıtları yan yana karşılaştırabilirsiniz.

> **2058 modu bir gelecek kurgusudur.** Yanıtları gerçekleşmiş olay veya doğrulanmış öngörü olarak kullanmayın.

## Kısa demo

- [Kısa kullanım videosu](demo/retrochat-demo.mp4)
- [Masaüstü karşılaştırma ekranı](demo/desktop.png)
- [Mobil karşılaştırma ekranı](demo/mobile.png)
- [2058 görünümü](demo/future.png)

Demo medyası `scripts/capture_demo.py` ile örnek yanıtlar kullanılarak üretildi; gerçek Gemini çıktısı değildir. Canlı ürünü kullanmak için kendi API anahtarınız gerekir.

## Özellikler

- 1998 ve 2058 kişilikleri arasında geçiş; her dönemin sohbeti ayrı tutulur.
- Aynı sorunun iki dönemdeki yanıtını eş zamanlı karşılaştırma.
- İsteğe bağlı gerçeklik rehberi: 1998 yanıtındaki doğrulanabilir iddiaları Google Search grounding ile kaynaklara karşı kontrol etme ve 2058 bölümünü açıkça yaratıcı kurgu olarak ayırma.
- Karşılaştırmada konu seçimi ve iki yanıt tamamlanınca 1998–2058 arasındaki üç kurgusal dönüm noktasını anlatan zaman kapsülü.
- İnternet, dijital kültür ve gündelik yaşam için dörder soruluk konu yolculukları; adım adım ilerleme ve paket tamamlanınca iki dönemi içeren metin özeti.
- Tamamlanan karşılaştırmaları bu cihazda saklayan ve daha sonra yeniden açan karşılaştırma geçmişi.
- Karşılaştırmadaki soru ve yanıtı bağlam olarak koruyup 1998 ya da 2058 sohbetinde devam etme.
- Tamamlanan karşılaştırma için yedi gün geçerli yeniden açılabilir bağlantı üretme; cihazın paylaşım menüsüyle paylaşma, destek yoksa bağlantı ve metni kopyalama, ayrıca metin veya PNG olarak indirme.
- Akış hâlinde görünen yanıtlar, bekleyen isteği durdurma, anlaşılır hata ve tek tıkla tekrar deneme.
- Bu cihazda saklanan sohbetler; yeni sohbet açma, eski sohbeti seçme, silme ve kısa süre içinde silmeyi geri alma.
- Kayıtlı sohbetleri başlık veya mesaj içeriğinde arama; tüm sohbetleri JSON ya da metin dosyası olarak indirme ve JSON yedeğini doğrulayarak geri yükleme.
- Tamamlanan yanıtlarda döneme uygunluk, yarım kalma ve tekrar için tek seçimlik geri bildirim; sunucuya yalnızca seçilen kategori gönderilir.
- Önceki 2030 sohbetleri arşiv etiketiyle korunur; yeni 2058 yanıtlarına eski dönem konuşması bağlam olarak gönderilmez.
- Örnek sorular, mobil düzen, klavye kullanımı, ekran okuyucu duyuruları ve azaltılmış hareket desteği.
- Bu cihazda saklanan okuma tercihleri: yazı boyutu, hareketi azaltma ve uzun yanıtları okunabilir parçalara ayırma.
- PWA olarak ana ekrana kurulma; uygulama kabuğunu ve bu cihazdaki kayıtlı sohbetleri çevrimdışıyken yeniden açma.
- Hesap açmadan yerel kullanıma devam etme; isteğe bağlı kullanıcı adı/parola hesabıyla en fazla 30 sohbeti cihazlar arasında açıkça tetiklenen birleştirme akışıyla eşitleme.
- Redis yapılandırıldığında sunucular arasında ortak, aksi hâlde SQLite tabanlı istek sınırı; oturumlu kullanıcı başına günlük model kotası, güvenlik başlıkları ve mesaj içeriği toplamayan kalıcı ölçümler.
- Model token sınırına ulaşırsa yanıtı devam ettirme; tamamlanamayan yanıtı bitmiş gibi kaydetmeme.

## Yerelde çalıştırma

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

`.env` içindeki `GEMINI_API_KEY` değerini ayarlayın. Anahtar yalnızca sunucuda okunur.

```powershell
uvicorn app.main:app --reload
```

Ardından `http://127.0.0.1:8000` adresini açın. İlk ekranda örnek sorulara basabilir veya **İki dönemi karşılaştır** düğmesini kullanabilirsiniz. Sohbetler tarayıcının `localStorage` alanına yazılır; aynı cihazdaki başka kullanıcılar bu tarayıcı profilini paylaşırsa sohbetleri görebilir. **Bu sohbeti sil** düğmesi ilgili kaydı kaldırır. Sunucuda sohbet geçmişi saklanmaz; Gemini isteğini oluşturmak için son 12 mesaj tarayıcıdan gönderilir.
