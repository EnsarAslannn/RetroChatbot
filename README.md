# RetroChat 98

1998 yılında yaşadığına inanan, Gemini destekli eğitim amaçlı bir sohbet botu.
Backend FastAPI; arayüz düz HTML, CSS ve JavaScript ile hazırlanmıştır.

Sayfanın üstündeki **Modernleştir** düğmesi arayüzü NovaChat 30 görünümüne
dönüştürür ve chatbotun kendisini 2030 yılında sanmasını sağlar. Aynı düğmeyle
1998 görünümüne geri dönülebilir. Dönem değiştirildiğinde iki kişiliğin sohbet
bağlamları karışmasın diye ekrandaki oturum sıfırlanır.

## Kurulum

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

`.env` dosyasını açıp `GEMINI_API_KEY` değerini kendi anahtarınızla değiştirin.
Anahtar yalnızca backend tarafından okunur ve tarayıcıya gönderilmez.

## Çalıştırma

```powershell
uvicorn app.main:app --reload
```

Ardından `http://127.0.0.1:8000` adresini açın.

## Testler

```powershell
python -m pytest tests -q -p no:cacheprovider
```
