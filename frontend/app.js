const state = {
  meta: null,
  assets: [],
  bullets: [],
  styles: ["auto"],
  currentBatchId: null,
  pollTimer: null,
};

const $ = (sel) => document.querySelector(sel);

function showToast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => t.classList.add("hidden"), 2800);
}

async function api(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    let errText = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      errText = j.detail || JSON.stringify(j);
    } catch (_) {}
    throw new Error(errText);
  }
  return res.json();
}

document.querySelectorAll(".nav-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    const target = btn.dataset.tab;
    $(`#tab-${target}`).classList.add("active");
    if (target === "history") loadHistory();
    if (target === "fonts") loadFonts();
    if (target === "preferences") loadPreferences();
  });
});

async function init() {
  state.meta = await api("/api/meta");
  const proj = await api("/api/project");
  populateProjectForm(proj);
  renderStyleChips();
  renderFontCategorySelect();
  await loadAssets();
}

function populateProjectForm(proj) {
  const p = proj.property_info || {};
  $("#prop-price").value = p.price || "";
  $("#prop-location").value = p.location || "";
  $("#prop-land").value = p.land_area || "";
  $("#prop-building").value = p.building_area || "";
  $("#prop-other").value = p.other_info || "";
  $("#appeal-free-text").value = proj.appeal_free_text || "";
  $("#duration-mode").value = proj.duration_mode || "auto";
  $("#writing-mode").value = proj.writing_mode || "auto";
  state.bullets = Array.isArray(proj.appeal_bullets) ? [...proj.appeal_bullets] : [];
  state.styles = Array.isArray(proj.styles) && proj.styles.length ? [...proj.styles] : ["auto"];
  renderBullets();
}

function collectProjectPayload() {
  return {
    property_info: {
      price: $("#prop-price").value.trim(),
      location: $("#prop-location").value.trim(),
      land_area: $("#prop-land").value.trim(),
      building_area: $("#prop-building").value.trim(),
      other_info: $("#prop-other").value.trim(),
    },
    appeal_bullets: state.bullets.map((b) => b.trim()).filter(Boolean),
    appeal_free_text: $("#appeal-free-text").value,
    styles: state.styles.length ? state.styles : ["auto"],
    duration_mode: $("#duration-mode").value,
    writing_mode: $("#writing-mode").value,
  };
}

let saveProjectTimer = null;
function scheduleSaveProject() {
  clearTimeout(saveProjectTimer);
  saveProjectTimer = setTimeout(async () => {
    try {
      await api("/api/project", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(collectProjectPayload()),
      });
    } catch (_) {}
  }, 500);
}

["#prop-price", "#prop-location", "#prop-land", "#prop-building", "#prop-other", "#appeal-free-text", "#duration-mode", "#writing-mode"]
  .forEach((sel) => $(sel).addEventListener("input", scheduleSaveProject));

function renderBullets() {
  const list = $("#bullet-list");
  list.innerHTML = "";
  state.bullets.forEach((txt, idx) => {
    const row = document.createElement("div");
    row.className = "bullet-row";
    row.innerHTML = `
      <input type="text" value="${escapeHtml(txt)}" />
      <button class="btn btn-sm" title="上へ">↑</button>
      <button class="btn btn-sm" title="下へ">↓</button>
      <button class="btn btn-sm btn-danger" title="削除">×</button>
    `;
    const inp = row.querySelector("input");
    inp.addEventListener("input", () => {
      state.bullets[idx] = inp.value;
      scheduleSaveProject();
    });
    const btns = row.querySelectorAll("button");
    btns[0].addEventListener("click", () => {
      if (idx > 0) {
        [state.bullets[idx - 1], state.bullets[idx]] = [state.bullets[idx], state.bullets[idx - 1]];
        renderBullets();
        scheduleSaveProject();
      }
    });
    btns[1].addEventListener("click", () => {
      if (idx < state.bullets.length - 1) {
        [state.bullets[idx + 1], state.bullets[idx]] = [state.bullets[idx], state.bullets[idx + 1]];
        renderBullets();
        scheduleSaveProject();
      }
    });
    btns[2].addEventListener("click", () => {
      state.bullets.splice(idx, 1);
      renderBullets();
      scheduleSaveProject();
    });
    list.appendChild(row);
  });
}

