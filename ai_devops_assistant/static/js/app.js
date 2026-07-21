/**
 * Chat UI wiring: sessions sidebar, streaming, tool chips, theme.
 */

import { streamPost } from "./sse.js";
import { createToolChip, el, renderMarkdown, resolveToolChip } from "./render.js";

const SESSIONS_KEY = "ai-devops-sessions";
const THEME_KEY = "ai-devops-theme";

const state = {
  sessionId: null,
  sessions: [],
  streaming: false,
  controller: null,
  csrfToken: null,
};

const dom = {};

function readCookie(name) {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

// ---------------------------------------------------------------------------
// Session bootstrap
// ---------------------------------------------------------------------------

/**
 * Trade an API key for a session cookie.
 *
 * The page cannot hold the key itself — anything JavaScript can read, an XSS on
 * this page can exfiltrate — so /auth/session swaps it for an HttpOnly cookie
 * and returns only the CSRF token, which is meant to be readable.
 *
 * With no API key configured the server is in local demo mode and issues a
 * session to anyone, so the same call covers both deployments.
 *
 * @returns {Promise<boolean>} whether a session was established
 */
async function requestSession(apiKey) {
  try {
    const resp = await fetch("/auth/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKey ?? null }),
      credentials: "same-origin",
    });
    if (!resp.ok) return false;
    const data = await resp.json();
    state.csrfToken = data.csrf_token ?? readCookie("ai_devops_csrf");
    return true;
  } catch {
    return false;
  }
}

/** Ask for an API key and keep asking until one is accepted. */
function showLogin(message) {
  const existing = document.getElementById("login-overlay");
  if (existing) {
    if (message) existing.querySelector(".login-error").textContent = message;
    return;
  }

  const overlay = el("div", "login-overlay");
  overlay.id = "login-overlay";
  const card = el("div", "login-card");
  card.appendChild(el("h2", "login-title", "API key required"));
  card.appendChild(
    el("p", "login-hint", "This deployment is protected. Enter its API key to continue."),
  );

  const input = document.createElement("input");
  input.type = "password";
  input.className = "login-input";
  input.id = "login-key";
  input.placeholder = "API key";
  input.autocomplete = "off";
  card.appendChild(input);

  const error = el("div", "login-error", message ?? "");
  card.appendChild(error);

  const submit = el("button", "login-submit", "Continue");
  submit.type = "button";
  submit.id = "login-submit";
  const attempt = async () => {
    submit.disabled = true;
    const ok = await requestSession(input.value.trim());
    submit.disabled = false;
    if (ok) {
      overlay.remove();
      loadModels();
    } else {
      error.textContent = "That key was not accepted.";
      input.select();
    }
  };
  submit.addEventListener("click", attempt);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") attempt();
  });
  card.appendChild(submit);

  overlay.appendChild(card);
  document.body.appendChild(overlay);
  input.focus();
}

// ---------------------------------------------------------------------------
// Sessions
// ---------------------------------------------------------------------------

function loadSessions() {
  try {
    state.sessions = JSON.parse(localStorage.getItem(SESSIONS_KEY) ?? "[]");
  } catch {
    state.sessions = [];
  }
}

function saveSessions() {
  try {
    localStorage.setItem(SESSIONS_KEY, JSON.stringify(state.sessions.slice(0, 50)));
  } catch {
    /* storage full or disabled; the sidebar is a convenience, not the record */
  }
}

function upsertSession(id, title) {
  const existing = state.sessions.find((s) => s.id === id);
  if (existing) {
    if (title) existing.title = title;
  } else {
    state.sessions.unshift({ id, title: title || "New chat" });
  }
  saveSessions();
  renderSessions();
}

function renderSessions() {
  dom.sessionList.replaceChildren();
  for (const session of state.sessions) {
    const item = el("button", "session-item", session.title);
    item.type = "button";
    if (session.id === state.sessionId) item.classList.add("active");
    item.addEventListener("click", () => selectSession(session.id));
    dom.sessionList.appendChild(item);
  }
}

