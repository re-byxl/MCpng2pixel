/* Litematic 方向转换工具 —— 前端逻辑 */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const state = {
  settings: null,
  files: [],
  blocks: [],
  selected: new Set(),
  activeFile: null,
  target: "keep",
  rotation: 0,
  jobTimer: null,
};

/* ------------------------------------------------------------------ */
/* 基础工具                                                            */
/* ------------------------------------------------------------------ */

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const text = await res.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch (err) {
    throw new Error(`服务器返回异常：${text.slice(0, 200)}`);
  }
  if (!res.ok) throw new Error(data.error || `请求失败 (${res.status})`);
  return data;
}

function post(path, payload) {
  return api(path, { method: "POST", body: JSON.stringify(payload || {}) });
}

function log(message, keep = false) {
  const el = $("#log");
  if (!keep) el.textContent = "";
  el.textContent += (el.textContent ? "\n" : "") + message;
  el.scrollTop = el.scrollHeight;
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/* ------------------------------------------------------------------ */
/* 状态与设置                                                          */
/* ------------------------------------------------------------------ */

async function loadState() {
  const data = await api("/api/state");
  state.settings = data.settings;
  state.files = data.files;
  state.blocks = data.blocks || [];

  $("#input-dir").value = data.input_dir;
  $("#output-dir").value = data.output_dir;
  $("#suffix").value = data.settings.suffix ?? "_transformed";
  $("#overwrite").checked = !!data.settings.overwrite;
  $("#keep-props").checked = !!data.settings.keep_properties;

  applyPlanToUI(data.settings.plan || {});
  renderRules(data.settings.replacements || {});
  renderFiles();

  if (state.files.length) {
    const first = state.files[0].name;
    state.selected.add(first);
    state.activeFile = first;
    renderFiles();
    refreshPreview();
  } else {
    $("#preview-name").textContent = "未选择文件";
    $("#preview-info").textContent = "";
  }
}

function collectPlan() {
  return {
    source_normal: $("#source-normal").value,
    target_normal: state.target,
    rotation: state.rotation,
    mirror_h: $("#mirror-h").checked,
    mirror_v: $("#mirror-v").checked,
    rotate_x: parseInt($("#rotate-x").value, 10) || 0,
    rotate_y: parseInt($("#rotate-y").value, 10) || 0,
    rotate_z: parseInt($("#rotate-z").value, 10) || 0,
  };
}

function applyPlanToUI(plan) {
  if (plan.source_normal) $("#source-normal").value = plan.source_normal;
  state.target = plan.target_normal || "keep";
  state.rotation = plan.rotation || 0;
  $("#mirror-h").checked = !!plan.mirror_h;
  $("#mirror-v").checked = !!plan.mirror_v;
  $("#rotate-x").value = String(plan.rotate_x || 0);
  $("#rotate-y").value = String(plan.rotate_y || 0);
  $("#rotate-z").value = String(plan.rotate_z || 0);
  syncPresetButtons();
}

function syncPresetButtons() {
  $$(".preset[data-target]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.target === state.target);
  });
  $$(".preset[data-rot]").forEach((btn) => {
    btn.classList.toggle("active", parseInt(btn.dataset.rot, 10) === state.rotation);
  });
}

/* ------------------------------------------------------------------ */
/* 文件列表                                                            */
/* ------------------------------------------------------------------ */

function renderFiles() {
  const list = $("#file-list");
  list.innerHTML = "";
  $("#file-count").textContent = state.files.length;
  $("#file-empty").style.display = state.files.length ? "none" : "block";

  state.files.forEach((file) => {
    const li = document.createElement("li");
    li.className = "file-item" + (state.activeFile === file.name ? " active" : "");

    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = state.selected.has(file.name);
    box.addEventListener("click", (ev) => ev.stopPropagation());
    box.addEventListener("change", () => {
      if (box.checked) state.selected.add(file.name);
      else state.selected.delete(file.name);
    });

    const main = document.createElement("div");
    main.className = "file-main";

    const name = document.createElement("span");
    name.className = "file-name";
    name.textContent = file.name;
    name.title = file.name;

    const meta = document.createElement("span");
    meta.className = "file-meta";
    if (file.error) {
      meta.innerHTML = `<span class="warn">读取失败：${escapeHtml(file.error)}</span>`;
    } else {
      const dims = file.dims || [0, 0, 0];
      const plane = file.normal ? planeLabel(file.normal) : "?";
      meta.innerHTML =
        `<span class="axis-tag">${plane}</span>` +
        `${dims[0]}×${dims[1]}×${dims[2]} · ${file.blocks ?? 0} 方块 · ${formatSize(file.size)}`;
    }

    main.append(name, meta);
    li.append(box, main);
    li.addEventListener("click", () => {
      state.activeFile = file.name;
      renderFiles();
      refreshPreview();
    });
    list.appendChild(li);
  });
}

