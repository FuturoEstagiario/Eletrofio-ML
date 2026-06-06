async function loadDevices() {
  try {
    const res = await fetch('/api/dashboard/pressao/devices');
    const json = await res.json();
    if (json.status !== 'ok') throw new Error(json.mensagem);

    const sel = document.getElementById('device-select');
    if (json.dados.length === 0) {
      sel.innerHTML = '<option value="">Nenhum device com dados de pressão</option>';
      document.getElementById('pressao-loading').innerHTML =
        '<div class="empty-chart"><i class="bi bi-speedometer2"></i><p>Nenhum device com dados de pressão disponíveis</p></div>';
      return;
    }
    json.dados.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d.dispositivo_id;
      opt.textContent = `Device ${d.dispositivo_id} — PS: ${d.pressao_succao} bar`;
      sel.appendChild(opt);
    });
  } catch (err) {
    showToast('Erro ao carregar devices: ' + err.message, 'error');
  }
}

function updateDiagnostics(stats) {
  const alertsEl   = document.getElementById('diag-alerts');
  if (!alertsEl) return;
  const bloqueioEl = document.getElementById('diag-bloqueio');
  const subcargaEl = document.getElementById('diag-subcarga');
  const okEl       = document.getElementById('diag-ok');

  const razao = stats.razao_mean;
  const sup   = stats.sup_mean;
  if (razao === null && sup === null) { alertsEl.style.display = 'none'; return; }

  alertsEl.style.display = '';
  const bloqueio = razao !== null && razao > 3.5;
  const subcarga = sup   !== null && sup   > 35;

  bloqueioEl.style.display = bloqueio ? '' : 'none';
  subcargaEl.style.display = subcarga ? '' : 'none';
  okEl.style.display       = (!bloqueio && !subcarga) ? '' : 'none';

  if (bloqueio) document.getElementById('diag-razao-val').textContent = razao;
  if (subcarga) document.getElementById('diag-sup-val').textContent   = sup;
}

function updateKPIs(stats) {
  document.getElementById('kpi-ps').textContent    = stats.ps_mean    !== null ? stats.ps_mean    + ' bar' : '—';
  document.getElementById('kpi-pc').textContent    = stats.pc_mean    !== null ? stats.pc_mean    + ' bar' : '—';
  document.getElementById('kpi-razao').textContent = stats.razao_mean !== null ? stats.razao_mean           : '—';
  document.getElementById('kpi-sup').textContent   = stats.sup_mean   !== null ? stats.sup_mean   + '°C'  : '—';
  updateDiagnostics(stats);
}

function buildChart(data) {
  const axisDark = {
    tickfont:      { size: 10, color: 'rgba(242,240,235,0.42)' },
    gridcolor:     'rgba(255,255,255,0.055)',
    linecolor:     'rgba(255,255,255,0.08)',
    zerolinecolor: 'rgba(255,255,255,0.06)',
  };

  const layout = {
    height: 400,
    plot_bgcolor:  'transparent',
    paper_bgcolor: 'transparent',
    font: { family: '"Inter", sans-serif', color: 'rgba(242,240,235,0.55)' },
    margin: { t: 12, r: 72, b: 60, l: 58 },
    xaxis: { ...axisDark, tickangle: -45, nticks: 12 },
    yaxis: {
      ...axisDark,
      title: { text: 'Pressão (bar)', font: { size: 11, color: 'rgba(242,240,235,0.5)' } },
    },
    yaxis2: {
      ...axisDark,
      title: { text: 'Razão / Superaq. (°C)', font: { size: 11, color: 'rgba(242,240,235,0.5)' } },
      overlaying: 'y', side: 'right', showgrid: false,
    },
    shapes: [{
      type: 'rect', xref: 'paper', yref: 'y2',
      x0: 0, x1: 1, y0: 2.0, y1: 3.5,
      fillcolor: 'rgba(34,197,94,0.05)', line: { width: 0 },
    }],
    legend: {
      orientation: 'h', y: -0.22,
      font: { size: 11, color: 'rgba(242,240,235,0.65)' },
      bgcolor: 'transparent',
    },
  };

  const traces = [
    { x: data.labels, y: data.pressao_succao,    name: 'P. Sucção (bar)',      type: 'scatter', mode: 'lines', line: { color: '#3b82f6', width: 2   }, yaxis: 'y'  },
    { x: data.labels, y: data.pressao_cond,       name: 'P. Condensação (bar)', type: 'scatter', mode: 'lines', line: { color: '#f97316', width: 2   }, yaxis: 'y'  },
    { x: data.labels, y: data.razao_pressao,      name: 'Razão PC/PS',          type: 'scatter', mode: 'lines', line: { color: '#a78bfa', width: 1.5, dash: 'dash' }, yaxis: 'y2' },
    { x: data.labels, y: data.superaquecimento,   name: 'Superaquecimento (°C)',type: 'scatter', mode: 'lines', line: { color: '#ef4444', width: 1.5  }, yaxis: 'y2' },
  ];

  const container = document.getElementById('chart-pressao');
  container.style.height = '100%';
  Plotly.newPlot('chart-pressao', traces, layout, {
    responsive: true, displayModeBar: true,
    modeBarButtonsToRemove: ['select2d', 'lasso2d', 'autoScale2d'],
  });
}

async function loadPressao(did) {
  const loadingEl = document.getElementById('pressao-loading');
  loadingEl.style.display = 'flex';
  loadingEl.innerHTML = '<div class="spinner-lg"></div><span>Carregando série de pressão…</span>';
  try {
    const res  = await fetch(`/api/dashboard/pressao/${did}`);
    const json = await res.json();
    if (json.status !== 'ok') throw new Error(json.mensagem);

    loadingEl.style.display = 'none';
    updateKPIs(json.dados.stats);
    buildChart(json.dados);
    const upd = document.getElementById('pressao-update');
    upd.style.display = 'inline-flex';
    upd.innerHTML = `<i class="bi bi-arrow-clockwise"></i> ${new Date().toLocaleTimeString('pt-BR')}`;
  } catch {
    loadingEl.innerHTML = `<i class="bi bi-x-circle text-danger" style="font-size:1.5rem"></i><span>Sem dados de pressão para este dispositivo</span>`;
  }
}

document.getElementById('device-select').addEventListener('change', e => {
  if (e.target.value) loadPressao(parseInt(e.target.value));
});

loadDevices();
