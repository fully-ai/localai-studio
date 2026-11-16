const state = {
  conversations: [],
  activeId: null,
  models: [],
  pendingAttachments: [],
  stream: true,
};

const el = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return res.json();
}

async function checkHealth() {
  const pill = el("ollama-status");
  try {
    const data = await api("/api/health");
    pill.textContent = data.ollama_reachable ? "Ollama: online" : "Ollama: offline";
    pill.className = `status-pill ${data.ollama_reachable ? "status-online" : "status-offline"}`;
  } catch {
    pill.textContent = "Ollama: error";
    pill.className = "status-pill status-offline";
  }
}

async function loadModels() {
  const select = el("model-select");
  select.innerHTML = "";
  try {
    const data = await api("/api/models");
    state.models = data.models.map((m) => m.name);
  } catch {
    state.models = [];
  }
  if (state.models.length === 0) {
    state.models = ["llama3.2"];
  }
  for (const name of state.models) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    select.appendChild(opt);
  }
}

async function loadConversations() {
  const data = await api("/api/conversations");
  state.conversations = data.conversations;
  renderConversationList();
  if (!state.activeId && state.conversations.length > 0) {
    await selectConversation(state.conversations[0].id);
  } else if (state.conversations.length === 0) {
    await createConversation();
  }
}

function renderConversationList() {
  const list = el("conversation-list");
  list.innerHTML = "";
  for (const conv of state.conversations) {
    const li = document.createElement("li");
    li.className = `conv-item ${conv.id === state.activeId ? "active" : ""}`;
    const span = document.createElement("span");
    span.textContent = conv.title;
    span.onclick = () => selectConversation(conv.id);
    const del = document.createElement("button");
    del.className = "conv-del";
    del.textContent = "×";
    del.title = "Delete conversation";
    del.onclick = async (e) => {
      e.stopPropagation();
      await api(`/api/conversations/${conv.id}`, { method: "DELETE" });
      if (state.activeId === conv.id) state.activeId = null;
      await loadConversations();
    };
    li.append(span, del);
    list.appendChild(li);
  }
}

async function createConversation() {
  const model = el("model-select").value || "llama3.2";
  const conv = await api("/api/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: "New Conversation", model }),
  });
  state.activeId = conv.id;
  await loadConversations();
  await selectConversation(conv.id);
}

async function selectConversation(id) {
  state.activeId = id;
  const conv = await api(`/api/conversations/${id}`);
  el("conv-title-input").value = conv.title;
  el("model-select").value = conv.model;
  el("system-prompt-input").value = conv.system_prompt || "";
  el("param-temp").value = conv.parameters.temperature;
  el("param-top-p").value = conv.parameters.top_p;
  el("param-top-k").value = conv.parameters.top_k;
  el("param-ctx").value = conv.parameters.num_ctx;
  renderConversationList();
  renderMessages(conv.messages || []);
}

function renderMessages(messages) {
  const container = el("chat-messages");
  container.innerHTML = "";
  for (const msg of messages) {
    appendMessageBubble(msg.role, msg.content);
  }
  container.scrollTop = container.scrollHeight;
}

function appendMessageBubble(role, content) {
  const container = el("chat-messages");
  const div = document.createElement("div");
  div.className = `msg msg-${role}`;
  const header = document.createElement("div");
  header.className = "msg-role";
  header.textContent = role;
  const body = document.createElement("div");
  body.textContent = content;
  div.append(header, body);
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return body;
}

async function saveConversationSettings() {
  if (!state.activeId) return;
  await api(`/api/conversations/${state.activeId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: el("conv-title-input").value,
      model: el("model-select").value,
      system_prompt: el("system-prompt-input").value,
      parameters: {
        temperature: parseFloat(el("param-temp").value),
        top_p: parseFloat(el("param-top-p").value),
        top_k: parseInt(el("param-top-k").value, 10),
        num_ctx: parseInt(el("param-ctx").value, 10),
        repeat_penalty: 1.1,
      },
    }),
  });
  await loadConversations();
}

async function sendMessage() {
  const input = el("prompt-input");
  const content = input.value.trim();
  if (!content || !state.activeId) return;
  input.value = "";
  appendMessageBubble("user", content);
  const assistantBody = appendMessageBubble("assistant", "");

  const attachmentIds = state.pendingAttachments.map((a) => a.id);
  state.pendingAttachments = [];
  el("attachment-bar").innerHTML = "";

  const res = await fetch(`/api/conversations/${state.activeId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, attachment_ids: attachmentIds, stream: state.stream }),
  });

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const evt = JSON.parse(line.slice(6));
      if (evt.type === "delta") {
        assistantBody.textContent += evt.content;
        el("chat-messages").scrollTop = el("chat-messages").scrollHeight;
      } else if (evt.type === "error") {
        assistantBody.textContent = `Error: ${evt.detail}`;
      }
    }
  }
}

el("new-chat-btn").onclick = createConversation;
el("toggle-settings-btn").onclick = () => el("settings-drawer").classList.toggle("hidden");
el("save-settings-btn").onclick = saveConversationSettings;
el("conv-title-input").onchange = saveConversationSettings;
el("model-select").onchange = saveConversationSettings;
el("send-btn").onclick = sendMessage;
el("prompt-input").onkeydown = (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
};
el("file-input").onchange = async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  const att = await api("/api/files", { method: "POST", body: form });
  state.pendingAttachments.push(att);
  const chip = document.createElement("span");
  chip.className = "att-chip";
  chip.textContent = `${att.filename} (${att.kind})`;
  el("attachment-bar").appendChild(chip);
  e.target.value = "";
};
el("pull-model-btn").onclick = async () => {
  const name = prompt("Enter Ollama model name to pull (e.g. llama3.2):");
  if (!name) return;
  await api("/api/models/pull", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  await loadModels();
};
el("theme-toggle-btn").onclick = async () => {
  const html = document.documentElement;
  const next = html.getAttribute("data-theme") === "dark" ? "light" : "dark";
  html.setAttribute("data-theme", next);
  await api("/api/preferences", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ theme: next }),
  });
};

(async () => {
  await checkHealth();
  await loadModels();
  const prefs = await api("/api/preferences");
  document.documentElement.setAttribute("data-theme", prefs.theme || "dark");
  await loadConversations();
})();
