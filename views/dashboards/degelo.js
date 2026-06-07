function barColor(fracao) {
  if (fracao > 30) return '#ef4444';
  if (fracao > 15) return '#eab308';
  return '#22c55e';
}

function updateKPIs(dados) {
  document.getElementById('kpi-devices').textContent = dados.length;
  const alerta = dados.filter(d => d.alerta).length;
  document.getElementById('kpi-alerta').textContent = alerta;
  const maxFracao = dados.length > 0 ? Math.max(...dados.map(d => d.degelo_fracao)) : 0;
  document.getElementById('kpi-max-fracao').textContent = maxFracao.toFixed(1) + '%';
  const avgCiclos = dados.length > 0
    ? (dados.reduce((s, d) => s + d.ciclos_max, 0) / dados.length).toFixed(1)
    : '—';
  document.getElementById('kpi-media-ciclos').textContent = avgCiclos;
}

function buildChart(dados) {
  const labels = dados.map(d => d.dispositivo_nome || 'Device ' + d.dispositivo_id);
  const values = dados.map(d => d.degelo_fracao);
  const colors = values.map(v => barColor(v));

  const threshold = {
    type: 'line',
    x0: -0.5,
    x1: labels.length - 0.5,
    y0: 30,
    y1: 30,
    line: { color: '#ef4444', width: 2, dash: 'dot' },
  };

  const annotation = {
    x: labels.length > 0 ? labels[labels.length - 1] : 0,
    y: 30,
    xref: 'x',
    yref: 'y',
    text: 'Threshold 30%',
    showarrow: false,
    font: { size: 10, color: '#ef4444' },
    xanchor: 'right',
    yanchor: 'bottom',
  };

  const trace = {
    x: values,
    y: labels,
    type: 'bar',
    orientation: 'h',
    marker: { color: colors },
    text: values.map(v => v.toFixed(1) + '%'),
    textposition: 'outside',
    textfont: { size: 10 },
  };

  const axisDark = { tickfont: { size: 10, color: 'rgba(242,240,235,0.42)' }, gridcolor: 'rgba(255,255,255,0.055)', linecolor: 'rgba(255,255,255,0.08)' };
  const layout = {
    margin: { t: 10, r: 60, b: 40, l: 160 },
    xaxis: { ...axisDark, title: { text: '% Degelo', font: { size: 11, color: 'rgba(242,240,235,0.5)' } }, range: [0, Math.max(...values, 35) * 1.1], ticksuffix: '%' },
    yaxis: { ...axisDark },
    shapes: [threshold],
    annotations: [{ ...annotation, font: { size: 10, color: '#ef4444' } }],
    plot_bgcolor:  'transparent',
    paper_bgcolor: 'transparent',
    font: { family: '"Inter", sans-serif', color: 'rgba(242,240,235,0.55)' },
    bargap: 0.25,
  };

  Plotly.newPlot('chart-degelo', [trace], layout, { responsive: true, displayModeBar: false });
}

function renderTable(dados) {
  const tbody = document.getElementById('degelo-tbody');
  tbody.innerHTML = dados.map(d => {
    const statusIcon = d.alerta
      ? '<i class="bi bi-exclamation-triangle-fill sem-trat-icon" title="Alerta: > 30%"></i>'
      : '<i class="bi bi-check-circle-fill ok-icon"></i>';
    const fracoStyle = d.degelo_fracao > 30
      ? 'color:#ef4444;font-weight:700'
      : d.degelo_fracao > 15 ? 'color:#eab308;font-weight:600' : 'color:#22c55e';
    return `<tr>
      <td>
        <div style="font-size:.79rem;font-weight:600">${d.dispositivo_nome || 'Device ' + d.dispositivo_id}</div>
        <div style="font-size:.67rem;color:var(--muted)">ID ${d.dispositivo_id}</div>
      </td>
      <td style="font-size:.78rem;max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${d.loja_nome}">${d.loja_nome}</td>
      <td class="num-col" style="${fracoStyle}">${d.degelo_fracao.toFixed(1)}%</td>
      <td class="num-col">${d.ciclos_max}</td>
      <td class="num-col">${d.duracao_media_min > 0 ? d.duracao_media_min.toFixed(1) + ' min' : '—'}</td>
      <td class="text-center">${statusIcon}</td>
    </tr>`;
  }).join('');
}

async function loadData() {
  try {
    const res = await fetch('/api/dashboard/degelo');
    const json = await res.json();
    if (json.status !== 'ok') throw new Error(json.mensagem);

    const dados = json.dados;
    document.getElementById('degelo-loading').style.display = 'none';
    updateKPIs(dados);
    if (dados.length > 0) {
      buildChart(dados);
      renderTable(dados);
    } else {
      document.getElementById('chart-degelo').innerHTML = '<div class="empty-chart"><i class="bi bi-snow"></i><p>Sem dados de degelo disponíveis</p></div>';
    }
    document.getElementById('degelo-update').innerHTML = `<i class="bi bi-arrow-clockwise"></i> ${new Date().toLocaleTimeString('pt-BR')}`;
  } catch (err) {
    document.getElementById('degelo-loading').innerHTML = `<i class="bi bi-x-circle text-danger" style="font-size:1.5rem"></i><span>Erro: ${err.message}</span>`;
  }
}

loadData();
setInterval(loadData, 60000);
