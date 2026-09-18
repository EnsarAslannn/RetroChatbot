const $ = (s) => document.querySelector(s);
const input = $("#message-input"), chatLog = $("#chat-log"), statusText = $("#status-text");
const typing = $("#typing"), cancelButton = $("#cancel-button"), announcement = $("#announcement");
const chatError = $("#chat-error"), comparePanel = $("#compare-panel"), compareResults = $("#compare-results");
let completedComparison = null;
const storageKey = "retrochat-sessions-v1";
const preferencesKey = "retrochat-reading-v1";
function readPreferences() {
  try {
    const saved = JSON.parse(localStorage.getItem(preferencesKey) || "{}");
    return {
      textSize: ["normal", "large", "larger"].includes(saved.textSize) ? saved.textSize : "normal",
      motion: ["system", "reduced"].includes(saved.motion) ? saved.motion : "system",
      splitAnswers: saved.splitAnswers === true
    };
  } catch { return { textSize: "normal", motion: "system", splitAnswers: false }; }
}
let preferences = readPreferences();
function applyPreferences() {
  document.body.dataset.textSize = preferences.textSize;
  document.body.dataset.motion = preferences.motion;
  $("#text-size").value = preferences.textSize;
  $("#motion-setting").value = preferences.motion;
  $("#split-answers").checked = preferences.splitAnswers;
}
function savePreferences() {
  try { localStorage.setItem(preferencesKey, JSON.stringify(preferences)); }
  catch { statusText.textContent = "Okuma ayarları kaydedilemedi"; }
  applyPreferences();
}

function sendEvent(event) {
  fetch("/api/events", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event }), keepalive: true
  }).catch(() => {});
}
const eraContent = {
  "1998": {
    title: "RetroChat 98 — İnternete Bağlan", brand: "RETRO", year: "98",
    tagline: "Bilgi otoyolundaki<br>en havalı sohbet noktası!",
    marquee: "★ HOŞ GELDİN NET GEZGİNİ! · EN İYİ 800×600 ÇÖZÜNÜRLÜKTE GÖRÜNTÜLENİR · MODEMİNİ HAZIRLA ★",
    window: "RetroChat 98 — Sohbet Odası", connection: "56K BAĞLI", typing: "RetroChat98 hatta veri arıyor...",
    label: "Mesajın:", placeholder: "Bir şeyler yaz...", zone: "Internet bölgesi",
    footer: "Bu sayfa sevgiyle ve düz HTML ile yapılmıştır.", counter: "ZİYARETÇİ: <span>0001998</span>",
    action: "Modernleştir", destination: "2058'e geç",
    welcome: "Selam net gezgini! Takvimler 1998'i gösteriyor. Modemin cızırtısı arasında sana nasıl yardımcı olabilirim?",
    disclaimer: "1998 dönemi canlandırması. Yanıtları önemli kararlar için doğrula."
  },
  "2058": {
    title: "FutureChat 2058 — Geleceğe Bağlan", brand: "FUTURE", year: "58",
    tagline: "Yarının düşünceleri,<br>şimdi aynı frekansta.",
    marquee: "SİNYAL KARARLI / 2058 İLETİŞİM AĞI ÇEVRİMİÇİ / GELECEĞİ KEŞFET",
    window: "FutureChat 2058 — İletişim Merkezi", connection: "FUTURE AĞI AKTİF", typing: "FutureChat2058 olasılıkları hesaplıyor...",
    label: "İletini yaz", placeholder: "2058'e bir soru gönder...", zone: "Gelecek kurgusu · 2058",
    footer: "İnsan merakı ile yeni nesil zekânın buluşma noktası.", counter: "SİNYAL <span>KARARLI</span>",
    action: "1998'e dön", destination: "retro moda geç",
    welcome: "2058 bağlantısı kuruldu. Ben FutureChat2058. Geleceğin içinden sana nasıl yardımcı olabilirim?",
    disclaimer: "2058 yanıtları yaratıcı bir gelecek kurgusudur; doğrulanmış öngörü değildir."
  }
};

