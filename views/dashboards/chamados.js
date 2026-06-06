let horaChart = null;
const today = new Date().toISOString().split('T')[0];

function formatTs(ts) {
  try {
    const d = new Date(ts);
    return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  } catch {
    return ts;
  }
}

function updateKPIs(dados) {
  document.getElementById('kpi-total').textContent = dados.length;

  const hoje = dados.filter(d => d.ts && d.ts.startsWith(today)).length;
  document.getElementById('kpi-hoje').textContent = hoje;

  const abertos = dados.filter(d => d.status === 'aberto').length;
  document.getElementById('kpi-abertos').textContent = abertos;

  document.getElementById('kpi-score-medio').textContent = '—';
}

function renderTable(dados) {
  const tbody = document.getElementById('chamados-tbody');
  const empty = document.getElementById('chamados-empty');
  document.getElementById('chamados-count').textContent = dados.length;

  if (dados.length === 0) {
    tbody.innerHTML = '';
    empty.style.display = 'flex';
    return;
  }
  empty.style.display = 'none';

  tbody.innerHTML = dados.map(d => {
    const motivoTrunc = d.motivo && d.motivo.length > 60
      ? `<span title="${d.motivo.replace(/"/g, '&quot;')}">${d.motivo.substring(0, 60)}…</span>`
      : (d.motivo || '—');

    const statusBadge = d.status === 'fechado'
      ? '<span class="badge-status-fechado">Fechado</span>'
      : '<span class="badge-status-aberto">Aberto</span>';

    return `<tr>
      <td style="font-size:.75rem;white-space:nowrap">${formatTs(d.ts)}</td>
      <td>
        <div style="font-weight:600;font-size:.8rem">${d.tag || '—'}</div>
        <div style="font-size:.67rem;color:var(--muted)">ID ${d.dispositivo_id}</div>
      </td>
      <td class="td-loja" style="font-size:.79rem" title="${d.loja_nome || ''}">${d.loja_nome || '—'}</td>
      <td class="num-col" style="font-size:.78rem">—</td>
      <td style="font-size:.78rem;max-width:200px">${motivoTrunc}</td>
      <td class="text-center">${statusBadge}</td>
    </tr>`;
  }).join('');
}

function buildHoraChart(dados) {
  const horas = Array(24).fill(0);
  dados.forEach(d => {
    try {
      const h = new Date(d.ts).getHours();
      horas[h]++;
    } catch {}
  });

  if (horas.every(v => v === 0)) {
    document.getElementById('hora-empty').style.display = 'flex';
    document.getElementById('chart-hora').style.display = 'none';
    return;
  }

  document.getElementById('hora-empty').style.display = 'none';
  document.getElementById('chart-hora').style.display = 'block';

  const ctx = document.getElementById('chart-hora').getContext('2d');
  if (horaChart) horaChart.destroy();
  horaChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: Array.from({ length: 24 }, (_, i) => `${i}h`),
      datasets: [{
        label: 'Chamados',
        data: horas,
        backgroundColor: 'rgba(79,70,229,0.7)',
        borderRadius: 4,
        borderSkipped: false,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 9 } } },
        y: { beginAtZero: true, grid: { color: '#f1f5f9' }, ticks: { stepSize: 1, font: { size: 10 } } },
      },
    },
  });
}

async function loadData() {
  try {
    const res = await fetch('/api/dashboard/chamados');
    const json = await res.json();
    if (json.status !== 'ok') throw new Error(json.mensagem);

    const dados = json.dados;
    document.getElementById('chamados-loading').style.display = 'none';
    updateKPIs(dados);
    renderTable(dados);
    buildHoraChart(dados);
    document.getElementById('chamados-update').innerHTML = `<i class="bi bi-arrow-clockwise"></i> ${new Date().toLocaleTimeString('pt-BR')}`;
  } catch (err) {
    document.getElementById('chamados-loading').innerHTML = `<i class="bi bi-x-circle text-danger" style="font-size:1.5rem"></i><span>Erro: ${err.message}</span>`;
  }
}

loadData();
setInterval(loadData, 30000);
