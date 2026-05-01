/**
 * WikiSuporte – Migração GoTo/Multi360
 * app.js – Lógica JavaScript da interface
 *
 * Responsabilidades:
 *  1. Gerenciar drag-and-drop e seleção de arquivo
 *  2. Validar tipo e tamanho no cliente antes do upload
 *  3. Enviar arquivo para a API (POST /importar)
 *  4. Renderizar preview da tabela
 *  5. Aplicar filtros via GET /relatorio
 *  6. Acionar downloads (CSV / XLSX / PDF) via links dinâmicos
 */

"use strict";

// ── Configuração ──────────────────────────────────────────────────────────────
const API_BASE    = window.API_BASE || "http://localhost:8000";
const MAX_BYTES   = 10 * 1024 * 1024; // 10 MB (espelhado do backend)
const ACCEPT_EXT  = ["csv", "xlsx", "zip"];
const PREVIEW_MAX = 15;

// ── Seletores DOM ─────────────────────────────────────────────────────────────
const dropZone        = document.getElementById("drop-zone");
const fileInput       = document.getElementById("file-input");
const filePreviewEl   = document.getElementById("file-preview");
const fileNameLabel   = document.getElementById("file-name-label");
const fileSizeLabel   = document.getElementById("file-size-label");
const clearFileBtn    = document.getElementById("clear-file-btn");
const uploadBtn       = document.getElementById("upload-btn");
const uploadBtnText   = document.getElementById("upload-btn-text");
const uploadSpinner   = document.getElementById("upload-spinner");
const uploadMsg       = document.getElementById("upload-msg");

const filterCard      = document.getElementById("filter-card");
const filterBtn       = document.getElementById("filter-btn");
const filterAnalista  = document.getElementById("filter-analista");
const filterPlantao   = document.getElementById("filter-plantao");
const filterDataInicio = document.getElementById("filter-data-inicio");
const filterDataFim   = document.getElementById("filter-data-fim");

const resultCard      = document.getElementById("result-card");
const resultMeta      = document.getElementById("result-meta");
const previewThead    = document.getElementById("preview-thead");
const previewTbody    = document.getElementById("preview-tbody");
const tableNote       = document.getElementById("table-note");

const dlCsv  = document.getElementById("dl-csv");
const dlXlsx = document.getElementById("dl-xlsx");
const dlPdf  = document.getElementById("dl-pdf");

// ── Estado ────────────────────────────────────────────────────────────────────
let selectedFile = null;
let lastMeta     = null;   // { tipo, total_registros, colunas }

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function getExtension(filename) {
  return filename.split(".").pop().toLowerCase();
}

function showMessage(text, type = "error") {
  uploadMsg.textContent = text;
  uploadMsg.className   = `alert alert-${type}`;
  uploadMsg.classList.remove("hidden");
}

function clearMessage() {
  uploadMsg.textContent = "";
  uploadMsg.className   = "alert hidden";
}

function setUploading(loading) {
  uploadBtn.disabled = loading;
  uploadBtnText.textContent = loading ? "Processando…" : "Enviar e Processar";
  uploadSpinner.classList.toggle("hidden", !loading);
}

// ─────────────────────────────────────────────────────────────────────────────
// Seleção / validação de arquivo
// ─────────────────────────────────────────────────────────────────────────────

function validateFile(file) {
  const ext = getExtension(file.name);
  if (!ACCEPT_EXT.includes(ext)) {
    return `Formato inválido (.${ext}). Envie um arquivo .csv, .xlsx ou .zip.`;
  }
  if (file.size > MAX_BYTES) {
    return `Arquivo muito grande (${formatBytes(file.size)}). Limite: 10 MB.`;
  }
  return null;
}

function applyFile(file) {
  const err = validateFile(file);
  if (err) {
    showMessage(err, "error");
    clearFile();
    return;
  }
  clearMessage();
  selectedFile = file;
  fileNameLabel.textContent = file.name;
  fileSizeLabel.textContent = formatBytes(file.size);
  filePreviewEl.classList.remove("hidden");
  uploadBtn.disabled = false;
}

function clearFile() {
  selectedFile         = null;
  fileInput.value      = "";
  filePreviewEl.classList.add("hidden");
  fileNameLabel.textContent = "";
  fileSizeLabel.textContent = "";
  uploadBtn.disabled   = true;
}

// ─────────────────────────────────────────────────────────────────────────────
// Drag & Drop
// ─────────────────────────────────────────────────────────────────────────────

dropZone.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); }
});

fileInput.addEventListener("change", () => {
  if (fileInput.files.length) applyFile(fileInput.files[0]);
});

dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("dragging");
});

["dragleave", "dragend"].forEach((ev) =>
  dropZone.addEventListener(ev, () => dropZone.classList.remove("dragging"))
);

dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("dragging");
  const file = e.dataTransfer.files[0];
  if (file) applyFile(file);
});

