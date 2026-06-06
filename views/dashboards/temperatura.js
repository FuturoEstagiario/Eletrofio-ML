let tempChart = null;

async function loadDevices() {
  try {
    const res = await fetch('/api/dashboard/temperatura/devices');
    const json = await res.json();
    if (json.status !== 'ok') throw new Error(json.mensagem);

    const sel = document.getElementById('device-select');
    json.dados.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d.did;
      opt.textContent = `[${d.criticidade}] ${d.nome || 'Device ' + d.did} — ${d.loja}`;
      sel.appendChild(opt);
    });
  } catch (err) {
    showToast('Erro ao carregar dispositivos: ' + err.message, 'error');
  }
}

function updateKPIs(stats) {
  document.getElementById('kpi-temp-media').textContent = stats.temp_mean !== undefined ? stats.temp_mean + '°C' : '—';
  document.getElementById('kpi-temp-max').textContent = stats.temp_max !== undefined ? stats.temp_max + '°C' : '—';
  document.getElementById('kpi-setpoint').textContent = stats.sp_mean !== undefined ? stats.sp_mean + '°C' : '—';
  document.getElementById('kpi-pct-acima').textContent = stats.pct_acima_sp !== undefined ? stats.pct_acima_sp + '%' : '—';
}

function renderStats(stats) {
  const rows = [
    ['Temp Média', stats.temp_mean + '°C'],
    ['Temp Máxima', stats.temp_max + '°C'],
    ['Temp Mínima', stats.temp_min + '°C'],
    ['Desvio Padrão', stats.temp_std + '°C'],
    ['Percentil 25', stats.temp_p25 + '°C'],
    ['Percentil 75', stats.temp_p75 + '°C'],
    ['Setpoint Médio', stats.sp_mean + '°C'],
    ['% Acima Setpoint', stats.pct_acima_sp + '%'],
  ];
  document.getElementById('temp-stats').innerHTML = rows.map(([k, v]) =>
    `<div class="analysis-row"><span class="analysis-key">${k}</span><span class="analysis-val">${v}</span></div>`
  ).join('');
}

function buildChart(data) {
  const degeloX = data.labels.filter((_, i) => data.degelo[i] === 1);
  const degeloY = data.temp.filter((_, i) => data.degelo[i] === 1);

  const traces = [
    {
      x: data.labels,
      y: data.band_upper,
      name: 'SP +2°C',
      type: 'scatter',
      mode: 'lines',
      line: { color: 'rgba(239,68,68,0.5)', width: 1, dash: 'dot' },
      showlegend: true,
    },
    {
      x: data.labels,
      y: data.band_lower,
      name: 'SP -2°C',
      type: 'scatter',
      mode: 'lines',
      line: { color: 'rgba(34,197,94,0.5)', width: 1, dash: 'dot' },
      fill: 'tonexty',
      fillcolor: 'rgba(34,197,94,0.08)',
      showlegend: true,
    },
    {
      x: data.labels,
      y: data.setpoint,
      name: 'Setpoint',
      type: 'scatter',
      mode: 'lines',
      line: { color: '#6366f1', width: 1.5, dash: 'dash' },
    },
    {
      x: data.labels,
      y: data.temp,
      name: 'Temperatura',
      type: 'scatter',
      mode: 'lines',
      line: { color: '#3b82f6', width: 2 },
    },
  ];

  if (degeloX.length > 0) {
    traces.push({
      x: degeloX,
      y: degeloY,
      name: 'Degelo Ativo',
      type: 'scatter',
      mode: 'markers',
      marker: { color: '#f97316', size: 6, symbol: 'circle' },
    });
  }

  const axisDark = {
    tickfont:      { size: 10, color: 'rgba(242,240,235,0.42)' },
    gridcolor:     'rgba(255,255,255,0.055)',
    linecolor:     'rgba(255,255,255,0.08)',
    zerolinecolor: 'rgba(255,255,255,0.06)',
  };
  const layout = {
    margin: { t: 10, r: 12, b: 60, l: 52 },
    xaxis: { ...axisDark, tickangle: -45, nticks: 12 },
    yaxis: { ...axisDark, title: { text: '°C', font: { size: 11, color: 'rgba(242,240,235,0.5)' } } },
    legend: { orientation: 'h', y: -0.22, font: { size: 11, color: 'rgba(242,240,235,0.65)' }, bgcolor: 'transparent' },
    plot_bgcolor:  'transparent',
    paper_bgcolor: 'transparent',
    font: { family: '"Inter", sans-serif', color: 'rgba(242,240,235,0.55)' },
  };

  const container = document.getElementById('chart-temperatura');
  container.style.height = '100%';
  Plotly.newPlot('chart-temperatura', traces, layout, { responsive: true, displayModeBar: false });
}

async function loadTemperatura(did) {
  const loadingEl = document.getElementById('temp-loading');
  loadingEl.style.display = 'flex';
  loadingEl.innerHTML = '<div class="spinner-lg"></div><span>Carregando série temporal…</span>';

  try {
    const res = await fetch(`/api/dashboard/temperatura/${did}`);
    const json = await res.json();
    if (json.status !== 'ok') throw new Error(json.mensagem);

    const data = json.dados;
    loadingEl.style.display = 'none';
    updateKPIs(data.stats);
    renderStats(data.stats);
    buildChart(data);

    document.getElementById('temp-update').style.display = 'inline-flex';
    document.getElementById('temp-update').innerHTML = `<i class="bi bi-arrow-clockwise"></i> ${new Date().toLocaleTimeString('pt-BR')}`;
  } catch (err) {
    loadingEl.innerHTML = `<i class="bi bi-x-circle text-danger" style="font-size:1.5rem"></i><span>Erro: ${err.message}</span>`;
  }
}

document.getElementById('device-select').addEventListener('change', e => {
  if (e.target.value) loadTemperatura(parseInt(e.target.value));
});

loadDevices();