async function selectSession(id) {
  state.sessionId = id;
  renderSessions();
  dom.messages.replaceChildren();

  try {
    const resp = await fetch(`/chat/sessions/${encodeURIComponent(id)}`, {
      credentials: "same-origin",
    });
    if (!resp.ok) return;
    const data = await resp.json();
    for (const message of data.messages ?? []) {
      addMessage(message.role, message.content);
    }
  } catch {
    /* history is best-effort; an empty pane is better than an error wall */
  }
}

function newSession() {
  state.sessionId = crypto.randomUUID();
  dom.messages.replaceChildren();
  renderSessions();
  dom.input.focus();
}

// ---------------------------------------------------------------------------
// Messages
// ---------------------------------------------------------------------------

function addMessage(role, text) {
  const row = el("div", `message ${role}`);
  row.appendChild(el("div", "message-role", role === "user" ? "You" : "Assistant"));
  const body = el("div", "message-body");
  if (role === "user") {
    // User input is shown verbatim; it is not markdown and should not be
    // reinterpreted as any.
    body.textContent = text;
  } else {
    renderMarkdown(body, text);
  }
  row.appendChild(body);
  dom.messages.appendChild(row);
  scrollToBottom();
  return { row, body };
}

function scrollToBottom() {
  dom.messages.scrollTop = dom.messages.scrollHeight;
}

function setStreaming(active) {
  state.streaming = active;
  dom.send.hidden = active;
  dom.stop.hidden = !active;
  dom.input.disabled = false; // let the user type the next message while it streams
}

// ---------------------------------------------------------------------------
// Sending
// ---------------------------------------------------------------------------

async function send() {
  const message = dom.input.value.trim();
  if (message === "" || state.streaming) return;

  if (!state.sessionId) state.sessionId = crypto.randomUUID();
  upsertSession(state.sessionId, message.slice(0, 40));

  addMessage("user", message);
  dom.input.value = "";
  autosize();

  const { row, body } = addMessage("assistant", "");
  const chips = new Map();
  let answer = "";
  const cursor = el("span", "cursor");
  body.appendChild(cursor);

  state.controller = new AbortController();
  setStreaming(true);

  const setStatus = (text) => {
    let status = row.querySelector(".status-line");
    if (!status) {
      status = el("div", "status-line");
      row.insertBefore(status, body);
    }
    status.textContent = text;
  };

  try {
    await streamPost(
      "/chat/stream",
      { message, session_id: state.sessionId, model: dom.model.value || null },
      (frame) => {
        const { event, data } = frame;
        if (event === "status") {
          setStatus(`${data.phase?.replace(/_/g, " ") ?? "working"}…`);
        } else if (event === "tool_start") {
          const chip = createToolChip(data.name, data.params);
          chips.set(data.id, chip);
          row.insertBefore(chip, body);
          scrollToBottom();
        } else if (event === "tool_end") {
          const chip = chips.get(data.id);
          if (chip) {
            resolveToolChip(chip, {
              ok: data.ok,
              durationMs: data.duration_ms,
              summary: data.summary,
              error: data.error,
            });
          }
        } else if (event === "token") {
          answer += data.t ?? "";
          renderMarkdown(body, answer);
          body.appendChild(cursor);
          scrollToBottom();
        } else if (event === "done") {
          answer = data.message ?? answer;
          renderMarkdown(body, answer);
          row.querySelector(".status-line")?.remove();
          if (data.session_id) state.sessionId = data.session_id;
        } else if (event === "error") {
          setStatus("");
          body.appendChild(el("div", "error-box", data.message ?? "Something went wrong"));
        }
      },
      { signal: state.controller.signal, csrfToken: state.csrfToken },
    );
  } catch (err) {
    if (err.name === "AbortError") {
      /* the user pressed Stop; the partial answer stays on screen */
    } else if (err.status === 401 || err.status === 403) {
      // The session expired or was never valid. Re-authenticating is the
      // actionable response; "Connection failed: 401" is not.
      showLogin("Your session expired. Enter the API key to continue.");
    } else {
      body.appendChild(el("div", "error-box", `Connection failed: ${err.message}`));
    }
  } finally {
    cursor.remove();
    row.querySelector(".status-line")?.remove();
    setStreaming(false);
    state.controller = null;
    addMessageActions(row, () => answer);
  }
}

