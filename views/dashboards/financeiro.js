const BRL = n => new Intl.NumberFormat('pt-BR', {
  style: 'currency', currency: 'BRL',
  minimumFractionDigits: 0, maximumFractionDigits: 0,
}).format(n);

const BRL2 = n => new Intl.NumberFormat('pt-BR', {
  style: 'currency', currency: 'BRL',
}).format(n);

const fmtROI = n => n >= 1000 ? '>' + Math.round(n / 1000) + 'k×' : n.toFixed(1) + '×';

const CHART_DARK = {
  grid:   { color: 'rgba(255,255,255,0.05)' },
  ticks:  { font: { size: 10 }, color: 'rgba(242,240,235,0.45)' },
  legend: { labels: { font: { size: 11 }, color: 'rgba(242,240,235,0.7)', padding: 10 } },
};

const CRIT_COLORS = {
  C: 'rgba(239,68,68,0.72)',
  A: 'rgba(249,115,22,0.72)',
  M: 'rgba(234,179,8,0.72)',
  B: 'rgba(59,130,246,0.72)',
  I: 'rgba(148,163,184,0.55)',
};

const CRIT_LABELS = { C: 'Crítica', A: 'Alta', M: 'Média', B: 'Baixa', I: 'Info' };

const REC_STYLE = {
  Urgente:     { bg: 'rgba(239,68,68,.15)',  border: 'rgba(239,68,68,.4)',   text: '#ef4444' },
  Recomendado: { bg: 'rgba(249,115,22,.1)',  border: 'rgba(249,115,22,.35)', text: '#f97316' },
  Monitorar:   { bg: 'rgba(234,179,8,.1)',   border: 'rgba(234,179,8,.3)',   text: '#eab308' },
  Normal:      { bg: 'rgba(34,197,94,.08)',  border: 'rgba(34,197,94,.22)',  text: '#22c55e' },
};

let _charts = {};
let _allDevices = [];

function destroyChart(id) {
  if (_charts[id]) { _charts[id].destroy(); delete _charts[id]; }
}

function recBadge(rec) {
  const s = REC_STYLE[rec] || REC_STYLE.Normal;
  return `<span style="display:inline-flex;align-items:center;gap:5px;font-size:.64rem;font-weight:700;padding:2px 8px;border-radius:50px;border:1px solid ${s.border};background:${s.bg};color:${s.text};letter-spacing:.05em;text-transform:uppercase">${rec}</span>`;
}

function critBadge(crit) {
  const colors = { C: '#ef4444', A: '#f97316', M: '#eab308', B: '#3b82f6', I: '#94a3b8' };
  return `<span style="font-size:.7rem;font-weight:700;color:${colors[crit] || '#94a3b8'};font-family:'DM Mono',monospace">${crit}</span>`;
}

function scoreBar(score) {
  const pct = Math.round((score || 0) * 100);
  const color = pct >= 70 ? '#ef4444' : pct >= 40 ? '#f97316' : pct >= 20 ? '#eab308' : '#4ade80';
  return `<div style="display:flex;align-items:center;gap:6px">
    <div style="width:52px;height:5px;background:rgba(255,255,255,0.08);border-radius:3px;overflow:hidden">
      <div style="width:${pct}%;height:100%;background:${color};border-radius:3px"></div>
    </div>
    <span style="font-family:'DM Mono',monospace;font-size:.73rem;color:rgba(242,240,235,.7)">${pct}%</span>
  </div>`;
}

function roiColor(roi) {
  return roi >= 50 ? '#ef4444' : roi >= 10 ? '#f97316' : roi >= 2 ? '#eab308' : '#22c55e';
}