$("#add-bullet-btn").addEventListener("click", () => {
  const v = $("#new-bullet-input").value.trim();
  if (!v) return;
  state.bullets.push(v);
  $("#new-bullet-input").value = "";
  renderBullets();
  scheduleSaveProject();
});

$("#new-bullet-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    $("#add-bullet-btn").click();
  }
});

function renderStyleChips() {
  const box = $("#style-chips");
  box.innerHTML = "";
  state.meta.styles.forEach((st) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip" + (state.styles.includes(st.id) ? " active" : "");
    chip.textContent = st.label;
    chip.addEventListener("click", () => {
      if (st.id === "auto") {
        state.styles = ["auto"];
      } else {
        state.styles = state.styles.filter((s) => s !== "auto");
        if (state.styles.includes(st.id)) {
          state.styles = state.styles.filter((s) => s !== st.id);
        } else {
          state.styles.push(st.id);
        }
        if (state.styles.length === 0) state.styles = ["auto"];
      }
      renderStyleChips();
      scheduleSaveProject();
    });
    box.appendChild(chip);
  });
}

const dropzone = $("#dropzone");
const fileInput = $("#asset-file-input");

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropzone.classList.add("dragover");
});
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
dropzone.addEventListener("drop", async (e) => {
  e.preventDefault();
  dropzone.classList.remove("dragover");
  if (e.dataTransfer.files.length) await uploadFiles(e.dataTransfer.files);
});
fileInput.addEventListener("change", async () => {
  if (fileInput.files.length) {
    await uploadFiles(fileInput.files);
    fileInput.value = "";
  }
});

async function uploadFiles(fileList) {
  const fd = new FormData();
  for (const f of fileList) fd.append("files", f);
  try {
    showToast("素材をアップロード中...");
    await api("/api/assets/upload", { method: "POST", body: fd });
    await loadAssets();
    showToast("素材を追加しました");
  } catch (err) {
    showToast(`アップロードエラー: ${err.message}`);
  }
}

async function loadAssets() {
  const res = await api("/api/assets");
  state.assets = res.assets;
  renderAssets();
}