function stop() {
  state.controller?.abort();
}

function addMessageActions(row, getText) {
  if (row.querySelector(".message-actions")) return;
  const actions = el("div", "message-actions");

  const copy = el("button", "action", "Copy");
  copy.type = "button";
  copy.addEventListener("click", async () => {
    await navigator.clipboard.writeText(getText());
    copy.textContent = "Copied";
    setTimeout(() => {
      copy.textContent = "Copy";
    }, 1500);
  });
  actions.appendChild(copy);

  row.appendChild(actions);
}

// ---------------------------------------------------------------------------
// Input and theme
// ---------------------------------------------------------------------------

function autosize() {
  dom.input.style.height = "auto";
  dom.input.style.height = `${Math.min(dom.input.scrollHeight, 200)}px`;
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* non-fatal */
  }
}

async function loadModels() {
  try {
    const resp = await fetch("/models", { credentials: "same-origin" });
    if (resp.status === 401 || resp.status === 403) {
      // First contact with a protected deployment. This is the only place the
      // page learns it needs credentials, since nothing is exchanged up front.
      showLogin();
      return;
    }
    if (!resp.ok) return;
    const data = await resp.json();
    dom.model.replaceChildren();
    for (const name of data.models ?? []) {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      dom.model.appendChild(option);
    }
  } catch {
    /* the picker is optional; a missing list must not block chatting */
  }
}

async function uploadDocument(file) {
  const body = new FormData();
  body.append("file", file);
  const headers = state.csrfToken ? { "X-CSRF-Token": state.csrfToken } : {};
  const resp = await fetch("/rag/ingest", {
    method: "POST",
    body,
    headers,
    credentials: "same-origin",
  });
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({}));
    throw new Error(detail.detail || `upload failed: ${resp.status}`);
  }
  return resp.json();
}

function init() {
  dom.messages = document.getElementById("messages");
  dom.input = document.getElementById("input");
  dom.send = document.getElementById("send");
  dom.stop = document.getElementById("stop");
  dom.sessionList = document.getElementById("session-list");
  dom.newChat = document.getElementById("new-chat");
  dom.themeToggle = document.getElementById("theme-toggle");
  dom.model = document.getElementById("model");
  dom.upload = document.getElementById("upload");
  dom.file = document.getElementById("file");

  state.csrfToken = readCookie("ai_devops_csrf");

  const stored = localStorage.getItem(THEME_KEY);
  applyTheme(stored ?? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));

  dom.send.addEventListener("click", send);
  dom.stop.addEventListener("click", stop);
  dom.newChat.addEventListener("click", newSession);
  dom.themeToggle.addEventListener("click", () => {
    applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  });

  dom.upload.addEventListener("click", () => dom.file.click());
  dom.file.addEventListener("change", async () => {
    const file = dom.file.files[0];
    if (!file) return;
    const { row, body } = addMessage("assistant", "");
    body.textContent = `Ingesting ${file.name}…`;
    try {
      const result = await uploadDocument(file);
      body.textContent = `Added ${file.name} to the knowledge base (${result.chunks} chunks).`;
    } catch (err) {
      body.replaceChildren(el("div", "error-box", err.message));
    }
    // Reset so selecting the same file again re-triggers change.
    dom.file.value = "";
    scrollToBottom();
    void row;
  });

  dom.input.addEventListener("input", autosize);
  dom.input.addEventListener("keydown", (event) => {
    // Enter sends, Shift+Enter inserts a newline.
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      send();
    }
  });

  loadSessions();
  renderSessions();
  newSession();

  // Authenticate lazily: load models, and only deal with credentials if the
  // server actually refuses. Calling /auth/session on every page load instead
  // would spend the brute-force budget (10/minute per IP) on visitors who need
  // no session at all — ten reloads, or a few colleagues behind one NAT
  // address, and the UI locks itself out.
  void loadModels();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