function readSessions() {
  try {
    const value = JSON.parse(localStorage.getItem(storageKey) || "[]");
    if (!Array.isArray(value)) return [];
    return value.filter((item) => item && typeof item.id === "string" && ["1998", "2030", "2058"].includes(item.era) && Array.isArray(item.messages))
      .slice(0, 30).map((item) => {
        const messages = item.messages.filter((message) =>
          ["user", "assistant"].includes(message.role) && typeof message.content === "string").slice(-100);
        return item.era === "2030"
          ? { ...item, era: "2058", title: `2030 arşivi · ${item.title}`, messages, legacyMessageCount: messages.length }
          : { ...item, messages };
      });
  } catch { return []; }
}

let sessions = readSessions(), activeId = sessions[0]?.id || null, era = sessions[0]?.era || "1998";
let activeRequest = null, failedIndex = null;
const currentSession = () => sessions.find((item) => item.id === activeId);
const timeLabel = () => new Intl.DateTimeFormat("tr-TR", { hour: "2-digit", minute: "2-digit" }).format(new Date());

function persist() {
  sessions.sort((a, b) => b.updated - a.updated);
  sessions = sessions.slice(0, 30);
  try { localStorage.setItem(storageKey, JSON.stringify(sessions)); }
  catch { statusText.textContent = "Bu cihazda sohbet kaydedilemedi"; }
}

function newSession(selectedEra = era) {
  const session = { id: crypto.randomUUID(), era: selectedEra, title: "Yeni sohbet", messages: [], updated: Date.now() };
  sessions.unshift(session); activeId = session.id; era = selectedEra;
  persist(); render(); return session;
}

function addMessage(role, content, label = timeLabel()) {
  const article = document.createElement("article");
  article.className = `message ${role === "user" ? "user-message" : "bot-message"}`;
  const avatar = document.createElement("div");
  avatar.className = `avatar ${role === "user" ? "user-avatar" : "bot-avatar"}`;
  avatar.setAttribute("aria-hidden", "true");
  avatar.textContent = role === "user" ? "SEN" : era === "2058" ? "F58" : "R98";
  const bubble = document.createElement("div"); bubble.className = "bubble";
  const sender = document.createElement("span"); sender.className = "sender";
  sender.textContent = role === "user" ? "Sen" : era === "2058" ? "FutureChat2058" : "RetroChat98";
  const paragraph = document.createElement("p"); paragraph.textContent = content;
  const time = document.createElement("time"); time.textContent = label;
  bubble.append(sender, paragraph, time); article.append(avatar, bubble); chatLog.append(article);
  if (role === "assistant") splitLongAnswer(paragraph, content);
  chatLog.scrollTop = chatLog.scrollHeight;
  return { article, paragraph };
}

function splitLongAnswer(paragraph, content) {
  if (!preferences.splitAnswers || content.length < 600) return;
  const chunks = [], words = content.trim().split(/\s+/);
  let part = "";
  for (const word of words) {
    if (part && `${part} ${word}`.length > 420) { chunks.push(part); part = word; }
    else part = part ? `${part} ${word}` : word;
  }
  if (part) chunks.push(part);
  if (chunks.length < 2) return;
  paragraph.textContent = chunks[0]; paragraph.classList.add("answer-part");
  for (const chunk of chunks.slice(1)) {
    const next = document.createElement("p"); next.className = "answer-part"; next.textContent = chunk;
    paragraph.parentNode.insertBefore(next, paragraph.nextSibling);
    paragraph = next;
  }
}

function renderSessions() {
  const list = $("#session-list"); list.replaceChildren();
  const query = $("#session-search").value.trim().toLocaleLowerCase("tr-TR");
  const matches = sessions.filter((session) => !query || [session.title, ...session.messages.map((message) => message.content)]
    .some((value) => value.toLocaleLowerCase("tr-TR").includes(query)));
  $("#session-search-empty").hidden = matches.length > 0;
  for (const session of matches) {
    const button = document.createElement("button"); button.type = "button";
    button.className = "session-item";
    if (session.id === activeId) button.setAttribute("aria-current", "true");
    button.textContent = `${session.era} · ${session.title}`;
    button.addEventListener("click", () => {
      if (activeId === session.id) return;
      cancelActive(); activeId = session.id; era = session.era; render();
    });
    const row = document.createElement("li"); row.append(button); list.append(row);
  }
  $("#delete-chat").disabled = !currentSession()?.messages.length;
  $("#export-json").disabled = !sessions.some((session) => session.messages.length);
  $("#export-text").disabled = $("#export-json").disabled;
}

