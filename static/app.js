const form = document.querySelector("#chat-form");
const input = document.querySelector("#message-input");
const chatLog = document.querySelector("#chat-log");
const sendButton = document.querySelector("#send-button");
const typing = document.querySelector("#typing");
const statusText = document.querySelector("#status-text");
const charCount = document.querySelector("#char-count");
const eraToggle = document.querySelector("#era-toggle");
const eraAction = document.querySelector(".era-action");
const eraDestination = document.querySelector(".era-destination");
const wordmark = document.querySelector("#wordmark");
const wordmarkTop = document.querySelector("#wordmark-top");
const wordmarkMain = document.querySelector("#wordmark-main");
const tagline = document.querySelector("#tagline");
const marqueeTrack = document.querySelector("#marquee-track");
const windowTitle = document.querySelector("#window-title");
const connection = document.querySelector("#connection b");
const typingText = document.querySelector("#typing-text");
const messageLabel = document.querySelector("#message-label");
const statusZone = document.querySelector("#status-zone");
const footerNote = document.querySelector("#footer-note");
const counter = document.querySelector("#counter");

const history = [];
let era = "1998";

const eraContent = {
  "1998": {
    title: "RetroChat 98 — İnternete Bağlan",
    brandLabel: "RetroChat 98",
    brandTop: "RETRO",
    brandYear: "98",
    tagline: "Bilgi otoyolundaki<br>en havalı sohbet noktası!",
    marquee: "★ HOŞ GELDİN NET GEZGİNİ!   •   EN İYİ 800×600 ÇÖZÜNÜRLÜKTE GÖRÜNTÜLENİR   •   MODEMİNİ HAZIRLA   ★",
    windowTitle: "RetroChat 98 — Sohbet Odası",
    connection: "56K BAĞLI",
    typing: "RetroChat98 hatta veri arıyor...",
    label: "Mesajın:",
    placeholder: "Bir şeyler yaz...",
    zone: "Internet bölgesi",
    footer: "Bu sayfa sevgiyle ve düz HTML ile yapılmıştır.",
    counter: "ZİYARETÇİ: <span>0001998</span>",
    action: "Modernleştir",
    destination: "2030'a geç",
    welcome: "Selam net gezgini! Takvimler 1998'i gösteriyor. Modemin cızırtısı arasında sana nasıl yardımcı olabilirim?",
  },
  "2030": {
    title: "NovaChat 30 — Geleceğe Bağlan",
    brandLabel: "NovaChat 30",
    brandTop: "NOVA",
    brandYear: "30",
    tagline: "Yarının düşünceleri,<br>şimdi aynı frekansta.",
    marquee: "SİNYAL KARARLI   /   KUANTUM GÜVENLİ KANAL   /   2030 İLETİŞİM AĞI ÇEVRİMİÇİ",
    windowTitle: "NovaChat 30 — İletişim Merkezi",
    connection: "NOVA AĞI AKTİF",
    typing: "NovaChat30 olasılıkları hesaplıyor...",
    label: "İletini yaz",
    placeholder: "2030'a bir soru gönder...",
    zone: "Güvenli ağ · 2030",
    footer: "İnsan merakı ile yeni nesil zekânın buluşma noktası.",
    counter: "SİNYAL <span>KARARLI</span>",
    action: "1998'e dön",
    destination: "retro moda geç",
    welcome: "2030 bağlantısı kuruldu. Ben NovaChat30. Yeni dünyanın içinden sana nasıl yardımcı olabilirim?",
  },
};

function currentTime() {
  return new Intl.DateTimeFormat("tr-TR", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date());
}

function addMessage(role, content) {
  const article = document.createElement("article");
  article.className = `message ${role === "user" ? "user-message" : "bot-message"}`;

  const avatar = document.createElement("div");
  avatar.className = `avatar ${role === "user" ? "user-avatar" : "bot-avatar"}`;
  avatar.setAttribute("aria-hidden", "true");
  avatar.textContent = role === "user" ? "SEN" : era === "2030" ? "N30" : "R98";

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  const sender = document.createElement("span");
  sender.className = "sender";
  sender.textContent = role === "user" ? "Sen" : era === "2030" ? "NovaChat30" : "RetroChat98";

  const paragraph = document.createElement("p");
  paragraph.textContent = content;

  const time = document.createElement("time");
  time.textContent = currentTime();

  bubble.append(sender, paragraph, time);
  article.append(avatar, bubble);
  chatLog.append(article);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function setBusy(isBusy) {
  input.disabled = isBusy;
  sendButton.disabled = isBusy;
  typing.hidden = !isBusy;
  statusText.textContent = isBusy
    ? era === "2030" ? "Olasılıklar taranıyor..." : "Gemini aranıyor..."
    : era === "2030" ? "Sistem hazır" : "Hazır";
}

async function sendMessage(message) {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history: history.slice(-12), era }),
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "Sunucuya ulaşılamadı.");
  }
  return data.reply;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) return;

  addMessage("user", message);
  input.value = "";
  charCount.textContent = "0 / 2000";
  setBusy(true);

  try {
    const reply = await sendMessage(message);
    history.push({ role: "user", content: message });
    history.push({ role: "assistant", content: reply });
    addMessage("assistant", reply);
  } catch (error) {
    addMessage("assistant", `BAĞLANTI NOTU: ${error.message}`);
    statusText.textContent = "Bağlantı hatası";
  } finally {
    setBusy(false);
    input.focus();
  }
});

function switchEra() {
  era = era === "1998" ? "2030" : "1998";
  const content = eraContent[era];

  document.body.dataset.era = era;
  document.title = content.title;
  eraToggle.setAttribute("aria-pressed", String(era === "2030"));
  eraAction.textContent = content.action;
  eraDestination.textContent = content.destination;
  wordmark.setAttribute("aria-label", content.brandLabel);
  wordmarkTop.textContent = content.brandTop;
  wordmarkMain.innerHTML = `CHAT <strong>${content.brandYear}</strong>`;
  tagline.innerHTML = content.tagline;
  marqueeTrack.textContent = content.marquee;
  windowTitle.textContent = content.windowTitle;
  connection.textContent = content.connection;
  typingText.textContent = content.typing;
  messageLabel.textContent = content.label;
  input.placeholder = content.placeholder;
  statusZone.textContent = content.zone;
  footerNote.textContent = content.footer;
  counter.innerHTML = content.counter;
  statusText.textContent = era === "2030" ? "Sistem hazır" : "Hazır";

  history.length = 0;
  chatLog.replaceChildren();
  addMessage("assistant", content.welcome);
  input.focus();
}

eraToggle.addEventListener("click", switchEra);

input.addEventListener("input", () => {
  charCount.textContent = `${input.value.length} / 2000`;
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});
