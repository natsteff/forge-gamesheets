"use strict";

(() => {
  const root = document.querySelector("[data-designer-app]");
  if (!root) return;

  const $ = (name) => root.querySelector(`[data-${name}]`);
  const escape = (value) => String(value).replace(/[&<>"]/g, (character) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"})[character]);
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const id = (prefix) => `${prefix}-${crypto.randomUUID()}`;
  const blockName = {header: "Header", score_table: "Score table", reference: "Reference", checklist: "Checklist", notes: "Notes"};
  const history = [];
  const future = [];
  let model = null;
  let selected = null;
  let saveTimer = null;
  let lastSaved = null;

  const locate = () => {
    for (const [rowIndex, row] of model.rows.entries()) {
      const blockIndex = row.blocks.findIndex((block) => block.id === selected);
      if (blockIndex >= 0) return {row, rowIndex, block: row.blocks[blockIndex], blockIndex};
    }
    return null;
  };

  function commit(change) {
    history.push(clone(model));
    if (history.length > 50) history.shift();
    future.length = 0;
    change(model);
    render();
    queueSave();
  }

  function queueSave() {
    clearTimeout(saveTimer);
    $("save-status").textContent = "Unsaved changes";
    saveTimer = setTimeout(save, 350);
  }

  async function flushSave() {
    if (!saveTimer) return true;
    clearTimeout(saveTimer);
    saveTimer = null;
    return save();
  }

  async function save() {
    saveTimer = null;
    try {
      const response = await fetch("/sheet-designer/document", {
        method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(model)
      });
      if (!response.ok) throw new Error((await response.json()).detail || "The draft could not be saved.");
      const saved = await response.json();
      lastSaved = clone(saved);
      localStorage.setItem("forge-sheet-designer-draft", JSON.stringify(saved));
      $("save-status").textContent = "✓ Saved";
      message("");
      return true;
    } catch (error) {
      if (lastSaved) model = clone(lastSaved);
      $("save-status").textContent = "Save failed";
      message(error.message);
      render();
      return false;
    }
  }

  function message(text, kind = "general") {
    $("message").hidden = !text;
    $("message").textContent = text;
    $("message").dataset.kind = text ? kind : "";
  }

  function moveRow(from, to) {
    if (to < 0 || to >= model.rows.length || from === to) return;
    commit((draft) => draft.rows.splice(to, 0, draft.rows.splice(from, 1)[0]));
  }

  function structure() {
    const sectionCount = model.rows.reduce((count, row) => count + row.blocks.length, 0);
    $("section-count").textContent = `${sectionCount} section${sectionCount === 1 ? "" : "s"}`;
    $("structure-list").innerHTML = model.rows.map((row, rowIndex) => row.blocks.map((block) => `
      <div class="designer-structure-item${selected === block.id ? " is-selected" : ""}" draggable="true" data-block-id="${block.id}" data-row-index="${rowIndex}">
        <button type="button" class="designer-section-select" data-select="${block.id}">
          <span aria-hidden="true">⠿</span><span>${escape(block.title || blockName[block.type])}</span>
        </button>
        <span class="designer-mini-actions">
          <button type="button" data-up="${rowIndex}" aria-label="Move ${escape(block.title)} up">↑</button>
          <button type="button" data-down="${rowIndex}" aria-label="Move ${escape(block.title)} down">↓</button>
        </span>
      </div>`).join("")).join("");
    root.querySelectorAll("[data-select]").forEach((button) => button.addEventListener("click", () => { selected = button.dataset.select; render(); }));
    root.querySelectorAll("[data-up]").forEach((button) => button.addEventListener("click", () => moveRow(Number(button.dataset.up), Number(button.dataset.up) - 1)));
    root.querySelectorAll("[data-down]").forEach((button) => button.addEventListener("click", () => moveRow(Number(button.dataset.down), Number(button.dataset.down) + 1)));
    root.querySelectorAll("[draggable=true]").forEach((item) => {
      item.addEventListener("dragstart", (event) => event.dataTransfer.setData("text/plain", item.dataset.rowIndex));
      item.addEventListener("dragover", (event) => event.preventDefault());
      item.addEventListener("drop", (event) => { event.preventDefault(); moveRow(Number(event.dataTransfer.getData("text/plain")), Number(item.dataset.rowIndex)); });
    });
  }

  function previewBlock(block) {
    if (block.type === "header") return `<section class="preview-header"><h2>${escape(block.title)}</h2><p>${escape(block.subtitle)}</p></section>`;
    if (block.type === "score_table") {
      const heads = block.players.map((player, index) => `<th>${escape(player || `Player ${index + 1}`)}</th>`).join("");
      const rows = block.score_rows.map((label) => `<tr><th>${escape(label)}</th>${block.players.map(() => "<td></td>").join("")}</tr>`).join("");
      const total = block.show_total ? `<tr class="total"><th>${escape(block.total_label)}</th>${block.players.map(() => "<td></td>").join("")}</tr>` : "";
      return `<section><h3>${escape(block.title)}</h3><table><thead><tr><th>Category</th>${heads}</tr></thead><tbody>${rows}${total}</tbody></table></section>`;
    }
    if (block.type === "notes") return `<section><h3>${escape(block.title)}</h3><div class="preview-note-lines">${Array.from({length: block.lines}, () => "<i></i>").join("")}</div></section>`;
    const items = block.items.map((item) => block.type === "checklist" ? `<li>□ ${escape(item)}</li>` : `<li>${escape(item)}</li>`).join("");
    return `<section><h3>${escape(block.title)}</h3><ul class="${block.type}">${items}</ul></section>`;
  }

  function preview() {
    const page = $("sheet-preview");
    page.className = `sheet-preview page-${model.page.size} page-${model.page.orientation}`;
    page.innerHTML = model.rows.map((row) => `<div class="preview-row columns-${row.blocks.length}">${row.blocks.map(previewBlock).join("")}</div>`).join("");
    requestAnimationFrame(() => {
      if (page.scrollHeight > page.clientHeight + 2) message("This content does not fit on one page. Remove content or use landscape orientation.", "overflow");
      else if ($("message").dataset.kind === "overflow") message("");
    });
  }

  const textList = (label, items, key) => `<label>${label}<textarea data-list="${key}" rows="${Math.min(12, Math.max(4, items.length))}">${escape(items.join("\n"))}</textarea></label>`;
  function properties() {
    const found = locate();
    if (!found) { $("properties-title").textContent = "Section"; $("properties-panel").innerHTML = "<p>Select a section to edit it.</p>"; return; }
    const {block, row, rowIndex, blockIndex} = found;
    $("properties-title").textContent = blockName[block.type];
    let fields = `<label>Heading<input data-field="title" maxlength="160" value="${escape(block.title)}"></label>`;
    if (block.type === "header") fields += `<label>Subtitle<input data-field="subtitle" maxlength="240" value="${escape(block.subtitle)}"></label>`;
    if (block.type === "score_table") fields += `<label>Players<input data-player-count type="number" min="1" max="12" value="${block.players.length}"></label>${textList("Player headings (one per line)", block.players, "players")}${textList("Score rows (one per line)", block.score_rows, "score_rows")}<p class="designer-field-help">Press Return to add a row. Delete a line to remove that row.</p><fieldset class="designer-row-generator"><legend>Generate numbered rows</legend><label>Label<input data-row-prefix maxlength="60" value="Round"></label><div><label>Start<input data-row-start type="number" min="-999" max="999" value="1"></label><label>Number of rows<input data-row-count type="number" min="1" max="30" value="10"></label></div><button class="secondary-button" data-generate-rows type="button">Generate rows</button></fieldset><label class="designer-check"><input data-total type="checkbox"${block.show_total ? " checked" : ""}> Include a summary row</label>${block.show_total ? `<label>Summary row label<input data-field="total_label" maxlength="80" value="${escape(block.total_label)}"></label>` : ""}`;
    if (block.type === "reference" || block.type === "checklist") fields += `${textList(`${block.type === "checklist" ? "Checklist items" : "Reminders"} (one per line)`, block.items, "items")}<p class="designer-field-help">Each line appears as a separate ${block.type === "checklist" ? "checkbox" : "reminder"}.</p>`;
    if (block.type === "notes") fields += `<label>Writing lines<input data-field="lines" type="number" min="1" max="20" value="${block.lines}"></label>`;
    fields += `<div class="designer-property-actions"><button class="secondary-button" data-duplicate type="button">Duplicate</button>${row.blocks.length === 1 && rowIndex < model.rows.length - 1 && model.rows[rowIndex + 1].blocks.length === 1 ? '<button class="secondary-button" data-pair type="button">Pair with next</button>' : ""}${row.blocks.length === 2 ? '<button class="secondary-button" data-unpair type="button">Use full width</button>' : ""}${model.rows.length === 1 && row.blocks.length === 1 ? "" : '<button class="danger-button" data-delete type="button">Delete</button>'}</div>`;
    $("properties-panel").innerHTML = fields;
    root.querySelectorAll("[data-field]").forEach((input) => input.addEventListener("change", () => commit(() => { block[input.dataset.field] = input.type === "number" ? Number(input.value) : input.value; })));
    root.querySelectorAll("[data-list]").forEach((input) => {
      if (input.dataset.list === "score_rows" || input.dataset.list === "items") return;
      input.addEventListener("change", () => commit(() => { block[input.dataset.list] = input.value.split("\n").map((item) => item.trim()).filter(Boolean); }));
    });
    const scoreRows = root.querySelector('[data-list="score_rows"]');
    if (scoreRows) {
      let beforeEdit = null;
      scoreRows.addEventListener("focus", () => { beforeEdit = clone(model); }, {once: true});
      scoreRows.addEventListener("input", () => {
        const rows = scoreRows.value.split("\n").map((item) => item.trim()).filter(Boolean);
        if (!rows.length) {
          message("A score table needs at least one row.");
          return;
        }
        if (rows.length > 30) {
          message("A score table may contain at most 30 rows.");
          return;
        }
        block.score_rows = rows;
        message("");
        preview();
        queueSave();
      });
      scoreRows.addEventListener("blur", () => {
        const count = scoreRows.value.split("\n").map((item) => item.trim()).filter(Boolean).length;
        if (!count || count > 30) {
          render();
          return;
        }
        if (!beforeEdit || JSON.stringify(beforeEdit) === JSON.stringify(model)) return;
        history.push(beforeEdit);
        if (history.length > 50) history.shift();
        future.length = 0;
        render();
      });
    }
    const itemList = root.querySelector('[data-list="items"]');
    if (itemList) {
      let beforeEdit = null;
      itemList.addEventListener("focus", () => { beforeEdit = clone(model); }, {once: true});
      itemList.addEventListener("input", () => {
        const items = itemList.value.split("\n").map((item) => item.trim()).filter(Boolean);
        if (!items.length) {
          message(`A ${blockName[block.type].toLowerCase()} section needs at least one item.`);
          return;
        }
        if (items.length > 30) {
          message("A section may contain at most 30 items.");
          return;
        }
        block.items = items;
        message("");
        preview();
        queueSave();
      });
      itemList.addEventListener("blur", () => {
        const count = itemList.value.split("\n").map((item) => item.trim()).filter(Boolean).length;
        if (!count || count > 30) {
          render();
          return;
        }
        if (!beforeEdit || JSON.stringify(beforeEdit) === JSON.stringify(model)) return;
        history.push(beforeEdit);
        if (history.length > 50) history.shift();
        future.length = 0;
        render();
      });
    }
    const count = root.querySelector("[data-player-count]");
    if (count) count.addEventListener("change", () => commit(() => { const wanted = Math.max(1, Math.min(12, Number(count.value))); block.players = Array.from({length: wanted}, (_, index) => block.players[index] || `Player ${index + 1}`); }));
    const total = root.querySelector("[data-total]");
    if (total) total.addEventListener("change", () => commit(() => { block.show_total = total.checked; }));
    const generateRows = root.querySelector("[data-generate-rows]");
    if (generateRows) generateRows.addEventListener("click", () => {
      const prefix = root.querySelector("[data-row-prefix]").value.trim();
      const start = Number(root.querySelector("[data-row-start]").value);
      const count = Number(root.querySelector("[data-row-count]").value);
      if (!prefix) {
        message("Enter a label for the numbered rows.");
        return;
      }
      if (!Number.isInteger(start) || start < -999 || start > 999 || !Number.isInteger(count) || count < 1 || count > 30) {
        message("Choose a whole-number start and generate between 1 and 30 rows.");
        return;
      }
      if (block.score_rows.length && !confirm(`Replace the existing ${block.score_rows.length} score row${block.score_rows.length === 1 ? "" : "s"}?`)) return;
      commit(() => { block.score_rows = Array.from({length: count}, (_, index) => `${prefix} ${start + index}`); });
    });
    root.querySelector("[data-duplicate]").addEventListener("click", () => commit((draft) => { const copy = clone(block); copy.id = id(block.type); copy.title = `${copy.title} copy`; draft.rows.splice(rowIndex + 1, 0, {id: id("row"), blocks: [copy]}); selected = copy.id; }));
    root.querySelector("[data-delete]")?.addEventListener("click", () => commit((draft) => { row.blocks.splice(blockIndex, 1); if (!row.blocks.length) draft.rows.splice(rowIndex, 1); selected = draft.rows[0]?.blocks[0]?.id || null; }));
    root.querySelector("[data-pair]")?.addEventListener("click", () => commit((draft) => { row.blocks.push(draft.rows[rowIndex + 1].blocks[0]); draft.rows.splice(rowIndex + 1, 1); }));
    root.querySelector("[data-unpair]")?.addEventListener("click", () => commit((draft) => { const moved = row.blocks.splice(blockIndex, 1)[0]; draft.rows.splice(rowIndex + 1, 0, {id: id("row"), blocks: [moved]}); }));
  }

  function render() {
    $("document-title").value = model.title;
    $("page-size").value = model.page.size;
    $("orientation").value = model.page.orientation;
    $("undo").disabled = !history.length;
    $("redo").disabled = !future.length;
    structure(); preview(); properties();
  }

  function activateDocument(document) {
    clearTimeout(saveTimer);
    saveTimer = null;
    model = document;
    lastSaved = clone(document);
    selected = model.rows[0].blocks[0].id;
    history.length = 0;
    future.length = 0;
    localStorage.setItem("forge-sheet-designer-draft", JSON.stringify(model));
    $("save-status").textContent = "✓ Saved";
    message("");
    render();
  }

  async function requestDocument(url, options = {}) {
    const response = await fetch(url, options);
    if (!response.ok) throw new Error((await response.json()).detail || "The sheet operation failed.");
    return response.json();
  }

  async function showSheetLibrary() {
    if (!await flushSave()) return;
    try {
      const workspace = await requestDocument("/sheet-designer/documents");
      $("sheet-list").innerHTML = workspace.documents.map((document) => `
        <article class="designer-sheet-item${document.id === workspace.current_id ? " is-current" : ""}">
          <button class="designer-sheet-open" type="button" data-open-id="${document.id}"><strong>${escape(document.title)}</strong><span>${document.id === workspace.current_id ? "Currently open" : "Open sheet"}</span></button>
          <button class="secondary-button" type="button" data-duplicate-id="${document.id}">Duplicate</button>
          <button class="danger-button" type="button" data-delete-id="${document.id}">Delete</button>
        </article>`).join("");
      root.querySelectorAll("[data-open-id]").forEach((button) => button.addEventListener("click", async () => {
        try {
          activateDocument(await requestDocument(`/sheet-designer/documents/${button.dataset.openId}/open`, {method: "POST"}));
          $("open-dialog").close();
        } catch (error) { message(error.message); }
      }));
      root.querySelectorAll("[data-duplicate-id]").forEach((button) => button.addEventListener("click", async () => {
        try {
          activateDocument(await requestDocument(`/sheet-designer/documents/${button.dataset.duplicateId}/duplicate`, {method: "POST"}));
          $("open-dialog").close();
        } catch (error) { message(error.message); }
      }));
      root.querySelectorAll("[data-delete-id]").forEach((button) => button.addEventListener("click", async () => {
        const item = button.closest(".designer-sheet-item");
        const title = item.querySelector("strong").textContent;
        if (!confirm(`Delete “${title}”? This cannot be undone.`)) return;
        try {
          activateDocument(await requestDocument(`/sheet-designer/documents/${button.dataset.deleteId}`, {method: "DELETE"}));
          $("open-dialog").close();
          await showSheetLibrary();
        } catch (error) { message(error.message); }
      }));
      $("open-dialog").showModal();
    } catch (error) { message(error.message); }
  }

  function addBlock() {
    const type = $("section-type").value;
    const templates = {
      header: {type: "header", title: "Sheet title", subtitle: ""},
      score_table: {type: "score_table", title: "Score table", players: ["Player 1", "Player 2"], score_rows: ["Round 1"], show_total: false, total_label: "Total"},
      reference: {type: "reference", title: "Reference", items: ["Helpful reminder"]},
      checklist: {type: "checklist", title: "Checklist", items: ["First objective"]},
      notes: {type: "notes", title: "Notes", lines: 5}
    };
    if (!templates[type]) return;
    commit((draft) => { const block = {...templates[type], id: id(type)}; draft.rows.push({id: id("row"), blocks: [block]}); selected = block.id; });
  }

  $("document-title").addEventListener("change", (event) => commit((draft) => { draft.title = event.target.value; }));
  $("page-size").addEventListener("change", (event) => commit((draft) => { draft.page.size = event.target.value; }));
  $("orientation").addEventListener("change", (event) => commit((draft) => { draft.page.orientation = event.target.value; }));
  $("add-block").addEventListener("click", addBlock);
  $("new-sheet").addEventListener("click", async () => {
    if (!await flushSave()) return;
    $("new-title").value = "Untitled Game Sheet";
    $("new-size").value = model.page.size;
    $("new-orientation").value = model.page.orientation;
    $("new-dialog").showModal();
    $("new-title").select();
  });
  $("open-sheets").addEventListener("click", showSheetLibrary);
  $("close-new").addEventListener("click", () => $("new-dialog").close());
  $("cancel-new").addEventListener("click", () => $("new-dialog").close());
  $("close-open").addEventListener("click", () => $("open-dialog").close());
  $("new-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const document = await requestDocument("/sheet-designer/documents", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({title: $("new-title").value, page_size: $("new-size").value, orientation: $("new-orientation").value})
      });
      activateDocument(document);
      $("new-dialog").close();
    } catch (error) { message(error.message); }
  });
  $("undo").addEventListener("click", () => { if (!history.length) return; future.push(clone(model)); model = history.pop(); render(); queueSave(); });
  $("redo").addEventListener("click", () => { if (!future.length) return; history.push(clone(model)); model = future.pop(); render(); queueSave(); });
  $("import-file").addEventListener("change", async (event) => {
    try { const imported = JSON.parse(await event.target.files[0].text()); history.push(clone(model)); model = imported; selected = model.rows[0]?.blocks[0]?.id; await save(); render(); }
    catch (error) { message(`Import failed: ${error.message}`); }
    event.target.value = "";
  });

  fetch("/sheet-designer/document").then((response) => response.json()).then((document) => {
    model = document; lastSaved = clone(document); selected = model.rows[0].blocks[0].id; render(); $("save-status").textContent = "✓ Saved";
  }).catch((error) => {
    const recovered = localStorage.getItem("forge-sheet-designer-draft");
    if (recovered) { model = JSON.parse(recovered); lastSaved = clone(model); selected = model.rows[0].blocks[0].id; render(); $("save-status").textContent = "Recovered locally"; }
    else message(`Designer failed to load: ${error.message}`);
  });
})();
