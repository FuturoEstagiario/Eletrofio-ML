/* EletroFrio ML — Dashboard PoC */

(function () {
  "use strict";

  // ── Sidebar ──────────────────────────────────────────────────────────────────

  const KEY     = "sb_collapsed";
  const sidebar = document.getElementById("sidebar");
  const wrapper = document.querySelector(".main-wrapper");
  const overlay = document.getElementById("sidebarOverlay");

  function isDesktop() { return window.innerWidth > 992; }

  // Aplica estado colapsado/expandido no desktop
  function setCollapsed(collapsed) {
    if (!sidebar) return;
    sidebar.classList.toggle("collapsed", collapsed);
    if (wrapper) wrapper.style.marginLeft = collapsed ? "64px" : "var(--sidebar-w)";
    localStorage.setItem(KEY, collapsed ? "1" : "0");
  }

  // Fecha sidebar mobile
  function closeMobile() {
    sidebar?.classList.remove("open");
    overlay?.classList.remove("open");
    document.body.style.overflow = "";
  }

  // Abre sidebar mobile
  function openMobile() {
    sidebar?.classList.add("open");
    overlay?.classList.add("open");
    document.body.style.overflow = "hidden"; // impede scroll do body
  }

  // Inicialização: limpa estados incompatíveis ao carregar
  if (isDesktop()) {
    sidebar?.classList.remove("open");   // limpa possível `open` de sessão mobile
    overlay?.classList.remove("open");
    setCollapsed(localStorage.getItem(KEY) === "1");
  } else {
    sidebar?.classList.remove("collapsed"); // limpa possível `collapsed` de sessão desktop
    if (wrapper) wrapper.style.marginLeft = "";
  }

  // Toggle principal — chamado pelo botão hamburguer (mobile) e pelo chevron (desktop)
  window.toggleSidebar = function () {
    if (isDesktop()) {
      setCollapsed(!sidebar?.classList.contains("collapsed"));
    } else {
      sidebar?.classList.contains("open") ? closeMobile() : openMobile();
    }
  };

  // Fecha ao clicar no overlay (mobile)
  window.closeMobileSidebar = closeMobile;
  overlay?.addEventListener("click", closeMobile);

  // Fecha ao clicar num link (mobile)
  document.querySelectorAll(".sidebar-link").forEach((el) => {
    el.addEventListener("click", () => { if (!isDesktop()) closeMobile(); });
  });

  // Reajusta ao redimensionar a janela
  window.addEventListener("resize", () => {
    if (isDesktop()) {
      closeMobile();
      setCollapsed(localStorage.getItem(KEY) === "1");
    } else {
      sidebar?.classList.remove("collapsed");
      if (wrapper) wrapper.style.marginLeft = "";
    }
  });

  // ── Telemetria: carrega em paralelo após a página abrir ────────────────────

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

    document.querySelectorAll(`.tele-media[data-id="${id}"]`).forEach((el) => {
      el.innerHTML = features ? `<span class="temp-val">${fmt(features.temp_media)}</span>` : NA;
    });
    document.querySelectorAll(`.tele-maxima[data-id="${id}"]`).forEach((el) => {
      const alta = features && features.temp_maxima > 30 ? " temp-alta" : "";
      el.innerHTML = features ? `<span class="temp-val${alta}">${fmt(features.temp_maxima)}</span>` : NA;
    });
    document.querySelectorAll(`.tele-tend[data-id="${id}"]`).forEach((el) => {
      if (!features) { el.innerHTML = NA; return; }
      const t = features.temp_tendencia;
      const cls  = t > 0 ? "tend-up" : t < 0 ? "tend-down" : "";
      const icon = t > 0 ? "▲" : t < 0 ? "▼" : "●";
      el.innerHTML = `<span class="tendencia ${cls}">${icon} ${t}</span>`;
    });
  }

  // Coleta IDs únicos da tabela e dispara todos os fetches ao mesmo tempo
  const ids = [...new Set(
    [...document.querySelectorAll("[data-id]")].map((el) => el.dataset.id)
  )];

  if (ids.length) {
    Promise.all(ids.map(carregarTelemetria)).then((resultados) => {
      resultados.forEach(({ id, features }) => preencherCelulasTelemetria(id, features));
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
          label: "Quantidade",
          data: window.DASH.data,
          backgroundColor: window.DASH.colors,
          borderRadius: 6,
          borderSkipped: false,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (c) => ` ${c.parsed.y} alarme(s)`,
            },
          },
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: { stepSize: 1, precision: 0 },
            grid: { color: "#f0f0f0" },
          },
          x: { grid: { display: false } },
        },
      },
    });
  }

  // ── Paginação de Alarmes ────────────────────────────────────────────────────

  const ALARMES        = window.ALARMES || [];
  const ALARMES_PG_SZ  = 10;
  let   alarmesPagina  = 1;
  const teleCache      = {};   // cache: dispositivoId → features (evita re-fetch ao trocar página)

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
        <td class="fw-medium text-nowrap">${a.loja_nome || "—"}</td>
        <td><code class="tag-code">${a.tag || "—"}</code></td>
        <td class="text-nowrap text-sm">${a.alarme_desc || "—"}</td>
        <td class="text-muted text-sm text-nowrap">${a.tempo || "—"}</td>
        <td class="text-center tele-media"  data-id="${id}"><span class="spinner"></span></td>
        <td class="text-center tele-maxima" data-id="${id}"><span class="spinner"></span></td>
        <td class="text-center tele-tend"   data-id="${id}"><span class="spinner"></span></td>
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

    // Telemetria: usa cache ou busca para IDs da página atual
    const ids = [...new Set(slice.map((a) => String(a.dispositivo_id)))];
    ids.forEach((id) => {
      if (teleCache[id] !== undefined) {
        preencherCelulasTelemetria(id, teleCache[id]);
      } else {
        carregarTelemetria(id).then(({ features }) => {
          teleCache[id] = features;
          preencherCelulasTelemetria(id, features);
        });
      }
    });
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

    // Sem resultados
    if (total === 0) {
      grid.innerHTML = `<div class="col-12 text-muted text-center py-3">Nenhuma unidade encontrada.</div>`;
      pag.innerHTML  = "";
      const count = document.getElementById("unid-count");
      if (count) count.textContent = "0";
      return;
    }

    // Cards
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

    // Paginação
    pag.innerHTML = buildPaginacao(pagina, total, PAGE_SIZE, "irPagina");

    // Indicador "x–y de N"
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

  // Estado do modal
  let _chamadoPayload = null;

  window.abrirModalChamado = function (btn) {
    const dispId   = btn.dataset.dispositivoId;
    const lojaId   = btn.dataset.lojaId;
    const lojaNome = btn.dataset.lojaNome;
    const tag      = btn.dataset.tag;
    const alarme   = btn.dataset.alarme || "";
    const crit     = btn.dataset.crit || "";

    _chamadoPayload = { dispositivo_id: dispId, loja_id: lojaId, loja_nome: lojaNome, tag };

    document.getElementById("mc-dispositivo").textContent =
      `[${crit}] ${tag} — ${lojaNome} (ID: ${dispId})`;

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
    btnConf.textContent = "Enviando...";
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
          <div class="alert alert-success py-2">
            <strong>Chamado aberto com sucesso!</strong>
            <pre class="mb-0 mt-1" style="font-size:.75rem">${JSON.stringify(json.resposta, null, 2)}</pre>
          </div>`;
        btnConf.textContent = "Confirmar Chamado";
      } else {
        feedback.innerHTML = `
          <div class="alert alert-danger py-2">
            <strong>Erro:</strong> ${json.mensagem || "Falha ao abrir chamado."}
          </div>`;
        btnConf.disabled = false;
        btnConf.textContent = "Confirmar Chamado";
      }
    } catch (err) {
      feedback.innerHTML = `<div class="alert alert-danger py-2"><strong>Erro de rede:</strong> ${err.message}</div>`;
      btnConf.disabled = false;
      btnConf.textContent = "Confirmar Chamado";
    }
  };

})();