function planeLabel(axis) {
  return { x: "YZ 侧", y: "XZ 地", z: "XY 墙" }[axis] || axis;
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"]/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;",
  })[c]);
}

/* ------------------------------------------------------------------ */
/* 预览                                                                */
/* ------------------------------------------------------------------ */

let previewTimer = null;

function refreshPreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(async () => {
    if (!state.activeFile) return;
    try {
      const data = await post("/api/preview", {
        file: state.activeFile,
        input_dir: $("#input-dir").value.trim(),
        plan: collectPlan(),
        replacements: collectRules(),
      });
      $("#preview-name").textContent = state.activeFile;
      $("#preview-info").textContent = describePreview(data);
      drawPreview($("#canvas-before"), data.before);
      drawPreview($("#canvas-after"), data.after);
    } catch (err) {
      $("#preview-info").textContent = `预览失败：${err.message}`;
    }
  }, 120);
}

function describePreview(data) {
  const before = data.dims_before || [];
  const after = data.dims_after || [];
  const axis = { x: "YZ 侧面", y: "XZ 地面", z: "XY 立面" };
  const to = axis[data.after?.normal] || "";
  return (
    `${before[0]}×${before[1]}×${before[2]}` +
    `  →  ${after[0]}×${after[1]}×${after[2]}（${to}）`
  );
}