function renderEra() {
  const content = eraContent[era];
  document.body.dataset.era = era; document.title = content.title;
  $("#era-toggle").setAttribute("aria-pressed", String(era === "2058"));
  $(".era-action").textContent = content.action; $(".era-destination").textContent = content.destination;
  $("#wordmark").setAttribute("aria-label", era === "2058" ? "FutureChat 2058" : "RetroChat 98");
  $("#wordmark-top").textContent = content.brand;
  $("#wordmark-main").innerHTML = `CHAT <strong>${content.year}</strong>`;
  $("#tagline").innerHTML = content.tagline; $("#marquee-track").textContent = content.marquee;
  $("#window-title").textContent = content.window; $("#connection b").textContent = content.connection;
  $("#typing-text").textContent = content.typing; $("#message-label").textContent = content.label;
  input.placeholder = content.placeholder; $("#status-zone").textContent = content.zone;
  $("#footer-note").textContent = content.footer; $("#counter").innerHTML = content.counter;
  $("#era-disclaimer").textContent = content.disclaimer;
  statusText.textContent = era === "2058" ? "Sistem hazır" : "Hazır";
}

function clearError() { chatError.hidden = true; failedIndex = null; }
function render() {
  renderEra(); renderSessions(); clearError(); chatLog.replaceChildren();
  const session = currentSession();
  if (session?.legacyMessageCount) $("#era-disclaimer").textContent += " Önceki 2030 sohbeti arşivlendi; yeni yanıtlar 2058 döneminden gelir.";
  if (!session?.messages.length) addMessage("assistant", eraContent[era].welcome, "şimdi");
  else for (const message of session.messages) addMessage(message.role, message.content, message.time || "önce");
  if (session?.messages.at(-1)?.role === "user") {
    failedIndex = session.messages.length - 1;
    $("#chat-error-text").textContent = "Bu mesaj için yanıt alınmadı.";
    chatError.hidden = false;
  }
}

function setBusy(busy, kind = "chat") {
  input.disabled = busy; $("#send-button").disabled = busy;
  typing.hidden = !busy || kind !== "chat"; cancelButton.hidden = !busy || kind !== "chat";
  $("#compare-cancel").hidden = !busy || kind !== "compare";
  $("#capsule-open").disabled = busy;
  $("#compare-input").disabled = busy; compareForm.querySelector('button[type="submit"]').disabled = busy;
  statusText.textContent = busy ? kind === "compare" ? "İki dönem yanıtlıyor..." : "Yanıt bekleniyor..." : era === "2058" ? "Sistem hazır" : "Hazır";
}

function cancelActive() {
  if (!activeRequest) return;
  const request = activeRequest; activeRequest = null; request.controller.abort();
  request.placeholder?.article.remove(); setBusy(false);
}

function errorMessage(detail, status) {
  if (status === 429 || detail?.code === "rate_limited") return "Çok fazla istek gönderildi. Bir dakika sonra tekrar dene.";
  if (detail?.message) return detail.message;
  if (status === 503) return "Sohbet hizmeti şu an meşgul. Biraz sonra tekrar dene.";
  return "Bağlantı kurulamadı. İnternet bağlantını kontrol edip tekrar dene.";
}

async function streamReply(message, history, selectedEra, signal, onChunk) {
  const response = await fetch("/api/chat/stream", {
    method: "POST", headers: { "Content-Type": "application/json" }, signal,
    body: JSON.stringify({ message, history, era: selectedEra })
  });
  if (!response.ok) {
    let detail; try { detail = (await response.json()).detail; } catch { /* use generic error */ }
    throw new Error(errorMessage(detail, response.status));
  }
  if (!response.body) throw new Error("Tarayıcı akış yanıtını açamadı.");
  const reader = response.body.getReader(), decoder = new TextDecoder();
  let buffer = "", fullText = "", finished = false;
  while (!finished) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done }).replace(/\r\n/g, "\n");
    let boundary;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const packet = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
      const name = packet.match(/^event: (.+)$/m)?.[1];
      const dataLine = packet.match(/^data: (.+)$/m)?.[1];
      const data = dataLine ? JSON.parse(dataLine) : {};
      if (name === "chunk") { fullText += data.text || ""; onChunk(fullText); }
      if (name === "error") throw new Error(errorMessage(data));
      if (name === "done") { finished = true; break; }
    }
    if (done && !finished) throw new Error("Yanıt tamamlanamadı. Tekrar dene.");
  }
  await reader.cancel().catch(() => {});
  return fullText;
}