function buildTopDevicesChart(devices) {
  destroyChart('top');
  const top10 = devices.slice(0, 10);
  const ctx = document.getElementById('chart-top-devices').getContext('2d');
  _charts.top = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: top10.map(d => (d.dispositivo_nome || ('Dev ' + d.dispositivo_id)).substring(0, 22)),
      datasets: [{
        label: 'Exposição/dia (R$)',
        data: top10.map(d => d.exposicao_diaria),
        backgroundColor: top10.map(d => CRIT_COLORS[d.criticidade] || 'rgba(201,184,154,0.5)'),
        borderRadius: 4,
        barThickness: 20,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => ' ' + BRL(ctx.raw) } },
      },
      scales: {
        x: { grid: CHART_DARK.grid, ticks: { ...CHART_DARK.ticks, callback: v => BRL(v) } },
        y: { grid: { display: false }, ticks: CHART_DARK.ticks },
      },
    },
  });
}

function buildRecDonut(porRec) {
  destroyChart('rec');
  const order = ['Urgente', 'Recomendado', 'Monitorar', 'Normal'];
  const labels = order.filter(k => (porRec[k] || 0) > 0);
  const values = labels.map(k => porRec[k]);
  const colors = labels.map(k => (REC_STYLE[k] || {}).text || '#94a3b8');
  const ctx = document.getElementById('chart-recomendacao').getContext('2d');
  _charts.rec = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{ data: values, backgroundColor: colors, borderWidth: 0, hoverOffset: 6 }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '68%',
      plugins: {
        legend: { position: 'bottom', ...CHART_DARK.legend },
        tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ${ctx.raw} devices` } },
      },
    },
  });
}

function buildLojasChart(porLoja) {
  destroyChart('lojas');
  const top = porLoja.slice(0, 12);
  const ctx = document.getElementById('chart-lojas').getContext('2d');
  _charts.lojas = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: top.map(l => l.nome.substring(0, 20)),
      datasets: [
        {
          label: 'Exposição/dia (R$)',
          data: top.map(l => l.total_exposicao_diaria),
          backgroundColor: 'rgba(201,184,154,0.42)',
          borderRadius: 3,
          barThickness: 14,
          yAxisID: 'y',
        },
        {
          label: 'Urgentes',
          data: top.map(l => l.devices_urgentes),
          backgroundColor: 'rgba(239,68,68,0.65)',
          borderRadius: 3,
          barThickness: 14,
          yAxisID: 'y2',
        },
      ],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'top', ...CHART_DARK.legend },
        tooltip: {
          callbacks: {
            label: ctx => ctx.datasetIndex === 0
              ? ' Exposição: ' + BRL(ctx.raw)
              : ' Urgentes: ' + ctx.raw,
          },
        },
      },
      scales: {
        x:  { grid: CHART_DARK.grid, ticks: { ...CHART_DARK.ticks, callback: v => BRL(v) } },
        y:  { grid: { display: false }, ticks: CHART_DARK.ticks },
        y2: { position: 'right', display: false },
      },
    },
  });
}

function buildScatterChart(devices) {
  destroyChart('scatter');
  const ctx = document.getElementById('chart-scatter').getContext('2d');
  const datasets = ['C', 'A', 'M', 'B', 'I'].map(crit => ({
    label: CRIT_LABELS[crit],
    data: devices
      .filter(d => d.criticidade === crit)
      .map(d => ({ x: +(d.risk_score * 100).toFixed(1), y: d.exposicao_diaria, _d: d })),
    backgroundColor: CRIT_COLORS[crit],
    pointRadius: 5,
    pointHoverRadius: 7,
  })).filter(ds => ds.data.length > 0);

  _charts.scatter = new Chart(ctx, {
    type: 'scatter',
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'top', ...CHART_DARK.legend },
        tooltip: {
          callbacks: {
            label: ctx => {
              const d = ctx.raw._d;
              return [
                ' ' + (d.dispositivo_nome || 'Device ' + d.dispositivo_id),
                ' Exposição/dia: ' + BRL(d.exposicao_diaria),
                ' Score ML: ' + Math.round(d.risk_score * 100) + '%',
                ' ROI: ' + fmtROI(d.roi),
              ];
            },
          },
        },
      },
      scales: {
        x: {
          title: { display: true, text: 'Score ML (%)', color: 'rgba(242,240,235,.42)', font: { size: 10 } },
          min: 0, max: 100,
          grid: CHART_DARK.grid, ticks: CHART_DARK.ticks,
        },
        y: {
          title: { display: true, text: 'Exposição/dia (R$)', color: 'rgba(242,240,235,.42)', font: { size: 10 } },
          grid: CHART_DARK.grid,
          ticks: { ...CHART_DARK.ticks, callback: v => v >= 1000 ? (v / 1000).toFixed(0) + 'k' : v },
        },
      },
    },
  });
}

function renderTable(devices) {
  const tbody = document.getElementById('fin-tbody');
  const emptyEl = document.getElementById('fin-empty');
  const countEl = document.getElementById('fin-count');

  if (!devices.length) {
    emptyEl.style.display = '';
    tbody.innerHTML = '';
    countEl.textContent = '0';
    return;
  }
  emptyEl.style.display = 'none';
  countEl.textContent = devices.length;

  tbody.innerHTML = devices.map(d => `
    <tr>
      <td>${recBadge(d.recomendacao)}</td>
      <td style="font-size:.8rem;font-weight:500;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${d.dispositivo_nome || ('Device ' + d.dispositivo_id)}</td>
      <td style="font-size:.76rem;color:var(--muted);max-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${d.loja_nome}</td>
      <td class="num-col">${critBadge(d.criticidade)}</td>
      <td class="num-col">${scoreBar(d.risk_score)}</td>
      <td class="num-col" style="font-family:'DM Mono',monospace;font-size:.74rem;color:var(--muted)">${BRL2(d.exposicao_hora)}</td>
      <td class="num-col" style="font-family:'DM Mono',monospace;font-size:.8rem;font-weight:600;color:#ef4444">${BRL(d.exposicao_diaria)}</td>
      <td class="num-col" style="font-family:'DM Mono',monospace;font-size:.74rem;color:var(--muted)">${BRL(d.exposicao_semanal)}</td>
      <td class="num-col" style="font-family:'DM Mono',monospace;font-size:.8rem;font-weight:700;color:${roiColor(d.roi)}">${fmtROI(d.roi)}</td>
      <td class="num-col" style="font-family:'DM Mono',monospace;font-size:.74rem;color:${d.economia_diaria > 0 ? '#4ade80' : 'var(--muted)'}">${d.economia_diaria > 0 ? BRL(d.economia_diaria) : '—'}</td>
    </tr>`).join('');
}

function populateKPIs(d) {
  document.getElementById('kpi-exp-diaria').textContent  = BRL(d.total_exposicao_diaria);
  document.getElementById('kpi-exp-semanal').textContent = BRL(d.total_exposicao_semanal);
  document.getElementById('kpi-urgentes').textContent    = d.devices_urgentes;
  document.getElementById('kpi-economia').textContent    = BRL(d.economia_potencial_diaria);
  document.getElementById('kpi-investimento').textContent = BRL(d.custo_total_intervencao);
  document.getElementById('kpi-roi-medio').textContent   = fmtROI(d.roi_medio);
}

function renderAssumpcoes(assumpcoes) {
  const custo = assumpcoes.custo_hora || {};
  const labels = { C: 'Crítica', A: 'Alta', M: 'Média', B: 'Baixa', I: 'Info' };
  const colors = { C: '#ef4444', A: '#f97316', M: '#eab308', B: '#3b82f6', I: '#94a3b8' };
  const grid = document.getElementById('assumpcoes-grid');

  const items = Object.entries(custo).map(([k, v]) => `
    <div class="col-6 col-md-4 col-lg-2">
      <div style="background:var(--card);border:1px solid rgba(255,255,255,.06);border-radius:var(--radius-sm);padding:.65rem .9rem">
        <div style="font-size:.63rem;color:${colors[k] || '#94a3b8'};font-weight:700;text-transform:uppercase;letter-spacing:.07em;margin-bottom:.25rem">${labels[k] || k}</div>
        <div style="font-family:'DM Mono',monospace;font-size:.88rem;font-weight:600;color:var(--text)">${BRL(v)}<span style="font-size:.68rem;color:var(--muted)">/h</span></div>
      </div>
    </div>`).join('');

  const intervencao = `
    <div class="col-6 col-md-4 col-lg-2">
      <div style="background:var(--card);border:1px solid rgba(201,184,154,.15);border-radius:var(--radius-sm);padding:.65rem .9rem">
        <div style="font-size:.63rem;color:var(--beige);font-weight:700;text-transform:uppercase;letter-spacing:.07em;margin-bottom:.25rem">Intervenção</div>
        <div style="font-family:'DM Mono',monospace;font-size:.88rem;font-weight:600;color:var(--text)">${BRL(assumpcoes.custo_intervencao || 450)}<span style="font-size:.68rem;color:var(--muted)">/visita</span></div>
      </div>
    </div>`;

  grid.innerHTML = items + intervencao;
}

function applyFilters() {
  const rec  = document.getElementById('rec-filter').value;
  const crit = document.getElementById('crit-filter-fin').value;
  const filtered = _allDevices.filter(d =>
    (!rec  || d.recomendacao === rec) &&
    (!crit || d.criticidade  === crit)
  );
  renderTable(filtered);
}

async function loadFinanceiro() {
  const loadingEl = document.getElementById('fin-loading');
  try {
    const res  = await fetch('/api/dashboard/financeiro');
    const json = await res.json();
    if (json.status !== 'ok') throw new Error(json.mensagem);

    loadingEl.style.display = 'none';
    const d = json.dados;
    _allDevices = d.devices || [];

    populateKPIs(d);
    buildTopDevicesChart(_allDevices);
    buildRecDonut(d.por_recomendacao || {});
    buildLojasChart(d.por_loja || []);
    buildScatterChart(_allDevices);
    renderTable(_allDevices);
    renderAssumpcoes(d.assumpcoes || {});

    const upd = document.getElementById('fin-update');
    upd.style.display = 'inline-flex';
    upd.innerHTML = `<i class="bi bi-arrow-clockwise"></i> ${new Date().toLocaleTimeString('pt-BR')}`;
    _initExportFin();
  } catch (err) {
    loadingEl.innerHTML = `<i class="bi bi-x-circle text-danger" style="font-size:1.5rem"></i><span>Erro ao carregar dados: ${err.message}</span>`;
    showToast('Erro ao carregar impacto financeiro: ' + err.message, 'error');
  }
}

let _exportFinInit = false;
function _initExportFin() {
  if (_exportFinInit) return;
  _exportFinInit = true;
  const ref = document.getElementById('fin-update');
  if (!ref) return;
  const btn = document.createElement('button');
  btn.className = 'btn-action ms-2';
  btn.style.cssText = 'font-size:.72rem;padding:.2rem .55rem';
  btn.innerHTML = '<i class="bi bi-download"></i> CSV';
  btn.onclick = () => {
    const headers = ['Recomendação', 'Dispositivo', 'ID', 'Loja', 'Criticidade', 'Score ML', 'R$/hora', 'Exposição/dia', 'Exposição/semana', 'ROI ×', 'Economia/dia'];
    const rows = _allDevices.map(d => [
      d.recomendacao,
      d.dispositivo_nome,
      d.dispositivo_id,
      d.loja_nome,
      d.criticidade,
      d.risk_score != null ? (d.risk_score * 100).toFixed(1) + '%' : '',
      d.custo_hora != null ? 'R$ ' + d.custo_hora.toFixed(0) : '',
      d.exposicao_diaria != null ? 'R$ ' + d.exposicao_diaria.toFixed(0) : '',
      d.exposicao_semanal != null ? 'R$ ' + d.exposicao_semanal.toFixed(0) : '',
      d.roi != null ? d.roi.toFixed(1) + 'x' : '',
      d.economia_diaria != null ? 'R$ ' + d.economia_diaria.toFixed(0) : '',
    ]);
    exportarCSV(headers, rows, `impacto_financeiro_${new Date().toISOString().slice(0,10)}.csv`);
  };
  ref.after(btn);
}

document.getElementById('rec-filter').addEventListener('change', applyFilters);
document.getElementById('crit-filter-fin').addEventListener('change', applyFilters);

loadFinanceiro();
setInterval(loadFinanceiro, 120000);
