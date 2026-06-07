const CRIT_COLORS = { C: '#ef4444', A: '#f97316', M: '#eab308', B: '#3b82f6', I: '#94a3b8' };
const CRIT_LABELS = { C: 'Crítica', A: 'Alta', M: 'Média', B: 'Baixa', I: 'Info' };

const CHART_DARK = {
  grid:   { color: 'rgba(255,255,255,0.05)' },
  ticks:  { font: { size: 10 }, color: 'rgba(242,240,235,0.45)' },
  legend: { font: { size: 11 }, color: 'rgba(242,240,235,0.7)', padding: 10 },
};

let donutChart = null;
let lojasChart = null;

function updateKPIs(d) {
  document.getElementById('kpi-total').textContent        = d.total;
  document.getElementById('kpi-critico').textContent      = d.n_critico;
  document.getElementById('kpi-critico-pct').textContent  = d.pct_critico + '% da frota';
  document.getElementById('kpi-atencao').textContent      = d.n_atencao;
  document.getElementById('kpi-atencao-pct').textContent  = d.pct_atencao + '% da frota';
  document.getElementById('kpi-normal').textContent       = d.n_normal;
  document.getElementById('kpi-normal-pct').textContent   = d.pct_normal + '% da frota';
  document.getElementById('kpi-score-medio').textContent  = d.avg_score !== null ? d.avg_score + '%' : '—';
}

function buildDonut(porCrit) {
  const keys   = Object.keys(porCrit).filter(k => porCrit[k] > 0);
  const data   = keys.map(k => porCrit[k]);
  const colors = keys.map(k => CRIT_COLORS[k] || '#94a3b8');
  const labels = keys.map(k => CRIT_LABELS[k] || k);
  const total  = data.reduce((a, b) => a + b, 0);

  const ctx = document.getElementById('chart-donut').getContext('2d');
  if (donutChart) donutChart.destroy();
  donutChart = new Chart(ctx, {
    type: 'doughnut',
    data: { labels, datasets: [{ data, backgroundColor: colors, borderWidth: 1, borderColor: 'rgba(255,255,255,0.08)', hoverOffset: 6 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      cutout: '66%',
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: ctx => ctx[0].label,
            label: ctx => {
              const pct = total > 0 ? (ctx.raw / total * 100).toFixed(1) : 0;
              return ` ${ctx.raw} devices — ${pct}% da frota`;
            },
            afterLabel: ctx => {
              const descs = {
                Crítica: 'Parada imediata — intervenção urgente',
                Alta:    'Risco elevado — planejar esta semana',
                Média:   'Monitorar de perto — risco moderado',
                Baixa:   'Operação normal com atenção',
                Info:    'Informativo — sem risco imediato',
              };
              return descs[ctx.label] || '';
            },
          },
        },
      },
    },
  });

  document.getElementById('crit-legend').innerHTML = keys.map((k, i) => `
    <div style="display:flex;align-items:center;gap:.5rem;font-size:.74rem">
      <span style="width:8px;height:8px;border-radius:2px;background:${colors[i]};flex-shrink:0"></span>
      <span style="color:var(--text);flex:1">${labels[i]}</span>
      <span style="font-family:'DM Mono',monospace;font-weight:700;color:var(--text)">${data[i]}</span>
      <span style="color:var(--muted)">${(data[i]/total*100).toFixed(0)}%</span>
    </div>`).join('');
}