clearFileBtn.addEventListener("click", () => {
  clearFile();
  clearMessage();
  resultCard.classList.add("hidden");
  filterCard.classList.add("hidden");
});

// ─────────────────────────────────────────────────────────────────────────────
// Upload → POST /importar
// ─────────────────────────────────────────────────────────────────────────────

uploadBtn.addEventListener("click", async () => {
  if (!selectedFile) return;
  clearMessage();
  setUploading(true);
  resultCard.classList.add("hidden");

  const formData = new FormData();
  formData.append("arquivo", selectedFile);

  try {
    const res = await fetch(`${API_BASE}/importar`, {
      method: "POST",
      body: formData,
      credentials: "include",
    });
    const data = await res.json();

    if (!res.ok) {
      showMessage(data.detail || "Erro ao processar arquivo.", "error");
      return;
    }

    lastMeta = { tipo: data.tipo, total_registros: data.total_registros, colunas: data.colunas };
    renderResult(data);
    filterCard.classList.remove("hidden");
    resultCard.classList.remove("hidden");
    showMessage(`✅ Processado com sucesso! Tipo: ${data.tipo} — ${data.total_registros} registros.`, "success");
  } catch (err) {
    showMessage(`Falha de conexão com o servidor: ${err.message}`, "error");
  } finally {
    setUploading(false);
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// Filtros → GET /relatorio
// ─────────────────────────────────────────────────────────────────────────────

filterBtn.addEventListener("click", async () => {
  const params = buildFilterParams();
  filterBtn.disabled = true;
  filterBtn.textContent = "Filtrando…";

  try {
    const res = await fetch(`${API_BASE}/relatorio?${params}`, { credentials: "include" });
    const data = await res.json();

    if (!res.ok) {
      showMessage(data.detail || "Erro ao filtrar.", "error");
      return;
    }

    renderTable(data.colunas, data.dados);
    tableNote.textContent = `Exibindo ${data.dados.length} de ${data.total_registros} registro(s) filtrado(s).`;
    resultMeta.textContent = `Tipo: ${lastMeta?.tipo || "—"} — ${data.total_registros} registro(s) após filtro`;
  } catch (err) {
    showMessage(`Erro ao consultar relatório: ${err.message}`, "error");
  } finally {
    filterBtn.disabled = false;
    filterBtn.textContent = "Aplicar Filtros";
  }
});

function buildFilterParams() {
  const p = new URLSearchParams();
  if (filterAnalista.value.trim()) p.set("analista", filterAnalista.value.trim());
  if (filterPlantao.value.trim())  p.set("plantao",  filterPlantao.value.trim());
  if (filterDataInicio.value)      p.set("data_inicio", filterDataInicio.value);
  if (filterDataFim.value)         p.set("data_fim",    filterDataFim.value);
  return p.toString();
}

// ─────────────────────────────────────────────────────────────────────────────
// Downloads
// ─────────────────────────────────────────────────────────────────────────────

function triggerDownload(url, filename) {
  const a = document.createElement("a");
  a.href     = url;
  a.download = filename;
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

function downloadEndpoint(formato) {
  const params = buildFilterParams();
  return `${API_BASE}/exportar/${formato}${params ? "?" + params : ""}`;
}

dlCsv.addEventListener("click",  () => triggerDownload(downloadEndpoint("csv"),  "dados_tratados.csv"));
dlXlsx.addEventListener("click", () => triggerDownload(downloadEndpoint("xlsx"), "dados_tratados.xlsx"));
dlPdf.addEventListener("click",  () => triggerDownload(downloadEndpoint("pdf"),  "dados_tratados.pdf"));

// ─────────────────────────────────────────────────────────────────────────────
// Renderização
// ─────────────────────────────────────────────────────────────────────────────

function renderResult(data) {
  resultMeta.textContent =
    `Tipo: ${data.tipo} — ${data.total_registros} registro(s) — Colunas: ${data.colunas.length}`;

  renderTable(data.colunas, data.preview);

  const shown = data.preview.length;
  const total = data.total_registros;
  tableNote.textContent =
    shown < total
      ? `Exibindo prévia de ${shown} de ${total} registro(s). Use os filtros ou baixe o arquivo completo.`
      : `Exibindo todos os ${total} registro(s).`;
}

function renderTable(columns, rows) {
  // Cabeçalho
  const tr = document.createElement("tr");
  columns.forEach((col) => {
    const th = document.createElement("th");
    th.textContent = col;
    tr.appendChild(th);
  });
  previewThead.innerHTML = "";
  previewThead.appendChild(tr);

  // Corpo
  previewTbody.innerHTML = "";
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    columns.forEach((col) => {
      const td = document.createElement("td");
      const val = row[col];
      td.textContent = val === null || val === undefined ? "" : String(val);
      td.title = td.textContent; // tooltip para texto truncado
      tr.appendChild(td);
    });
    previewTbody.appendChild(tr);
  });
}
