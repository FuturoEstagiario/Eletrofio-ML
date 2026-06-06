/* EletroFrio ML — Dashboard PoC */

(function () {
  "use strict";

  // ── Sidebar ──────────────────────────────────────────────────────────────────

  const KEY     = "sb_collapsed";
  const sidebar = document.getElementById("sidebar");
  const wrapper = document.querySelector(".main-wrapper");
  const overlay = document.getElementById("sidebarOverlay");

  function isDesktop() { return window.innerWidth > 992; }

  function setCollapsed(collapsed) {
    if (!sidebar) return;
    sidebar.classList.toggle("collapsed", collapsed);
    if (wrapper) wrapper.style.marginLeft = collapsed ? "64px" : "var(--sidebar-w)";
    localStorage.setItem(KEY, collapsed ? "1" : "0");
  }

  function closeMobile() {
    sidebar?.classList.remove("open");
    overlay?.classList.remove("open");
    document.body.style.overflow = "";
  }

  function openMobile() {
    sidebar?.classList.add("open");
    overlay?.classList.add("open");
    document.body.style.overflow = "hidden";
  }

  if (isDesktop()) {
    sidebar?.classList.remove("open");
    overlay?.classList.remove("open");
    setCollapsed(localStorage.getItem(KEY) === "1");
  } else {
    sidebar?.classList.remove("collapsed");
    if (wrapper) wrapper.style.marginLeft = "";
  }

  window.toggleSidebar = function () {
    if (isDesktop()) {
      setCollapsed(!sidebar?.classList.contains("collapsed"));
    } else {
      sidebar?.classList.contains("open") ? closeMobile() : openMobile();
    }
  };

  window.closeMobileSidebar = closeMobile;
  overlay?.addEventListener("click", closeMobile);

  document.querySelectorAll(".sidebar-link").forEach((el) => {
    el.addEventListener("click", () => { if (!isDesktop()) closeMobile(); });
  });

  window.addEventListener("resize", () => {
    if (isDesktop()) {
      closeMobile();
      setCollapsed(localStorage.getItem(KEY) === "1");
    } else {
      sidebar?.classList.remove("collapsed");
      if (wrapper) wrapper.style.marginLeft = "";
    }
  });

  // ── Toast Notifications ─────────────────────────────────────────────────────

  const toastContainer = document.getElementById("toastContainer");

  window.mostrarToast = function (message, type, duration) {
    if (!toastContainer) return;
    type = type || "info";
    duration = duration || 4000;
    const icons = { success: "bi-check-circle-fill", error: "bi-x-circle-fill", info: "bi-info-circle-fill" };
    const el = document.createElement("div");
    el.className = `toast-item toast-${type}`;
    el.innerHTML = `<i class="bi ${icons[type] || icons.info}"></i><span>${message}</span>`;
    toastContainer.appendChild(el);
    setTimeout(() => {
      el.classList.add("toast-leaving");
      setTimeout(() => el.remove(), 250);
    }, duration);
  };

  // ── Health Check ────────────────────────────────────────────────────────────

  async function verificarSaude() {
    try {
      const res  = await fetch("/api/health");
      const json = await res.json();
      const el   = document.getElementById("api-status-label");
      if (!el) return;
      if (json.status === "ok" && json.api) {
        el.innerHTML =
          `<span class="text-success"><i class="bi bi-circle-fill" style="font-size:.55rem"></i> API conectada</span>`;
      } else {
        el.innerHTML =
          `<span class="text-danger"><i class="bi bi-circle-fill" style="font-size:.55rem"></i> API indispon&iacute;vel</span>`;
      }
    } catch {
      const el = document.getElementById("api-status-label");
      if (el) el.innerHTML =
        `<span class="text-danger"><i class="bi bi-circle-fill" style="font-size:.55rem"></i> API indispon&iacute;vel</span>`;
    }
  }
  verificarSaude();

  // ── Telemetria ──────────────────────────────────────────────────────────────

  async function carregarTelemetria(dispositivoId) {
    try {
      const res = await fetch(`/api/telemetria/${dispositivoId}`);
      const json = await res.json();
      if (json.status !== "ok" || !json.features || !Object.keys(json.features).length) {
        return { id: dispositivoId, features: null };
      }
      return { id: dispositivoId, features: json.features };
    } catch {
      return { id: dispositivoId, features: null };
    }
  }

  function preencherCelulasTelemetria(id, features) {
    const fmt = (v) => v != null ? `${v}°C` : "—";
    const NA  = '<span class="text-muted">—</span>';

    document.querySelectorAll(`.tele-temp[data-id="${id}"]`).forEach((el) => {
      if (!features) { el.innerHTML = NA; return; }
      const alta = features.temp_maxima > 30 ? " temp-alta" : "";
      const sep  = `<span class="text-muted" style="margin:0 3px">/</span>`;
      el.innerHTML =
        `<span class="temp-val tele-label">mín</span><span class="temp-val">${fmt(features.temp_minima)}</span>`
        + sep
        + `<span class="temp-val tele-label">méd</span><span class="temp-val">${fmt(features.temp_media)}</span>`
        + sep
        + `<span class="temp-val tele-label">máx</span><span class="temp-val${alta}">${fmt(features.temp_maxima)}</span>`;
    });
  }

  // ── Predição (Risco + Anomalia) ─────────────────────────────────────────────

  async function carregarPredicao(dispositivoId) {
    try {
      const res = await fetch(`/api/predict/${dispositivoId}`);
      const json = await res.json();
      if (json.status !== "ok") return { id: dispositivoId, risk: null, anomaly: false };
      return { id: dispositivoId, risk: json.risk_score, anomaly: json.anomaly, reason: json.anomaly_reason };
    } catch {
      return { id: dispositivoId, risk: null, anomaly: false };
    }
  }

  function preencherCelulasPredicao(id, pred) {
    if (!pred) {
      document.querySelectorAll(`.tele-risco[data-id="${id}"]`).forEach((el) => el.innerHTML = '<span class="text-muted">—</span>');
      document.querySelectorAll(`.tele-anomalia[data-id="${id}"]`).forEach((el) => el.innerHTML = '<span class="text-muted">—</span>');
      return;
    }

    // Risco
    const risk = pred.risk;
    document.querySelectorAll(`.tele-risco[data-id="${id}"]`).forEach((el) => {
      if (risk == null) { el.innerHTML = '<span class="text-muted">—</span>'; return; }
      const pct = Math.round(risk * 100);
      const cls = pct < 30 ? "risk-low" : pct < 75 ? "risk-mid" : "risk-high";
      const label = pct < 30 ? "Baixo" : pct < 75 ? "Médio" : "Alto";
      el.innerHTML = `<span class="risk-badge ${cls}">${pct}% · ${label}</span>`;
    });

    // Anomalia
    document.querySelectorAll(`.tele-anomalia[data-id="${id}"]`).forEach((el) => {
      if (pred.anomaly) {
        const reason = pred.reason ? pred.reason.replace(/"/g, "&quot;") : "Possível anomalia";
        el.innerHTML = `<span class="anomaly-yes" title="${reason}"><i class="bi bi-exclamation-triangle-fill"></i> Anomalia</span>`;
      } else {
        el.innerHTML = `<span class="anomaly-no"><i class="bi bi-check-circle-fill"></i></span>`;
      }
    });
  }

  // ── Fetch combinado: telemetria + predição em paralelo ──────────────────────

  const teleCache = {};
  const predCache = {};

  function fetchDeviceData(ids) {
    ids.forEach((id) => {
      // Telemetria
      if (teleCache[id] !== undefined) {
        preencherCelulasTelemetria(id, teleCache[id]);
      } else {
        carregarTelemetria(id).then(({ features }) => {
          teleCache[id] = features;
          preencherCelulasTelemetria(id, features);
        });
      }
      // Predição
      if (predCache[id] !== undefined) {
        preencherCelulasPredicao(id, predCache[id]);
      } else {
        carregarPredicao(id).then((pred) => {
          predCache[id] = pred;
          preencherCelulasPredicao(id, pred);
        });
      }
    });
  }

  // ── Chart.js: Alarmes por Criticidade ──────────────────────────────────────

  const ctx = document.getElementById("chartCrit");
  if (ctx && window.DASH) {
    new Chart(ctx, {
      type: "bar",
      data: {
        labels: window.DASH.labels,
        datasets: [{
          label: "Alarmes",
          data: window.DASH.data,
          backgroundColor: window.DASH.colors,
          borderRadius: 4,
          borderSkipped: false,
          barThickness: 28,
        }],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (c) => ` ${c.parsed.x} alarme(s)`,
            },
          },
        },
        scales: {
          x: {
            beginAtZero: true,
            ticks: { stepSize: 1, precision: 0, color: 'rgba(242,240,235,0.45)', font: { size: 10 } },
            grid: { color: 'rgba(255,255,255,0.055)' },
          },
          y: {
            grid: { display: false },
            ticks: { color: 'rgba(242,240,235,0.7)', font: { size: 11, weight: '600' } },
          },
        },
      },
    });
  }

  // ── Paginação de Alarmes ────────────────────────────────────────────────────

  const ALARMES        = window.ALARMES || [];
  const ALARMES_PG_SZ  = 10;
  let   alarmesPagina  = 1;

  const CRIT_LABELS = { C:"Crítica", A:"Alta", M:"Média", B:"Baixa", I:"Info" };

  function buildAlarmeRow(a) {
    const id    = a.dispositivo_id;
    const crit  = a.criticidade || "I";
    const label = CRIT_LABELS[crit] || crit;
    const trat  = a.sem_tratativa
      ? `<span class="pill pill-danger">Pendente</span>`
      : `<span class="status-ok"><i class="bi bi-check-lg"></i></span>`;

    return `
      <tr class="row-crit-${crit}">
        <td><span class="crit-badge crit-${crit}">${crit} · ${label}</span></td>
        <td class="fw-medium td-loja" title="${a.loja_nome || ""}">${a.loja_nome || "—"}</td>
        <td><code class="tag-code">${a.tag || "—"}</code></td>
        <td class="text-sm td-alarme" title="${a.alarme_desc || ""}">${a.alarme_desc || "—"}</td>
        <td class="text-muted text-sm text-nowrap">${a.tempo || "—"}</td>
        <td class="text-center tele-risco" data-id="${id}"><span class="shimmer"></span></td>
        <td class="text-center tele-anomalia" data-id="${id}"><span class="shimmer"></span></td>
        <td class="text-center tele-temp" data-id="${id}"><span class="shimmer"></span></td>
        <td class="text-center">${trat}</td>
        <td class="text-center">
          <button class="btn-action"
            data-dispositivo-id="${id}"
            data-loja-id="${a.loja_id}"
            data-loja-nome="${a.loja_nome}"
            data-tag="${a.tag}"
            data-alarme="${a.alarme_desc || ""}"
            data-crit="${crit}"
            onclick="abrirModalChamado(this)">
            <i class="bi bi-plus-lg"></i> Chamado
          </button>
        </td>
      </tr>`;
  }

  function buildPaginacao(paginaAtual, total, pageSize, fnIr) {
    const pages = Math.ceil(total / pageSize) || 1;
    const maxBtns = 7;
    let html = "";

    html += `<li class="${paginaAtual === 1 ? "disabled" : ""}">
      <a href="#" onclick="${fnIr}(${paginaAtual - 1});return false;">&laquo;</a></li>`;

    let start = Math.max(1, paginaAtual - Math.floor(maxBtns / 2));
    let end   = Math.min(pages, start + maxBtns - 1);
    if (end - start < maxBtns - 1) start = Math.max(1, end - maxBtns + 1);

    if (start > 1) {
      html += `<li><a href="#" onclick="${fnIr}(1);return false;">1</a></li>`;
      if (start > 2) html += `<li class="disabled"><span>…</span></li>`;
    }
    for (let p = start; p <= end; p++) {
      html += `<li class="${p === paginaAtual ? "active" : ""}">
        <a href="#" onclick="${fnIr}(${p});return false;">${p}</a></li>`;
    }
    if (end < pages) {
      if (end < pages - 1) html += `<li class="disabled"><span>…</span></li>`;
      html += `<li><a href="#" onclick="${fnIr}(${pages});return false;">${pages}</a></li>`;
    }
    html += `<li class="${paginaAtual === pages ? "disabled" : ""}">
      <a href="#" onclick="${fnIr}(${paginaAtual + 1});return false;">&raquo;</a></li>`;

    return html;
  }

  function renderAlarmes(pagina) {
    const tbody = document.getElementById("alarmes-tbody");
    const pag   = document.getElementById("alarmes-pagination");
    const info  = document.getElementById("alarmes-info");
    const count = document.getElementById("alarmes-count");
    if (!tbody) return;

    const total  = ALARMES.length;
    const pages  = Math.ceil(total / ALARMES_PG_SZ) || 1;
    const inicio = (pagina - 1) * ALARMES_PG_SZ;
    const fim    = Math.min(inicio + ALARMES_PG_SZ, total);
    const slice  = ALARMES.slice(inicio, fim);

    tbody.innerHTML = slice.length
      ? slice.map(buildAlarmeRow).join("")
      : `<tr><td colspan="10" class="text-center text-muted py-4">Nenhum alarme ativo.</td></tr>`;

    if (pag) pag.innerHTML = total > ALARMES_PG_SZ
      ? buildPaginacao(pagina, total, ALARMES_PG_SZ, "irPaginaAlarmes")
      : "";

    if (info) info.textContent = total
      ? `${inicio + 1}–${fim} de ${total}`
      : "";

    if (count) count.textContent = total;

    // Data fetching for visible rows
    const ids = [...new Set(slice.map((a) => String(a.dispositivo_id)))];
    fetchDeviceData(ids);
  }

  window.irPaginaAlarmes = function (p) {
    const pages = Math.ceil(ALARMES.length / ALARMES_PG_SZ) || 1;
    alarmesPagina = Math.max(1, Math.min(p, pages));
    renderAlarmes(alarmesPagina);
  };

  if (ALARMES.length) renderAlarmes(1);

  // ── Paginação de Unidades ───────────────────────────────────────────────────

  const UNIDADES     = window.UNIDADES || [];
  const PAGE_SIZE    = 24;
  let   paginaAtual  = 1;
  let   filtrado     = UNIDADES;

  function filtrarUnidades(termo) {
    const q = termo.trim().toLowerCase();
    filtrado = q
      ? UNIDADES.filter((u) =>
          (u.lojaNm    || "").toLowerCase().includes(q) ||
          (u.lojaApelido || "").toLowerCase().includes(q) ||
          (u.contaNm   || "").toLowerCase().includes(q)
        )
      : UNIDADES;
    paginaAtual = 1;
    renderUnidades(1);
  }

  function renderUnidades(pagina) {
    const grid   = document.getElementById("unidades-grid");
    const pag    = document.getElementById("unidades-pagination");
    if (!grid || !pag) return;

    const total  = filtrado.length;
    const pages  = Math.ceil(total / PAGE_SIZE) || 1;
    const inicio = (pagina - 1) * PAGE_SIZE;
    const fim    = Math.min(inicio + PAGE_SIZE, total);

    if (total === 0) {
      grid.innerHTML = `<div class="col-12 text-muted text-center py-3">Nenhuma unidade encontrada.</div>`;
      pag.innerHTML  = "";
      const count = document.getElementById("unid-count");
      if (count) count.textContent = "0";
      return;
    }

    grid.innerHTML = filtrado.slice(inicio, fim).map((u) => {
      const id       = u.lojaId || "";
      const nome     = (u.lojaNm || u.nome || "Sem nome").trim();
      const apelido  = u.lojaApelido ? `<div class="unidade-apelido">${u.lojaApelido}</div>` : "";
      const contrato = u.tpContratoNm ? `<span class="unidade-tag">${u.tpContratoNm}</span>` : "";
      const conta    = u.contaNm ? `<div class="unidade-local">${u.contaNm}</div>` : "";
      const ativo    = u.ativo === false ? `<span class="unidade-inativo">Inativo</span>` : "";

      return `
        <div class="col-12 col-sm-6 col-md-4 col-xl-3">
          <a href="/api/unidades/${id}" target="_blank" class="unidade-link" title="Ver JSON da loja #${id}">
            <div class="unidade-card">
              <div class="unidade-nome">${nome} ${ativo}</div>
              ${apelido}
              ${conta}
              ${contrato}
            </div>
          </a>
        </div>`;
    }).join("");

    pag.innerHTML = buildPaginacao(pagina, total, PAGE_SIZE, "irPagina");

    const count = document.getElementById("unid-count");
    if (count) {
      count.textContent = total < UNIDADES.length
        ? `${inicio + 1}–${fim} de ${total} (filtrado)`
        : `${inicio + 1}–${fim} de ${total}`;
    }
  }

  window.irPagina = function (p) {
    const pages = Math.ceil(filtrado.length / PAGE_SIZE) || 1;
    paginaAtual = Math.max(1, Math.min(p, pages));
    renderUnidades(paginaAtual);
    document.getElementById("unidades-grid")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  if (UNIDADES.length) {
    renderUnidades(1);
    const input = document.getElementById("unidades-busca");
    if (input) {
      input.addEventListener("input", (e) => filtrarUnidades(e.target.value));
    }
  }

  // ── Modal: Abrir Chamado ────────────────────────────────────────────────────

  let _chamadoPayload = null;

  window.abrirModalChamado = function (btn) {
    const dispId   = btn.dataset.dispositivoId;
    const lojaId   = btn.dataset.lojaId;
    const lojaNome = btn.dataset.lojaNome;
    const tag      = btn.dataset.tag;
    const alarme   = btn.dataset.alarme || "";
    const crit     = btn.dataset.crit || "";

    _chamadoPayload = { dispositivo_id: dispId, loja_id: lojaId, loja_nome: lojaNome, tag };

    const critLabel = CRIT_LABELS[crit] || crit;
    document.getElementById("mc-dispositivo").innerHTML = `
      <div class="mb-2"><span class="crit-badge crit-${crit}">${crit} · ${critLabel}</span></div>
      <div class="modal-device-row"><i class="bi bi-shop"></i><span>${lojaNome}</span></div>
      <div class="modal-device-row"><i class="bi bi-cpu"></i><span>${tag}</span><span class="modal-id">ID: ${dispId}</span></div>`;

    document.getElementById("mc-motivo").value =
      alarme ? `Alarme ativo: ${alarme}` : "";

    document.getElementById("mc-feedback").innerHTML = "";
    document.getElementById("mc-confirmar").disabled = false;

    new bootstrap.Modal(document.getElementById("modalChamado")).show();
  };

  window.confirmarChamado = async function () {
    if (!_chamadoPayload) return;

    const motivo  = document.getElementById("mc-motivo").value.trim();
    const tecnico = document.getElementById("mc-tecnico").checked;
    const feedback = document.getElementById("mc-feedback");
    const btnConf  = document.getElementById("mc-confirmar");

    if (!motivo) {
      feedback.innerHTML = '<div class="alert alert-warning py-2">Informe o motivo do chamado.</div>';
      return;
    }

    btnConf.disabled = true;
    btnConf.innerHTML = '<i class="bi bi-hourglass-split"></i> Enviando…';
    feedback.innerHTML = "";

    const payload = {
      ..._chamadoPayload,
      motivo_ia: motivo,
      requer_tecnico: tecnico,
    };

    try {
      const res  = await fetch("/api/abrir-chamado", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const json = await res.json();

      if (res.ok && json.status === "ok") {
        feedback.innerHTML = `
          <div class="modal-feedback-ok">
            <i class="bi bi-check-circle-fill" style="font-size:1.1rem;flex-shrink:0"></i>
            <div>
              <div class="fw-semibold">Chamado aberto com sucesso!</div>
              <pre class="modal-resp-pre">${JSON.stringify(json.resposta, null, 2)}</pre>
            </div>
          </div>`;
        btnConf.innerHTML = '<i class="bi bi-send-fill"></i> Confirmar Chamado';
        mostrarToast(`Chamado aberto para ${_chamadoPayload.loja_nome}`, "success", 5000);
      } else {
        feedback.innerHTML = `
          <div class="modal-feedback-err">
            <i class="bi bi-x-circle-fill" style="font-size:1.1rem;flex-shrink:0"></i>
            <span><strong>Erro:</strong> ${json.mensagem || "Falha ao abrir chamado."}</span>
          </div>`;
        btnConf.disabled = false;
        btnConf.innerHTML = '<i class="bi bi-send-fill"></i> Confirmar Chamado';
        mostrarToast(json.mensagem || "Erro ao abrir chamado", "error", 5000);
      }
    } catch (err) {
      feedback.innerHTML = `
        <div class="modal-feedback-err">
          <i class="bi bi-x-circle-fill" style="font-size:1.1rem;flex-shrink:0"></i>
          <span><strong>Erro de rede:</strong> ${err.message}</span>
        </div>`;
      btnConf.disabled = false;
      btnConf.innerHTML = '<i class="bi bi-send-fill"></i> Confirmar Chamado';
      mostrarToast("Erro de rede ao abrir chamado", "error", 5000);
    }
  };

})();