function buildLojasChart(porLoja) {
  const top     = porLoja.slice(0, 12);
  const labels  = top.map(l => l.nome.length > 16 ? l.nome.substring(0, 16) + '…' : l.nome);
  const scores  = top.map(l => l.score_medio);
  const criticos = top.map(l => l.criticos);

  const ctx = document.getElementById('chart-lojas').getContext('2d');
  if (lojasChart) lojasChart.destroy();
  lojasChart = new Chart(ctx, {
    data: {
      labels,
      datasets: [
        {
          type: 'bar',
          label: 'Score ML Médio (%)',
          data: scores,
          backgroundColor: scores.map(s => s > 70 ? 'rgba(239,68,68,0.65)' : s > 40 ? 'rgba(234,179,8,0.55)' : 'rgba(34,197,94,0.45)'),
          borderRadius: 3,
          yAxisID: 'y',
          order: 2,
        },
        {
          type: 'line',
          label: 'Críticos',
          data: criticos,
          borderColor: '#ef4444',
          backgroundColor: 'transparent',
          borderWidth: 2,
          pointRadius: 4,
          pointBackgroundColor: '#ef4444',
          tension: 0.25,
          yAxisID: 'y2',
          order: 1,
        },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: 'top', labels: { ...CHART_DARK.legend, padding: 14 } },
        tooltip: {
          callbacks: {
            title: ctx => top[ctx[0].dataIndex]?.nome || ctx[0].label,
            label: ctx => {
              if (ctx.datasetIndex === 0) return ` Score ML médio: ${ctx.raw}%`;
              return ` Críticos: ${ctx.raw}`;
            },
            afterBody: ctx => {
              const l = top[ctx[0].dataIndex];
              if (!l) return [];
              const scoreLabel = l.score_medio > 70 ? '🔴 Alto risco' : l.score_medio > 40 ? '🟡 Risco moderado' : '🟢 Risco baixo';
              return [
                `─────────────────`,
                ` Total devices : ${l.total}`,
                ` Críticos      : ${l.criticos}`,
                ` Score médio   : ${l.score_medio}%`,
                ` ${scoreLabel}`,
              ];
            },
          },
        },
      },
      scales: {
        x: { grid: CHART_DARK.grid, ticks: { ...CHART_DARK.ticks, maxRotation: 40, minRotation: 20 } },
        y: {
          grid: CHART_DARK.grid, ticks: CHART_DARK.ticks,
          title: { display: true, text: 'Score (%)', color: 'rgba(242,240,235,0.45)', font: { size: 10 } },
          min: 0, max: 100,
        },
        y2: {
          position: 'right', grid: { display: false },
          ticks: { font: { size: 10 }, color: '#ef4444' },
          title: { display: true, text: 'Críticos', color: '#ef4444', font: { size: 10 } },
          min: 0,
        },
      },
    },
  });
}

function renderTop10(top10) {
  const tbody = document.getElementById('top10-tbody');
  tbody.innerHTML = top10.map((d, i) => {
    const pct  = d.risk_score !== null ? Math.round(d.risk_score * 100) : null;
    const fill = pct !== null ? (pct > 70 ? '#ef4444' : pct > 40 ? '#eab308' : '#22c55e') : '#94a3b8';
    const tratativa = d.sem_tratativa
      ? '<i class="bi bi-exclamation-circle-fill sem-trat-icon" title="Sem tratativa"></i>'
      : '<i class="bi bi-check-circle-fill ok-icon" title="Com tratativa"></i>';

    return `<tr>
      <td style="color:var(--muted);font-size:.73rem;font-family:'DM Mono',monospace">${i + 1}</td>
      <td><span class="crit-badge crit-${d.criticidade}">${d.crit_label}</span></td>
      <td>
        <div style="font-weight:600;font-size:.82rem">${d.dispositivo_nome || '—'}</div>
        <div style="font-size:.68rem;color:var(--muted)">ID ${d.dispositivo_id}</div>
      </td>
      <td class="td-loja" title="${d.loja_nome}">${d.loja_nome}</td>
      <td class="num-col">
        ${pct !== null ? `<div class="d-flex align-items-center gap-2 justify-content-end">
          <div class="progress-bar-risk" style="width:42px">
            <div class="progress-bar-risk-fill" style="width:${pct}%;background:${fill}"></div>
          </div>
          <span style="font-weight:700;font-size:.78rem">${pct}%</span>
        </div>` : '<span class="text-muted">—</span>'}
      </td>
      <td class="num-col">${d.temp_atual !== null ? `<span style="font-weight:600">${d.temp_atual}°C</span>` : '<span class="text-muted">—</span>'}</td>
      <td class="num-col">${d.temp_erro !== null ? `<span style="color:${Math.abs(d.temp_erro) > 5 ? '#ef4444' : Math.abs(d.temp_erro) > 2 ? '#eab308' : '#22c55e'}">${d.temp_erro > 0 ? '+' : ''}${d.temp_erro}°C</span>` : '<span class="text-muted">—</span>'}</td>
      <td class="num-col"><span style="color:${d.degelo_fracao > 30 ? '#ef4444' : d.degelo_fracao > 15 ? '#eab308' : '#22c55e'}">${d.degelo_fracao}%</span></td>
      <td class="text-center">${tratativa}</td>
    </tr>`;
  }).join('');
}

async function loadData() {
  try {
    const res  = await fetch('/api/dashboard/saude');
    const json = await res.json();
    if (json.status !== 'ok') throw new Error(json.mensagem);

    const d = json.dados;
    document.getElementById('saude-loading').style.display = 'none';
    updateKPIs(d);
    buildDonut(d.por_crit);
    buildLojasChart(d.por_loja);
    renderTop10(d.top10);
    document.getElementById('saude-update').innerHTML = `<i class="bi bi-arrow-clockwise"></i> ${new Date().toLocaleTimeString('pt-BR')}`;
  } catch (err) {
    document.getElementById('saude-loading').innerHTML = `<i class="bi bi-x-circle text-danger" style="font-size:1.5rem"></i><span>Erro: ${err.message}</span>`;
  }
}

loadData();
setInterval(loadData, 60000);