async function runChat(message, retryAt = null) {
  if (activeRequest) return;
  const session = currentSession(), index = retryAt === null ? session.messages.length : retryAt;
  const history = session.messages.slice(Math.max(0, index - 12, session.legacyMessageCount || 0), index).map(({ role, content }) => ({ role, content }));
  if (retryAt === null) {
    if (index === 0) sendEvent("chat_started");
    session.messages.push({ role: "user", content: message, time: timeLabel() });
    const title = message.length > 30 ? `${message.slice(0, 30)}…` : message;
    session.title = session.legacyMessageCount ? `2030 arşivi · ${title}` : title;
    session.updated = Date.now(); persist();
    if (index === 0) chatLog.replaceChildren();
    addMessage("user", message); renderSessions();
  }
  clearError(); input.value = ""; $("#char-count").textContent = "0 / 2000";
  const controller = new AbortController();
  const request = { controller, sessionId: session.id, kind: "chat", placeholder: addMessage("assistant", "") };
  activeRequest = request; setBusy(true);
  try {
    const reply = await streamReply(message, history, era, controller.signal, (text) => {
      if (activeRequest === request) { request.placeholder.paragraph.textContent = text; chatLog.scrollTop = chatLog.scrollHeight; }
    });
    if (activeRequest !== request) return;
    if (!reply.trim()) throw new Error("Boş yanıt alındı. Tekrar dene.");
    session.messages.push({ role: "assistant", content: reply, time: timeLabel() });
    session.updated = Date.now(); persist();
    splitLongAnswer(request.placeholder.paragraph, reply);
    announcement.textContent = `${era === "2058" ? "FutureChat2058" : "RetroChat98"} yanıtı tamamlandı.`;
  } catch (error) {
    if (activeRequest !== request) return;
    request.placeholder.article.remove(); failedIndex = index;
    $("#chat-error-text").textContent = error.name === "AbortError" ? "Yanıt durduruldu." : error.message;
    chatError.hidden = false; statusText.textContent = "Yanıt alınamadı";
  } finally {
    if (activeRequest === request) { activeRequest = null; setBusy(false); input.focus(); }
  }
}

$("#chat-form").addEventListener("submit", (event) => {
  event.preventDefault(); const message = input.value.trim(); if (message) runChat(message);
});
$("#retry-button").addEventListener("click", () => {
  if (failedIndex === null) return;
  const message = currentSession().messages[failedIndex];
  if (message?.role === "user") { sendEvent("retry"); runChat(message.content, failedIndex); }
});
cancelButton.addEventListener("click", () => activeRequest?.controller.abort());
$("#era-toggle").addEventListener("click", () => {
  cancelActive();
  const nextEra = era === "1998" ? "2058" : "1998", existing = sessions.find((item) => item.era === nextEra);
  if (existing) { activeId = existing.id; era = nextEra; render(); } else newSession(nextEra);
  announcement.textContent = `${nextEra} dönemine geçildi. ${eraContent[nextEra].disclaimer}`; input.focus();
});
$("#new-chat").addEventListener("click", () => { cancelActive(); newSession(); input.focus(); });
$("#session-search").addEventListener("input", renderSessions);
$("#text-size").addEventListener("change", (event) => {
  preferences.textSize = event.target.value; savePreferences();
});
$("#motion-setting").addEventListener("change", (event) => {
  preferences.motion = event.target.value; savePreferences();
});
$("#split-answers").addEventListener("change", (event) => {
  preferences.splitAnswers = event.target.checked; savePreferences();
  if (!activeRequest) render();
});
$("#delete-chat").addEventListener("click", () => {
  cancelActive(); sessions = sessions.filter((item) => item.id !== activeId);
  const existing = sessions.find((item) => item.era === era);
  if (existing) { activeId = existing.id; persist(); render(); } else newSession();
  announcement.textContent = "Sohbet silindi.";
});
document.querySelectorAll(".prompt-chip").forEach((button) => button.addEventListener("click", () => {
  input.value = button.dataset.prompt; $("#char-count").textContent = `${input.value.length} / 2000`; input.focus();
}));
input.addEventListener("input", () => { $("#char-count").textContent = `${input.value.length} / 2000`; });
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); $("#chat-form").requestSubmit(); }
});