function renderAssets() {
  const list = $("#asset-list");
  list.innerHTML = "";
  if (!state.assets.length) {
    list.innerHTML = `<div class="hint" style="text-align:center;padding:8px;">素材がまだありません</div>`;
    return;
  }
  state.assets.forEach((a, idx) => {
    const row = document.createElement("div");
    row.className = "asset-item";
    const metaText = a.media_type === "video"
      ? `動画 ${a.duration}s (${a.width}x${a.height})`
      : `静止画 (${a.width}x${a.height})`;
    row.innerHTML = `
      <input type="checkbox" ${a.selected ? "checked" : ""} title="使用ON/OFF" />
      <img class="asset-thumb" src="${a.thumb_url}" alt="" />
      <div class="asset-info">
        <div class="asset-name">${escapeHtml(a.original_name)}</div>
        <div class="asset-meta">${metaText}</div>
      </div>
      <div class="asset-actions">
        <button class="btn btn-sm" title="上へ">↑</button>
        <button class="btn btn-sm" title="下へ">↓</button>
        <button class="btn btn-sm btn-danger" title="削除">×</button>
      </div>
    `;
    const chk = row.querySelector('input[type="checkbox"]');
    chk.addEventListener("change", async () => {
      await api(`/api/assets/${a.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ selected: chk.checked }),
      });
      a.selected = chk.checked ? 1 : 0;
    });
    const btns = row.querySelectorAll("button");
    btns[0].addEventListener("click", () => moveAsset(idx, -1));
    btns[1].addEventListener("click", () => moveAsset(idx, 1));
    btns[2].addEventListener("click", async () => {
      await api(`/api/assets/${a.id}`, { method: "DELETE" });
      await loadAssets();
    });
    list.appendChild(row);
  });
}

async function moveAsset(idx, delta) {
  const target = idx + delta;
  if (target < 0 || target >= state.assets.length) return;
  const ids = state.assets.map((a) => a.id);
  [ids[idx], ids[target]] = [ids[target], ids[idx]];
  const res = await api("/api/assets/reorder", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ordered_ids: ids }),
  });
  state.assets = res.assets;
  renderAssets();
}

async function startGeneration() {
  const errBox = $("#error-banner");
  errBox.classList.add("hidden");

  try {
    $("#generate-btn").disabled = true;
    $("#regenerate-btn").disabled = true;
    const res = await api("/api/batches/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project: collectProjectPayload(), count: 40 }),
    });
    state.currentBatchId = res.batch_id;
    $("#progress-wrap").classList.remove("hidden");
    $("#progress-fill").style.width = "0%";
    $("#progress-count").textContent = "0 / 40";
    $("#video-grid").innerHTML = "";
    pollBatch(res.batch_id);
  } catch (err) {
    errBox.textContent = err.message;
    errBox.classList.remove("hidden");
    $("#generate-btn").disabled = false;
  }
}

$("#generate-btn").addEventListener("click", startGeneration);
$("#regenerate-btn").addEventListener("click", startGeneration);

function pollBatch(batchId) {
  clearInterval(state.pollTimer);
  const fetchOnce = async () => {
    try {
      const b = await api(`/api/batches/${batchId}`);
      $("#batch-status-text").textContent = b.current_message;
      const pct = Math.round((b.completed_count / b.total_count) * 100);
      $("#progress-fill").style.width = `${pct}%`;
      $("#progress-count").textContent = `${b.completed_count} / ${b.total_count}`;
      renderVideoGrid($("#video-grid"), b.videos);

      if (b.status === "completed" || b.status === "error") {
        clearInterval(state.pollTimer);
        $("#generate-btn").disabled = false;
        $("#regenerate-btn").disabled = false;
        $("#play-all-btn").disabled = b.videos.length === 0;
        $("#pause-all-btn").disabled = b.videos.length === 0;
        if (b.status === "error") {
          $("#error-banner").textContent = b.error_message || b.current_message;
          $("#error-banner").classList.remove("hidden");
        }
      }
    } catch (err) {
      clearInterval(state.pollTimer);
      $("#generate-btn").disabled = false;
    }
  };
  fetchOnce();
  state.pollTimer = setInterval(fetchOnce, 900);
}

$("#play-all-btn").addEventListener("click", () => {
  document.querySelectorAll("#video-grid video").forEach((v) => {
    v.currentTime = 0;
    v.play().catch(() => {});
  });
});
$("#pause-all-btn").addEventListener("click", () => {
  document.querySelectorAll("#video-grid video").forEach((v) => v.pause());
});

function renderVideoGrid(container, videos) {
  const existingIds = new Set([...container.querySelectorAll(".video-card")].map((el) => el.dataset.vid));
  videos.forEach((v) => {
    if (existingIds.has(v.id)) return;
    const card = buildVideoCard(v);
    container.appendChild(card);
  });
}

function buildVideoCard(v) {
  const dna = v.dna || {};
  const card = document.createElement("div");
  card.className = "video-card" + (v.is_favorite ? " fav" : "") + (v.is_disliked ? " disliked" : "");
  card.dataset.vid = v.id;

  if (v.status === "error") {
    card.innerHTML = `<div class="video-body"><strong>#${v.index_in_batch} 生成エラー</strong><pre class="hint">${escapeHtml(v.error_message)}</pre></div>`;
    return card;
  }

  card.innerHTML = `
    <div class="video-stage">
      <video src="${v.video_url}" poster="${v.thumb_url}" controls loop playsinline preload="metadata"></video>
      <div class="video-badge-top">
        <span class="pill">#${v.index_in_batch} ${escapeHtml(dna.primary_style_label || "")}</span>
        <span class="pill">冒頭${v.hook_duration}s / 全${v.duration}s</span>
      </div>
    </div>
    <div class="video-body">
      <div class="dna-tags">
        <span class="dna-tag">${escapeHtml(dna.font_name || "")}</span>
        ${dna.writing_label ? `<span class="dna-tag">${escapeHtml(dna.writing_label)}</span>` : ""}
        <span class="dna-tag">${escapeHtml(dna.hook_animation_label || "")}</span>
        <span class="dna-tag">${escapeHtml(dna.telop_label || dna.palette_name || "")}</span>
        <span class="dna-tag">${escapeHtml(dna.decoration_label || "")}</span>
      </div>
      <div class="card-controls">
        <a class="btn btn-primary btn-sm" href="${v.download_url}" download>MP4ダウンロード</a>
        <button class="btn btn-sm js-fav">${v.is_favorite ? "★ お気に入り済" : "☆ お気に入り"}</button>
        <button class="btn btn-sm btn-danger js-dislike">嫌い</button>
      </div>
      <div class="eval-box">
        <span class="hint">要素別の評価・学習:</span>
        <div class="eval-row">
          <button class="btn btn-sm js-eval" data-act="boost_style">この系統をもっと</button>
          <button class="btn btn-sm js-eval" data-act="like_font">フォント👍</button>
          <button class="btn btn-sm js-eval" data-act="like_animation">アニメ👍</button>
        </div>
        <div class="eval-row">
          <button class="btn btn-sm btn-danger js-eval" data-act="block_font">このフォントNG</button>
          <button class="btn btn-sm btn-danger js-eval" data-act="block_animation">このアニメNG</button>
          <button class="btn btn-sm btn-danger js-eval" data-act="block_palette">この配色NG</button>
          <button class="btn btn-sm btn-danger js-eval" data-act="block_combo">この組合せNG</button>
        </div>
      </div>
    </div>
  `;

  card.querySelector(".js-fav").addEventListener("click", async (e) => {
    const res = await api(`/api/videos/${v.id}/evaluate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "favorite" }),
    });
    const fav = res.video.is_favorite === 1;
    card.classList.toggle("fav", fav);
    card.classList.remove("disliked");
    e.target.textContent = fav ? "★ お気に入り済" : "☆ お気に入り";
    showToast(res.message);
  });

  card.querySelector(".js-dislike").addEventListener("click", async () => {
    const res = await api(`/api/videos/${v.id}/evaluate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "dislike_design" }),
    });
    card.classList.add("disliked");
    card.classList.remove("fav");
    showToast(res.message);
  });

  card.querySelectorAll(".js-eval").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const act = btn.dataset.act;
      const res = await api(`/api/videos/${v.id}/evaluate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: act }),
      });
      showToast(res.message);
    });
  });

  return card;
}

$("#history-fav-only").addEventListener("change", loadHistory);

async function loadHistory() {
  const favOnly = $("#history-fav-only").checked;
  const res = await api(`/api/history?only_favorites=${favOnly}`);
  const box = $("#history-container");
  box.innerHTML = "";
  if (!res.batches.length) {
    box.innerHTML = `<div class="card hint">履歴がありません。</div>`;
    return;
  }
  res.batches.forEach((b) => {
    const sec = document.createElement("div");
    sec.className = "history-batch";
    sec.innerHTML = `
      <div class="history-batch-head">
        <strong>生成日時: ${b.created_at}（${b.videos.length}件）</strong>
        <span class="hint">系統: ${(b.styles || []).join(", ")}</span>
      </div>
      <div class="video-grid"></div>
    `;
    const grid = sec.querySelector(".video-grid");
    b.videos.forEach((v) => grid.appendChild(buildVideoCard(v)));
    box.appendChild(sec);
  });
}

function renderFontCategorySelect() {
  const sel = $("#font-upload-cat");
  sel.innerHTML = "";
  state.meta.font_categories.forEach((c) => {
    const opt = document.createElement("option");
    opt.value = c.id;
    opt.textContent = c.label;
    sel.appendChild(opt);
  });
}

$("#font-upload-btn").addEventListener("click", async () => {
  const inp = $("#font-file-input");
  if (!inp.files.length) {
    showToast("フォントファイルを選択してください");
    return;
  }
  const fd = new FormData();
  fd.append("file", inp.files[0]);
  fd.append("category", $("#font-upload-cat").value);
  fd.append("license_type", $("#font-upload-license").value);
  fd.append("commercial_ok", $("#font-upload-comm").checked);
  try {
    await api("/api/fonts/upload", { method: "POST", body: fd });
    inp.value = "";
    showToast("フォントを追加しました");
    await loadFonts();
  } catch (err) {
    showToast(`追加失敗: ${err.message}`);
  }
});

async function loadFonts() {
  const res = await api("/api/fonts");
  const list = $("#font-list");
  list.innerHTML = "";
  res.fonts.forEach((f) => {
    const row = document.createElement("div");
    row.className = "font-row";
    const catOpts = state.meta.font_categories
      .map((c) => `<option value="${c.id}" ${c.id === f.category ? "selected" : ""}>${c.label}</option>`)
      .join("");
    row.innerHTML = `
      <div>
        <strong>${escapeHtml(f.display_name)}</strong>
        <div class="hint">${f.source === "custom" ? "ローカル追加" : "Windows標準"}</div>
      </div>
      <img class="font-preview-img" loading="lazy" src="/api/fonts/${f.id}/preview?t=${Date.now()}" alt="preview" />
      <select class="js-cat">${catOpts}</select>
      <div>
        <input type="text" class="js-lic" value="${escapeHtml(f.license_type)}" style="width:100%;font-size:11px;" />
        <label class="inline-check mt-sm"><input type="checkbox" class="js-comm" ${f.commercial_ok ? "checked" : ""} /> 商用利用可</label>
      </div>
      <div style="display:flex;gap:8px;align-items:center;">
        <label class="inline-check"><input type="checkbox" class="js-en" ${f.enabled ? "checked" : ""} /> 使用</label>
        ${f.source === "custom" ? `<button class="btn btn-sm btn-danger js-del">削除</button>` : ""}
      </div>
    `;

    const saveMeta = async (patch) => {
      await api(`/api/fonts/${f.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      showToast("フォント設定を保存しました");
    };
    row.querySelector(".js-cat").addEventListener("change", (e) => saveMeta({ category: e.target.value }));
    row.querySelector(".js-lic").addEventListener("change", (e) => saveMeta({ license_type: e.target.value }));
    row.querySelector(".js-comm").addEventListener("change", (e) => saveMeta({ commercial_ok: e.target.checked }));
    row.querySelector(".js-en").addEventListener("change", (e) => saveMeta({ enabled: e.target.checked }));
    const delBtn = row.querySelector(".js-del");
    if (delBtn) {
      delBtn.addEventListener("click", async () => {
        await api(`/api/fonts/${f.id}`, { method: "DELETE" });
        await loadFonts();
        showToast("フォントを削除しました");
      });
    }
    list.appendChild(row);
  });
}

