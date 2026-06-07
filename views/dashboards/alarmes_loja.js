const CRIT_BAR_COLORS = {
  C: 'rgba(239,68,68,0.8)',
  A: 'rgba(249,115,22,0.8)',
  M: 'rgba(234,179,8,0.8)',
  B: 'rgba(59,130,246,0.8)',
  I: 'rgba(148,163,184,0.6)',
};
const CRIT_BAR_LABELS = { C: 'Crítica', A: 'Alta', M: 'Média', B: 'Baixa', I: 'Info' };

const CHART_DARK = {
  grid:   { color: 'rgba(255,255,255,0.05)' },
  ticks:  { font: { size: 10 }, color: 'rgba(242,240,235,0.45)' },
  legend: { font: { size: 11 }, color: 'rgba(242,240,235,0.7)', padding: 10 },
};

let barChart     = null;
let doughnutChart = null;
let paretoChart  = null;

function updateKPIs(dados) {
  document.getElementById('kpi-total-lojas').textContent = dados.top_lojas.length;
  document.getElementById('kpi-sem-trat').textContent    = dados.sem_tratativa;

  const critAlta = (dados.totais_por_crit.C || 0) + (dados.totais_por_crit.A || 0);
  document.getElementById('kpi-crit-alta').textContent = critAlta;

  const sorted = [...dados.top_lojas].sort((a, b) => (b.C || 0) - (a.C || 0));
  if (sorted.length > 0) {
    document.getElementById('kpi-loja-top').textContent      = sorted[0].C || 0;
    document.getElementById('kpi-loja-top-nome').textContent = sorted[0].nome;
  }
}

function buildBarChart(lojas) {
  const labels   = lojas.map(l => l.nome.length > 20 ? l.nome.substring(0, 20) + '…' : l.nome);
  const datasets = ['C', 'A', 'M', 'B', 'I'].map(crit => ({
    label: CRIT_BAR_LABELS[crit],
    data: lojas.map(l => l[crit] || 0),
    backgroundColor: CRIT_BAR_COLORS[crit],
    borderRadius: 2,
    borderSkipped: false,
  }));

  const ctx = document.getElementById('chart-lojas-bar').getContext('2d');
  if (barChart) barChart.destroy();
  barChart = new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom', labels: CHART_DARK.legend } },
      scales: {
        x: { stacked: true, grid: CHART_DARK.grid, ticks: CHART_DARK.ticks },
        y: { stacked: true, grid: { display: false }, ticks: CHART_DARK.ticks },
      },
    },
  });
}

function buildDoughnutChart(totais) {
  const labels = Object.keys(totais).map(k => CRIT_BAR_LABELS[k]);
  const data   = Object.values(totais);
  const colors = Object.keys(totais).map(k => CRIT_BAR_COLORS[k]);

  const ctx = document.getElementById('chart-crit-doughnut').getContext('2d');
  if (doughnutChart) doughnutChart.destroy();
  doughnutChart = new Chart(ctx, {
    type: 'doughnut',
    data: { labels, datasets: [{ data, backgroundColor: colors, borderWidth: 1, borderColor: 'rgba(255,255,255,0.08)' }] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom', labels: CHART_DARK.legend } },
      cutout: '62%',
    },
  });
}