function drawPreview(canvas, data) {
  const ctx = canvas.getContext("2d");
  const cols = data?.cols || 0;
  const rows = data?.rows || 0;
  canvas.width = Math.max(cols, 1);
  canvas.height = Math.max(rows, 1);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!cols || !rows) return;

  const colors = data.colors || [];
  const grid = data.grid || [];
  for (let row = 0; row < rows; row++) {
    for (let col = 0; col < cols; col++) {
      const idx = grid[row * cols + col];
      if (idx === undefined || idx < 0) continue;
      const rgb = colors[idx] || [90, 90, 90];
      ctx.fillStyle = `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
      ctx.fillRect(col, row, 1, 1);
    }
  }
}

/* ------------------------------------------------------------------ */
/* 替换规则                                                            */
/* ------------------------------------------------------------------ */

function renderRules(rules) {
  const list = $("#rule-list");
  list.innerHTML = "";
  Object.entries(rules || {}).forEach(([from, to]) => addRuleRow(from, to));
  if (!list.children.length) addRuleRow("", "");
}

function addRuleRow(from = "", to = "") {
  const list = $("#rule-list");
  const row = document.createElement("div");
  row.className = "rule";

  const inputFrom = document.createElement("input");
  inputFrom.type = "text";
  inputFrom.value = from;
  inputFrom.placeholder = "red_concrete";
  inputFrom.setAttribute("list", "block-list");

  const inputTo = document.createElement("input");
  inputTo.type = "text";
  inputTo.value = to;
  inputTo.placeholder = "red_terracotta";
  inputTo.setAttribute("list", "block-list");

  const del = document.createElement("button");
  del.className = "rule-del";
  del.textContent = "×";
  del.title = "删除这条规则";
  del.addEventListener("click", () => {
    row.remove();
    if (!list.children.length) addRuleRow("", "");
  });

  row.append(inputFrom, inputTo, del);
  list.appendChild(row);
}

function collectRules() {
  const rules = {};
  $$("#rule-list .rule").forEach((row) => {
    const [inputFrom, inputTo] = row.querySelectorAll("input");
    const from = inputFrom.value.trim();
    if (!from) return;
    rules[from] = inputTo.value.trim();
  });
  return rules;
}

function fillBlockList() {
  if ($("#block-list")) return;
  const list = document.createElement("datalist");
  list.id = "block-list";
  state.blocks.forEach((name) => {
    const opt = document.createElement("option");
    opt.value = name;
    list.appendChild(opt);
  });
  document.body.appendChild(list);
}

/* ------------------------------------------------------------------ */
/* 操作                                                                */
/* ------------------------------------------------------------------ */

async function saveSettings() {
  const payload = {
    ...state.settings,
    input_dir: $("#input-dir").value.trim(),
    output_dir: $("#output-dir").value.trim(),
    suffix: $("#suffix").value.trim(),
    overwrite: $("#overwrite").checked,
    keep_properties: $("#keep-props").checked,
    plan: collectPlan(),
    replacements: collectRules(),
  };
  try {
    const data = await post("/api/settings", payload);
    state.settings = data.settings;
    log("设置已保存到 config.json 的 tool 节");
  } catch (err) {
    log(`保存失败：${err.message}`);
  }
}

async function browse(targetId) {
  const start = $(targetId).value.trim();
  try {
    const data = await post("/api/browse", { start });
    if (data.path) $(targetId).value = data.path;
  } catch (err) {
    log(`选择文件夹失败：${err.message}`);
  }
}

async function openFolder(path) {
  try {
    await post("/api/open_folder", { path });
  } catch (err) {
    log(`打开文件夹失败：${err.message}`);
  }
}

async function runTransform() {
  const files = Array.from(state.selected);
  if (!files.length) {
    log("请先在左侧勾选要处理的文件。");
    return;
  }

  const btn = $("#btn-run");
  btn.disabled = true;
  log(`开始处理 ${files.length} 个文件…`);

  try {
    const data = await post("/api/transform", {
      files,
      plan: collectPlan(),
      replacements: collectRules(),
      keep_properties: $("#keep-props").checked,
      suffix: $("#suffix").value.trim(),
      overwrite: $("#overwrite").checked,
      input_dir: $("#input-dir").value.trim(),
      output_dir: $("#output-dir").value.trim(),
    });
    pollJob(data.job);
  } catch (err) {
    log(`处理失败：${err.message}`);
    btn.disabled = false;
  }
}

function pollJob(jobId) {
  clearInterval(state.jobTimer);
  state.jobTimer = setInterval(async () => {
    try {
      const job = await api(`/api/job?id=${jobId}`);
      log(job.log.join("\n"), true);
      if (job.status !== "running") {
        clearInterval(state.jobTimer);
        $("#btn-run").disabled = false;
      }
    } catch (err) {
      clearInterval(state.jobTimer);
      $("#btn-run").disabled = false;
      log(`读取进度失败：${err.message}`);
    }
  }, 400);
}

/* ------------------------------------------------------------------ */
/* 事件绑定                                                            */
/* ------------------------------------------------------------------ */

function bind() {
  $("#btn-save").addEventListener("click", saveSettings);
  $("#btn-run").addEventListener("click", runTransform);

  $("#btn-refresh").addEventListener("click", async () => {
    await saveSettings();
    await loadState();
    log("已刷新文件列表");
  });

  $("#btn-select-all").addEventListener("click", () => {
    state.files.forEach((f) => state.selected.add(f.name));
    renderFiles();
  });
  $("#btn-select-none").addEventListener("click", () => {
    state.selected.clear();
    renderFiles();
  });

  $("#btn-browse-in").addEventListener("click", () => browse("#input-dir"));
  $("#btn-browse-out").addEventListener("click", () => browse("#output-dir"));
  $("#btn-open-in").addEventListener("click", () => openFolder($("#input-dir").value.trim()));
  $("#btn-open-out").addEventListener("click", () => openFolder($("#output-dir").value.trim()));

  $("#source-normal").addEventListener("change", refreshPreview);
  $("#mirror-h").addEventListener("change", refreshPreview);
  $("#mirror-v").addEventListener("change", refreshPreview);
  ["#rotate-x", "#rotate-y", "#rotate-z"].forEach((sel) => {
    $(sel).addEventListener("change", refreshPreview);
  });

  $$(".preset[data-target]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.target = btn.dataset.target;
      syncPresetButtons();
      refreshPreview();
    });
  });
  $$(".preset[data-rot]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.rotation = parseInt(btn.dataset.rot, 10);
      syncPresetButtons();
      refreshPreview();
    });
  });

  $("#btn-add-rule").addEventListener("click", () => addRuleRow("", ""));
  $("#btn-clear-rules").addEventListener("click", () => {
    $("#rule-list").innerHTML = "";
    addRuleRow("", "");
  });
}

(async function main() {
  bind();
  try {
    await loadState();
    fillBlockList();
    applyUrlOverrides();
    log("就绪。左侧勾选文件，右侧调整方向与替换规则，然后点「开始处理」。");
  } catch (err) {
    log(`初始化失败：${err.message}`);
  }
})();

/* 用网址参数覆盖设置，例如 ?target=y&rotation=90&mirror_h=1 */
function applyUrlOverrides() {
  const params = new URLSearchParams(location.search);
  if (!params.size) return;

  const plan = collectPlan();
  if (params.has("target")) plan.target_normal = params.get("target");
  if (params.has("source")) plan.source_normal = params.get("source");
  if (params.has("rotation")) plan.rotation = parseInt(params.get("rotation"), 10) || 0;
  if (params.has("rotate_x")) plan.rotate_x = parseInt(params.get("rotate_x"), 10) || 0;
  if (params.has("rotate_y")) plan.rotate_y = parseInt(params.get("rotate_y"), 10) || 0;
  if (params.has("rotate_z")) plan.rotate_z = parseInt(params.get("rotate_z"), 10) || 0;
  if (params.has("mirror_h")) plan.mirror_h = params.get("mirror_h") !== "0";
  if (params.has("mirror_v")) plan.mirror_v = params.get("mirror_v") !== "0";
  if (params.has("file")) {
    const name = params.get("file");
    if (state.files.some((f) => f.name === name)) {
      state.activeFile = name;
      state.selected.add(name);
    }
  }

  applyPlanToUI(plan);
  renderFiles();
  refreshPreview();
}