async function loadPreferences() {
  const res = await api("/api/preferences");
  const blk = $("#blocked-list");
  blk.innerHTML = res.blocked_items.length ? "" : `<div class="hint">NG登録された要素はありません。</div>`;
  res.blocked_items.forEach((item) => {
    const el = document.createElement("div");
    el.className = "pref-item";
    el.innerHTML = `<span>[${escapeHtml(item.item_type)}] ${escapeHtml(item.label || item.item_value)}</span><button class="btn btn-sm">解除</button>`;
    el.querySelector("button").addEventListener("click", async () => {
      await api(`/api/preferences/blocked/${item.id}`, { method: "DELETE" });
      await loadPreferences();
      showToast("NG登録を解除しました");
    });
    blk.appendChild(el);
  });

  const wgt = $("#weights-list");
  wgt.innerHTML = res.weights.length ? "" : `<div class="hint">まだ学習スコアが蓄積されていません。</div>`;
  res.weights.forEach((w) => {
    const el = document.createElement("div");
    el.className = "pref-item";
    el.innerHTML = `<span>[${escapeHtml(w.item_type)}] ${escapeHtml(w.item_value)}</span><strong>スコア: ${Number(w.score).toFixed(2)}</strong>`;
    wgt.appendChild(el);
  });
}

function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

init();