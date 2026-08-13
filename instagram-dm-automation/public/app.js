// Vanilla JS admin dashboard — no framework, no build step. Talks to the
// existing REST API (/api/*) that already backs the DM + posting automation.

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (res.status === 204) return null;

  let body = null;
  try { body = await res.json(); } catch { /* empty body */ }

  if (!res.ok) {
    const message = body?.error ? JSON.stringify(body.error) : res.statusText;
    throw new Error(message);
  }
  return body;
}

let toastTimer;
function showToast(message, isError = false) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.classList.toggle("error", isError);
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 3000);
}

function statusPillClass(status) {
  if (status === "PUBLISHED" || status === "ACTIVE") return "pill-success";
  if (status === "FAILED") return "pill-danger";
  if (status === "CONTAINER_CREATED") return "pill-warning";
  return "pill-muted";
}

// ---------- Tabs ----------

function initTabs() {
  const loaders = {
    "keyword-rules": loadKeywordRules,
    "comment-rules": loadCommentRules,
    welcome: loadWelcomeMessage,
    flows: loadFlows,
    posts: loadScheduledPosts,
    logs: loadLogs,
  };

  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab;
      document.querySelectorAll(".nav-item").forEach((b) => b.setAttribute("aria-selected", String(b === btn)));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tab}`));
      loaders[tab]?.();
    });
  });

  document.getElementById("tab-keyword-rules").classList.add("active");
  loadKeywordRules();
}

// ---------- Keyword rules ----------

async function loadKeywordRules() {
  const rules = await api("/api/keyword-rules");
  const body = document.getElementById("list-keyword-rules");
  document.getElementById("empty-keyword-rules").hidden = rules.length > 0;
  body.innerHTML = rules.map((r) => `
    <tr>
      <td>${esc(r.keyword)}</td>
      <td>${esc(r.matchType)}</td>
      <td class="truncate">${esc(r.replyText)}</td>
      <td><button class="pill ${statusPillClass(r.isActive ? "ACTIVE" : "")}" data-toggle="${r.id}" data-active="${r.isActive}">${r.isActive ? "Active" : "Inactive"}</button></td>
      <td><button class="btn btn-danger btn-small" data-delete="${r.id}">Delete</button></td>
    </tr>
  `).join("");

  body.querySelectorAll("[data-toggle]").forEach((btn) => btn.addEventListener("click", async () => {
    await api(`/api/keyword-rules/${btn.dataset.toggle}`, { method: "PATCH", body: JSON.stringify({ isActive: btn.dataset.active !== "true" }) });
    loadKeywordRules();
  }));
  body.querySelectorAll("[data-delete]").forEach((btn) => btn.addEventListener("click", async () => {
    if (!confirm("Delete this rule?")) return;
    await api(`/api/keyword-rules/${btn.dataset.delete}`, { method: "DELETE" });
    showToast("Rule deleted");
    loadKeywordRules();
  }));
}

document.getElementById("form-keyword-rule").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData(e.target);
  try {
    await api("/api/keyword-rules", { method: "POST", body: JSON.stringify(Object.fromEntries(form)) });
    e.target.reset();
    showToast("Rule added");
    loadKeywordRules();
  } catch (err) { showToast(err.message, true); }
});

// ---------- Comment rules ----------

async function loadCommentRules() {
  const rules = await api("/api/comment-rules");
  const body = document.getElementById("list-comment-rules");
  document.getElementById("empty-comment-rules").hidden = rules.length > 0;
  body.innerHTML = rules.map((r) => `
    <tr>
      <td>${esc(r.keyword)}</td>
      <td>${esc(r.mediaId) || "<span class=\"pill pill-muted\">Any post</span>"}</td>
      <td class="truncate">${esc(r.dmText)}</td>
      <td><button class="pill ${statusPillClass(r.isActive ? "ACTIVE" : "")}" data-toggle="${r.id}" data-active="${r.isActive}">${r.isActive ? "Active" : "Inactive"}</button></td>
      <td><button class="btn btn-danger btn-small" data-delete="${r.id}">Delete</button></td>
    </tr>
  `).join("");

  body.querySelectorAll("[data-toggle]").forEach((btn) => btn.addEventListener("click", async () => {
    await api(`/api/comment-rules/${btn.dataset.toggle}`, { method: "PATCH", body: JSON.stringify({ isActive: btn.dataset.active !== "true" }) });
    loadCommentRules();
  }));
  body.querySelectorAll("[data-delete]").forEach((btn) => btn.addEventListener("click", async () => {
    if (!confirm("Delete this rule?")) return;
    await api(`/api/comment-rules/${btn.dataset.delete}`, { method: "DELETE" });
    showToast("Rule deleted");
    loadCommentRules();
  }));
}

document.getElementById("form-comment-rule").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = Object.fromEntries(new FormData(e.target));
  if (!form.mediaId) delete form.mediaId;
  if (!form.publicReplyText) delete form.publicReplyText;
  try {
    await api("/api/comment-rules", { method: "POST", body: JSON.stringify(form) });
    e.target.reset();
    showToast("Rule added");
    loadCommentRules();
  } catch (err) { showToast(err.message, true); }
});

// ---------- Welcome message ----------

async function loadWelcomeMessage() {
  const welcome = await api("/api/welcome-message");
  document.getElementById("wm-text").value = welcome?.text ?? "";
  document.getElementById("wm-active").checked = welcome?.isActive ?? true;
}

document.getElementById("form-welcome").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/welcome-message", {
      method: "PUT",
      body: JSON.stringify({ text: document.getElementById("wm-text").value, isActive: document.getElementById("wm-active").checked }),
    });
    showToast("Welcome message saved");
  } catch (err) { showToast(err.message, true); }
});

// ---------- Flows ----------

let stepCount = 0;

function addFlowStep() {
  const index = stepCount++;
  const container = document.getElementById("flow-steps");
  const step = document.createElement("div");
  step.className = "flow-step";
  step.dataset.step = String(index);
  step.innerHTML = `
    <div class="flow-step-head">
      <span>Step ${index}</span>
      <button type="button" class="btn btn-ghost btn-small" data-remove-step>Remove step</button>
    </div>
    <div class="field">
      <label>Message</label>
      <textarea class="step-message" rows="2" required></textarea>
    </div>
    <div class="qr-list"></div>
    <button type="button" class="btn btn-ghost btn-small" data-add-qr>+ Add quick reply</button>
  `;
  step.querySelector("[data-remove-step]").addEventListener("click", () => step.remove());
  step.querySelector("[data-add-qr]").addEventListener("click", () => addQuickReply(step));
  container.appendChild(step);
}

function addQuickReply(stepEl) {
  const row = document.createElement("div");
  row.className = "qr-row";
  row.innerHTML = `
    <input type="text" class="qr-title" placeholder="Button label" />
    <input type="number" class="qr-payload" min="0" placeholder="Next step #" />
    <button type="button" class="btn btn-ghost btn-small" data-remove-qr>✕</button>
  `;
  row.querySelector("[data-remove-qr]").addEventListener("click", () => row.remove());
  stepEl.querySelector(".qr-list").appendChild(row);
}

document.getElementById("add-step").addEventListener("click", addFlowStep);
addFlowStep(); // start every new flow form with one step

document.getElementById("form-flow").addEventListener("submit", async (e) => {
  e.preventDefault();
  const steps = Array.from(document.querySelectorAll(".flow-step")).map((stepEl, order) => {
    const quickReplies = Array.from(stepEl.querySelectorAll(".qr-row"))
      .map((row) => ({ title: row.querySelector(".qr-title").value.trim(), payload: row.querySelector(".qr-payload").value.trim() }))
      .filter((qr) => qr.title && qr.payload);
    return {
      order,
      messageText: stepEl.querySelector(".step-message").value,
      ...(quickReplies.length ? { quickReplies } : {}),
    };
  });

  try {
    await api("/api/flows", {
      method: "POST",
      body: JSON.stringify({
        name: document.getElementById("fl-name").value,
        triggerKeyword: document.getElementById("fl-trigger").value,
        triggerMatch: document.getElementById("fl-match").value,
        steps,
      }),
    });
    e.target.reset();
    document.getElementById("flow-steps").innerHTML = "";
    stepCount = 0;
    addFlowStep();
    showToast("Flow created");
    loadFlows();
  } catch (err) { showToast(err.message, true); }
});

async function loadFlows() {
  const flows = await api("/api/flows");
  const list = document.getElementById("list-flows");
  document.getElementById("empty-flows").hidden = flows.length > 0;
  list.innerHTML = flows.map((f) => `
    <div class="flow-card">
      <div>
        <h3>${esc(f.name)}</h3>
        <div class="meta">Trigger: "${esc(f.triggerKeyword)}" (${esc(f.triggerMatch)}) &middot; ${f.steps.length} step${f.steps.length === 1 ? "" : "s"}</div>
      </div>
      <div class="actions">
        <button class="pill ${statusPillClass(f.isActive ? "ACTIVE" : "")}" data-toggle="${f.id}" data-active="${f.isActive}">${f.isActive ? "Active" : "Inactive"}</button>
        <button class="btn btn-danger btn-small" data-delete="${f.id}">Delete</button>
      </div>
    </div>
  `).join("");

  list.querySelectorAll("[data-toggle]").forEach((btn) => btn.addEventListener("click", async () => {
    await api(`/api/flows/${btn.dataset.toggle}`, { method: "PATCH", body: JSON.stringify({ isActive: btn.dataset.active !== "true" }) });
    loadFlows();
  }));
  list.querySelectorAll("[data-delete]").forEach((btn) => btn.addEventListener("click", async () => {
    if (!confirm("Delete this flow?")) return;
    await api(`/api/flows/${btn.dataset.delete}`, { method: "DELETE" });
    showToast("Flow deleted");
    loadFlows();
  }));
}

// ---------- Scheduled posts ----------

async function loadScheduledPosts() {
  const posts = await api("/api/scheduled-posts");
  const body = document.getElementById("list-posts");
  document.getElementById("empty-posts").hidden = posts.length > 0;
  body.innerHTML = posts.map((p) => `
    <tr>
      <td>${esc(p.mediaType)}</td>
      <td class="truncate"><a href="${esc(p.mediaUrl)}" target="_blank" rel="noopener">${esc(p.mediaUrl)}</a></td>
      <td>${new Date(p.scheduledFor).toLocaleString()}</td>
      <td>
        <span class="pill ${statusPillClass(p.status)}">${esc(p.status)}</span>
        ${p.errorMessage ? `<div class="meta" style="color:var(--danger);font-size:12px;margin-top:4px;">${esc(p.errorMessage)}</div>` : ""}
      </td>
      <td>${p.status === "PENDING" ? `<button class="btn btn-danger btn-small" data-cancel="${p.id}">Cancel</button>` : ""}</td>
    </tr>
  `).join("");

  body.querySelectorAll("[data-cancel]").forEach((btn) => btn.addEventListener("click", async () => {
    if (!confirm("Cancel this scheduled post?")) return;
    try {
      await api(`/api/scheduled-posts/${btn.dataset.cancel}`, { method: "DELETE" });
      showToast("Post cancelled");
      loadScheduledPosts();
    } catch (err) { showToast(err.message, true); }
  }));
}

document.getElementById("form-post").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = Object.fromEntries(new FormData(e.target));
  if (!form.caption) delete form.caption;
  form.scheduledFor = new Date(form.scheduledFor).toISOString();
  try {
    await api("/api/scheduled-posts", { method: "POST", body: JSON.stringify(form) });
    e.target.reset();
    showToast("Post scheduled");
    loadScheduledPosts();
  } catch (err) { showToast(err.message, true); }
});

// ---------- Message log ----------

async function loadLogs() {
  const igUserId = document.getElementById("log-filter").value.trim();
  const query = igUserId ? `?igUserId=${encodeURIComponent(igUserId)}` : "";
  const logs = await api(`/api/message-logs${query}`);
  const body = document.getElementById("list-logs");
  document.getElementById("empty-logs").hidden = logs.length > 0;
  body.innerHTML = logs.map((l) => `
    <tr>
      <td>${new Date(l.createdAt).toLocaleString()}</td>
      <td><span class="pill ${l.direction === "outbound" ? "pill-success" : "pill-muted"}">${esc(l.direction)}</span></td>
      <td>${esc(l.igUserId)}</td>
      <td class="truncate">${esc(l.text) || "<span class=\"pill pill-muted\">—</span>"}</td>
    </tr>
  `).join("");
}

document.getElementById("refresh-logs").addEventListener("click", loadLogs);
document.getElementById("log-filter").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); loadLogs(); } });

initTabs();