$("#compare-toggle").addEventListener("click", () => {
  comparePanel.hidden = !comparePanel.hidden;
  $("#compare-toggle").setAttribute("aria-expanded", String(!comparePanel.hidden));
  if (!comparePanel.hidden) $("#compare-input").focus();
});
$("#compare-close").addEventListener("click", () => {
  if (activeRequest?.kind === "compare") cancelActive();
  comparePanel.hidden = true; $("#compare-toggle").setAttribute("aria-expanded", "false"); $("#compare-toggle").focus();
});
$("#compare-cancel").addEventListener("click", () => activeRequest?.controller.abort());
document.querySelectorAll(".topic-chip").forEach((button) => button.addEventListener("click", () => {
  $("#compare-input").value = button.dataset.question;
  $("#compare-input").focus();
}));
function comparisonText() {
  if (!completedComparison) return "";
  const { question, retro, future } = completedComparison;
  return `RetroChat 98 / FutureChat 2058\nSoru: ${question}\n\n1998 / RETROCHAT\n${retro}\n\n2058 / FUTURECHAT (gelecek kurgusu)\n${future}\n\n2058 yanıtı yaratıcı bir gelecek kurgusudur; doğrulanmış bir öngörü değildir.`;
}
function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob), link = document.createElement("a");
  link.href = url; link.download = filename; document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$("#export-json").addEventListener("click", () => {
  downloadBlob(new Blob([JSON.stringify(sessions, null, 2)], { type: "application/json;charset=utf-8" }), "retrochat-sohbetler.json");
});
$("#export-text").addEventListener("click", () => {
  const text = sessions.map((session) => [
    `${session.era} · ${session.title}`,
    ...session.messages.map((message) => `${message.role === "user" ? "Sen" : "Sohbet botu"}: ${message.content}`)
  ].join("\n\n")).join("\n\n---\n\n");
  downloadBlob(new Blob([text], { type: "text/plain;charset=utf-8" }), "retrochat-sohbetler.txt");
});
async function copyComparison() {
  try { await navigator.clipboard.writeText(comparisonText()); $("#share-status").textContent = "Karşılaştırma kopyalandı."; }
  catch { $("#share-status").textContent = "Kopyalanamadı. Metin indir seçeneğini kullan."; }
}
$("#share-comparison").addEventListener("click", async () => {
  if (!completedComparison) return;
  if (!navigator.share) { await copyComparison(); return; }
  try {
    await navigator.share({ title: "RetroChat karşılaştırması", text: comparisonText() });
    $("#share-status").textContent = "Paylaşım açıldı.";
  } catch (error) {
    if (error.name !== "AbortError") await copyComparison();
  }
});
$("#copy-comparison").addEventListener("click", () => { if (completedComparison) copyComparison(); });
$("#download-text").addEventListener("click", () => {
  if (completedComparison) downloadBlob(new Blob([comparisonText()], { type: "text/plain;charset=utf-8" }), "retrochat-karsilastirma.txt");
});
$("#download-image").addEventListener("click", () => {
  if (!completedComparison) return;
  const canvas = document.createElement("canvas"), context = canvas.getContext("2d");
  const width = 1080, inset = 64, maxWidth = width - inset * 2;
  context.font = "24px Arial";
  const lines = [];
  for (const paragraph of comparisonText().split("\n")) {
    let line = "";
    for (const word of paragraph.split(/\s+/)) {
      const next = line ? `${line} ${word}` : word;
      if (context.measureText(next).width > maxWidth && line) { lines.push(line); line = word; }
      else line = next;
    }
    lines.push(line);
  }
  canvas.width = width; canvas.height = Math.max(480, inset * 2 + lines.length * 38);
  context.fillStyle = "#101525"; context.fillRect(0, 0, canvas.width, canvas.height);
  context.font = "24px Arial"; context.fillStyle = "#f2f7ff";
  lines.forEach((line, index) => context.fillText(line, inset, inset + 26 + index * 38));
  canvas.toBlob((blob) => {
    if (blob) downloadBlob(blob, "retrochat-karsilastirma.png");
    else $("#share-status").textContent = "Görsel oluşturulamadı.";
  }, "image/png");
});
$("#capsule-open").addEventListener("click", async () => {
  if (!completedComparison || activeRequest) return;
  const { question, retro, future } = completedComparison;
  const message = `Bu karşılaştırma için 1998'den 2058'e uzanan üç dönüm noktası anlat. Yılları sırala. 2058 kısmı açıkça yaratıcı kurgu olsun; doğrulanmış tarih veya öngörü gibi sunma. Kısa ve anlaşılır yaz.\nSoru: ${question.slice(0, 500)}\n1998 yanıtı: ${retro.slice(0, 400)}\n2058 yanıtı: ${future.slice(0, 400)}`;
  const controller = new AbortController(), request = { controller, kind: "compare" };
  activeRequest = request; setBusy(true, "compare");
  $("#capsule-result").hidden = false; $("#capsule-error").hidden = true;
  $("#capsule-text").textContent = "Dönüm noktaları hazırlanıyor...";
  try {
    const reply = await streamReply(message, [], "2058", controller.signal, (value) => {
      if (activeRequest === request) $("#capsule-text").textContent = value;
    });
    if (activeRequest === request) {
      if (!reply.trim()) throw new Error("Boş yanıt alındı. Tekrar dene.");
      $("#capsule-text").textContent = reply;
      announcement.textContent = "Zaman kapsülü hazır.";
    }
  } catch (error) {
    if (activeRequest === request) {
      $("#capsule-result").hidden = true;
      $("#capsule-error").textContent = error.name === "AbortError" ? "Zaman kapsülü durduruldu." : error.message;
      $("#capsule-error").hidden = false;
    }
  } finally { if (activeRequest === request) { activeRequest = null; setBusy(false); } }
});
const compareForm = $("#compare-form");
compareForm.addEventListener("submit", async (event) => {
  event.preventDefault(); const question = $("#compare-input").value.trim();
  if (!question || activeRequest) return;
  sendEvent("comparison_started");
  completedComparison = null; $("#share-actions").hidden = true; $("#share-status").textContent = "";
  $("#capsule-panel").hidden = true; $("#capsule-result").hidden = true;
  $("#compare-error").hidden = true; compareResults.hidden = false;
  $("#compare-1998").textContent = "Yanıt bekleniyor..."; $("#compare-2058").textContent = "Yanıt bekleniyor...";
  const controller = new AbortController(), request = { controller, kind: "compare" };
  activeRequest = request; setBusy(true, "compare");
  try {
    await Promise.all(["1998", "2058"].map(async (selectedEra) => {
      const target = $(`#compare-${selectedEra}`);
      const reply = await streamReply(question, [], selectedEra, controller.signal, (text) => {
        if (activeRequest === request) target.textContent = text;
      });
      if (activeRequest === request) target.textContent = reply;
    }));
    if (activeRequest === request) {
      completedComparison = { question, retro: $("#compare-1998").textContent, future: $("#compare-2058").textContent };
      $("#share-actions").hidden = false;
      $("#capsule-panel").hidden = false;
      announcement.textContent = "İki dönemin yanıtı hazır.";
    }
  } catch (error) {
    if (activeRequest === request) {
      controller.abort(); $("#compare-error").textContent = error.name === "AbortError" ? "Karşılaştırma durduruldu." : error.message;
      $("#compare-error").hidden = false;
      for (const selectedEra of ["1998", "2058"]) {
        const target = $(`#compare-${selectedEra}`);
        if (target.textContent === "Yanıt bekleniyor...") target.textContent = error.name === "AbortError" ? "Karşılaştırma durduruldu." : "Yanıt alınamadı.";
      }
    }
  } finally { if (activeRequest === request) { activeRequest = null; setBusy(false); } }
});

applyPreferences();
if (!activeId) newSession(); else render();
sendEvent("page_view");
