let importanceChart = null;
let scoresChart     = null;

function buildImportanceChart(items) {
  const labels = items.map(i => i.feature.replace(/_/g, ' '));
  const values = items.map(i => +(i.importancia * 100).toFixed(1));
  const colors = values.map(v => v >= 25 ? '#ef4444' : v >= 15 ? '#f97316' : v >= 8 ? '#eab308' : '#3b82f6');

  const ctx = document.getElementById('chart-importance').getContext('2d');
  if (importanceChart) importanceChart.destroy();
  importanceChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: colors,
        borderRadius: 4,
        borderSkipped: false,
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
            label: ctx => ` ${ctx.raw}% de importância`,
            afterLabel: ctx => {
              const tips = {
                'temp media':       'Temperatura média do período',
                'temp maxima':      'Pico de temperatura',
                'temp minima':      'Vale de temperatura',
                'temp amplitude':   'Variação máx-mín (oscilação)',
                'temp volatilidade':'Desvio padrão — instabilidade',
                'temp tendencia':   'Taxa de variação linear (subida/descida)',
              };
              return tips[ctx.label] ? `  ↳ ${tips[ctx.label]}` : '';
            },
          },
        },
      },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,.05)' },
          ticks: { color: '#94a3b8', callback: v => v + '%' },
          max: 100,
        },
        y: {
          grid: { display: false },
          ticks: { color: '#c9b89a', font: { family: "'DM Mono', monospace", size: 11 } },
        },
      },
    },
  });
}

function buildScoresChart(dist) {
  const ctx = document.getElementById('chart-scores').getContext('2d');
  if (scoresChart) scoresChart.destroy();
  scoresChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['Baixo (<40%)', 'Médio (40–70%)', 'Alto (>70%)'],
      datasets: [{
        data: [dist.baixo, dist.medio, dist.alto],
        backgroundColor: ['#22c55e', '#eab308', '#ef4444'],
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,.08)',
        hoverOffset: 6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '62%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: { color: '#94a3b8', font: { size: 11 }, padding: 12 },
        },
        tooltip: {
          callbacks: {
            label: ctx => {
              const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
              const pct = total > 0 ? (ctx.raw / total * 100).toFixed(0) : 0;
              return ` ${ctx.raw} devices — ${pct}%`;
            },
          },
        },
      },
    },
  });
}

function renderModelInfo(info, elId) {
  const el = document.getElementById(elId);
  if (!info || !info.carregado) {
    el.innerHTML = '<div class="empty-chart" style="min-height:120px"><i class="bi bi-cpu"></i><p>Modelo não carregado — execute <code>python main.py --real</code></p></div>';
    return;
  }
  if (info.erro) {
    el.innerHTML = `<p style="color:var(--muted)">${info.tipo} carregado, mas não foi possível extrair metadados.</p>`;
    return;
  }

  const rows = Object.entries(info)
    .filter(([k]) => !['tipo', 'carregado', 'erro'].includes(k))
    .map(([k, v]) => {
      const labels = {
        n_estimators: 'Nº estimadores', n_features: 'Nº features',
        kernel: 'Kernel', nu: 'Nu (taxa anomalia)', n_support: 'Vectores de suporte',
      };
      return `<div style="display:flex;justify-content:space-between;padding:.3rem 0;border-bottom:1px solid rgba(255,255,255,.05)">
        <span style="color:var(--muted)">${labels[k] || k}</span>
        <span style="font-family:'DM Mono',monospace;font-weight:600">${v}</span>
      </div>`;
    }).join('');

  el.innerHTML = `<div style="font-weight:600;color:var(--beige);margin-bottom:.6rem">${info.tipo}</div>${rows}`;
}

async function loadData() {
  try {
    const res  = await fetch('/api/dashboard/modelo');
    const json = await res.json();
    if (json.status !== 'ok') throw new Error(json.mensagem);

    const d = json.dados;
    document.getElementById('modelo-loading').style.display = 'none';

    document.getElementById('kpi-modelo-tipo').textContent =
      d.modelo_info?.rf?.carregado ? 'Random Forest' : d.modelo_info?.ocsvm?.carregado ? 'OneClass SVM' : 'Não carregado';
    document.getElementById('kpi-n-estimators').textContent =
      d.modelo_info?.rf?.n_estimators ?? '—';
    document.getElementById('kpi-score-medio').textContent =
      d.score_medio != null ? Math.round(d.score_medio * 100) + '%' : '—';
    document.getElementById('kpi-n-scored').textContent =
      d.n_devices_scored ?? '—';

    if (d.feature_importance?.length) {
      buildImportanceChart(d.feature_importance);
    } else {
      document.getElementById('chart-importance').closest('.chart-container-sm').innerHTML =
        '<div class="empty-chart"><i class="bi bi-cpu"></i><p>Modelo RF não carregado — sem feature importance disponível</p></div>';
    }

    buildScoresChart(d.score_distribuicao || { baixo: 0, medio: 0, alto: 0 });
    renderModelInfo(d.modelo_info?.rf, 'info-rf');
    renderModelInfo(d.modelo_info?.ocsvm, 'info-ocsvm');

    document.getElementById('modelo-update').innerHTML =
      `<i class="bi bi-arrow-clockwise"></i> ${new Date().toLocaleTimeString('pt-BR')}`;
  } catch (err) {
    document.getElementById('modelo-loading').innerHTML =
      `<i class="bi bi-x-circle text-danger" style="font-size:1.5rem"></i><span>Erro: ${err.message}</span>`;
  }
}

loadData();
setInterval(loadData, 120000);