function buildParetoChart(lojas) {
  const sorted = [...lojas].sort((a, b) => b.total - a.total);
  const total  = sorted.reduce((acc, l) => acc + l.total, 0);
  if (total === 0) return;

  const labels = sorted.map(l => l.nome.length > 13 ? l.nome.substring(0, 13) + '…' : l.nome);
  const counts = sorted.map(l => l.total);

  let cum = 0;
  const cumulativePct = counts.map(c => { cum += c; return +(cum / total * 100).toFixed(1); });
  const line80Idx = cumulativePct.findIndex(p => p >= 80);

  const ctx = document.getElementById('chart-pareto').getContext('2d');
  if (paretoChart) paretoChart.destroy();
  paretoChart = new Chart(ctx, {
    data: {
      labels,
      datasets: [
        {
          type: 'bar',
          label: 'Nº Alarmes',
          data: counts,
          backgroundColor: counts.map((_, i) => i <= line80Idx ? 'rgba(239,68,68,0.65)' : 'rgba(148,163,184,0.3)'),
          borderRadius: 3,
          yAxisID: 'y',
          order: 2,
        },
        {
          type: 'line',
          label: '% Acumulado',
          data: cumulativePct,
          borderColor: '#c9b89a',
          backgroundColor: 'transparent',
          borderWidth: 2,
          pointRadius: 3,
          pointBackgroundColor: '#c9b89a',
          tension: 0.3,
          yAxisID: 'y2',
          order: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'top', labels: { ...CHART_DARK.legend, padding: 14 } },
        tooltip: {
          callbacks: {
            afterLabel: ctx => ctx.datasetIndex === 1
              ? (ctx.raw >= 80 ? '(dentro dos 80% de impacto)' : '')
              : '',
          },
        },
      },
      scales: {
        x: {
          grid: CHART_DARK.grid,
          ticks: { ...CHART_DARK.ticks, maxRotation: 45, minRotation: 30 },
        },
        y: {
          grid: CHART_DARK.grid,
          ticks: CHART_DARK.ticks,
          title: { display: true, text: 'Qtd. Alarmes', color: 'rgba(242,240,235,0.45)', font: { size: 10 } },
        },
        y2: {
          position: 'right',
          min: 0, max: 100,
          grid: { display: false },
          ticks: { font: { size: 10 }, color: '#c9b89a', callback: v => v + '%' },
          title: { display: true, text: '% Acumulado', color: '#c9b89a', font: { size: 10 } },
        },
      },
    },
  });
}

function renderTable(lojas) {
  const tbody = document.getElementById('lojas-tbody');
  tbody.innerHTML = lojas.map((l, i) => {
    const critCell = (crit, colorVar) => l[crit] > 0
      ? `<td class="num-col" style="color:${colorVar};font-weight:700;font-family:'DM Mono',monospace">${l[crit]}</td>`
      : `<td class="num-col" style="color:var(--muted)">—</td>`;
    return `<tr>
      <td style="color:var(--muted);font-size:.73rem;font-family:'DM Mono',monospace">${i + 1}</td>
      <td style="font-weight:600">${l.nome}</td>
      <td class="num-col" style="font-family:'DM Mono',monospace"><strong>${l.total}</strong></td>
      ${critCell('C', 'var(--c-crit)')}
      ${critCell('A', 'var(--c-alta)')}
      ${critCell('M', 'var(--c-media)')}
      ${critCell('B', 'var(--c-baixa)')}
      ${critCell('I', 'var(--c-info)')}
      <td class="num-col">${l.sem_trat > 0 ? `<span class="pill pill-warning">${l.sem_trat}</span>` : '<span class="text-muted">—</span>'}</td>
    </tr>`;
  }).join('');
}

async function loadData() {
  try {
    const res  = await fetch('/api/dashboard/alarmes-loja');
    const json = await res.json();
    if (json.status !== 'ok') throw new Error(json.mensagem);

    const dados = json.dados;
    document.getElementById('aloja-loading').style.display = 'none';
    updateKPIs(dados);
    buildBarChart(dados.top_lojas);
    buildDoughnutChart(dados.totais_por_crit);
    buildParetoChart(dados.top_lojas);
    renderTable(dados.top_lojas);
    document.getElementById('aloja-update').innerHTML = `<i class="bi bi-arrow-clockwise"></i> ${new Date().toLocaleTimeString('pt-BR')}`;
  } catch (err) {
    document.getElementById('aloja-loading').innerHTML = `<i class="bi bi-x-circle text-danger" style="font-size:1.5rem"></i><span>Erro: ${err.message}</span>`;
  }
}

loadData();
setInterval(loadData, 60000);
