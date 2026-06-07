const CRIT_ORDER = { C: 0, A: 1, M: 2, B: 3, I: 4 };
const CRIT_SCORE = { C: 1.0, A: 0.75, M: 0.5, B: 0.25, I: 0.1 };
let allData = [];
let activeCrits = new Set(['C', 'A', 'M', 'B', 'I']);

function calcCompositeScore(d) {
  const ml       = d.risk_score ?? 0;
  const crit     = CRIT_SCORE[d.criticidade] ?? 0.25;
  const degeloN  = Math.min((d.degelo_fracao || 0) / 50, 1);
  const tempErrN = d.temp_erro !== null && d.temp_erro !== undefined
    ? Math.min(Math.abs(d.temp_erro) / 10, 1) : 0;
  return Math.min(ml * 0.40 + crit * 0.25 + degeloN * 0.20 + tempErrN * 0.15, 1);
}

function getScoreHistory() {
  try { return JSON.parse(localStorage.getItem('ef_score_history') || '{}'); } catch { return {}; }
}

function saveScoreHistory(data) {
  const hist = getScoreHistory();
  const now  = Date.now();
  data.forEach(d => {
    const key = String(d.dispositivo_id);
    const arr = hist[key] || [];
    arr.push({ ts: now, v: calcCompositeScore(d) });
    hist[key] = arr.slice(-8);
  });
  try { localStorage.setItem('ef_score_history', JSON.stringify(hist)); } catch {}
}

function renderSparkline(deviceId, historyMap) {
  const pts = (historyMap[String(deviceId)] || []).map(p => p.v);
  if (pts.length < 2) return '<span style="font-size:.6rem;color:var(--muted)">—</span>';

  const W = 52, H = 18;
  const min = Math.min(...pts), max = Math.max(...pts);
  const range = max - min || 0.01;
  const coords = pts.map((v, i) => {
    const x = (i / (pts.length - 1)) * W;
    const y = H - ((v - min) / range) * (H - 3) - 1;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');

  const last = pts[pts.length - 1];
  const prev = pts[pts.length - 2];
  const color = last > prev + 0.02 ? '#ef4444' : last < prev - 0.02 ? '#4ade80' : '#c9b89a';

  return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" style="overflow:visible">
    <polyline points="${coords}" fill="none" stroke="${color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`;
}

function estimarDiasFalha(deviceId) {
  const hist = getScoreHistory();
  const pts  = hist[String(deviceId)] || [];
  if (pts.length < 3) return null;

  const now = Date.now();
  const xs  = pts.map(p => (p.ts - now) / 86400000);
  const ys  = pts.map(p => p.v);
  const n   = xs.length;
  const sx  = xs.reduce((a, b) => a + b, 0);
  const sy  = ys.reduce((a, b) => a + b, 0);
  const sxy = xs.reduce((s, x, i) => s + x * ys[i], 0);
  const sx2 = xs.reduce((s, x) => s + x * x, 0);
  const denom = n * sx2 - sx * sx;
  if (Math.abs(denom) < 1e-9) return null;

  const slope = (n * sxy - sx * sy) / denom;
  const intercept = (sy - slope * sx) / n;
  if (slope <= 0.001) return null;

  const THRESHOLD = 0.85;
  if (intercept >= THRESHOLD) return 0;
  const dias = Math.round((THRESHOLD - intercept) / slope);
  return dias > 0 && dias <= 365 ? dias : null;
}

function scoreColor(score) {
  if (score === null || score === undefined) return null;
  if (score < 0.4) return 'risk-fill-low';
  if (score < 0.7) return 'risk-fill-mid';
  return 'risk-fill-high';
}

function tempErrColor(err) {
  if (err === null || err === undefined) return '';
  if (err > 5) return 'color:#ef4444;font-weight:700';
  if (err > 2) return 'color:#eab308;font-weight:600';
  return 'color:#22c55e';
}

function renderRow(d, historyMap) {
  const composite = calcCompositeScore(d);
  const mlPct     = d.risk_score !== null && d.risk_score !== undefined
    ? Math.round(d.risk_score * 100) : null;

  const dias = estimarDiasFalha(d.dispositivo_id);
  const diasBadge = dias !== null
    ? `<div style="font-size:.6rem;font-weight:600;margin-top:3px;color:${dias <= 7 ? '#ef4444' : dias <= 30 ? '#eab308' : '#4ade80'}">⏱ ~${dias}d p/ falha</div>`
    : '';

  const WARN_LABELS = {
    temp_subindo:   { icon: '🌡', txt: 'Temp subindo',     color: '#f97316' },
    degelo_elevado: { icon: '❄',  txt: 'Degelo elevado',   color: '#60a5fa' },
    acima_setpoint: { icon: '↑',  txt: 'Acima setpoint',   color: '#ef4444' },
    temp_instavel:  { icon: '〜', txt: 'Temp instável',    color: '#eab308' },
  };
  const alertasBadges = (d.alertas || []).map(a => {
    const w = WARN_LABELS[a] || { icon: '!', txt: a, color: '#94a3b8' };
    return `<span style="font-size:.58rem;background:${w.color}22;color:${w.color};border:1px solid ${w.color}44;border-radius:3px;padding:0 4px;margin-right:2px;white-space:nowrap">${w.icon} ${w.txt}</span>`;
  }).join('');

  const scoreCell = `<div class="sparkline-cell">
    <div>
      <div class="d-flex align-items-center gap-2 mb-1">
        <div class="progress-bar-risk" style="width:52px">
          <div class="progress-bar-risk-fill ${scoreColor(composite)}" style="width:${Math.round(composite*100)}%"></div>
        </div>
        <span style="font-size:.75rem;font-weight:700">${Math.round(composite*100)}%</span>
      </div>
      <div style="font-size:.62rem;color:var(--muted)">ML: ${mlPct !== null ? mlPct + '%' : 'N/A'}</div>
      ${diasBadge}
      ${alertasBadges ? `<div style="margin-top:3px">${alertasBadges}</div>` : ''}
    </div>
    ${renderSparkline(d.dispositivo_id, historyMap)}
  </div>`;

  const tempStr = d.temp_atual !== null && d.temp_atual !== undefined
    ? `<span style="font-weight:600">${d.temp_atual}°C</span>`
    : '<span class="text-muted">—</span>';

  const errStr = d.temp_erro !== null && d.temp_erro !== undefined
    ? `<span style="${tempErrColor(d.temp_erro)}">${d.temp_erro > 0 ? '+' : ''}${d.temp_erro}°C</span>`
    : '<span class="text-muted">—</span>';

  const stdStr = d.temp_std !== null && d.temp_std !== undefined
    ? `<span style="font-size:.79rem">${d.temp_std}°C</span>`
    : '<span class="text-muted">—</span>';

  const degeloStr = `<span style="${d.degelo_fracao > 30 ? 'color:#ef4444;font-weight:700' : d.degelo_fracao > 15 ? 'color:#eab308;font-weight:600' : 'color:#22c55e'}">${d.degelo_fracao}%</span>`;

  const tratativa = d.sem_tratativa
    ? '<i class="bi bi-exclamation-circle-fill sem-trat-icon" title="Sem tratativa"></i>'
    : '<i class="bi bi-check-circle-fill ok-icon" title="Com tratativa"></i>';

  return `<tr class="row-crit-${d.criticidade}" data-crit="${d.criticidade}" data-loja="${d.loja_nome}" data-score="${d.risk_score ?? 0}" data-degelo="${d.degelo_fracao}" data-temp="${d.temp_atual ?? 0}" data-composite="${composite}">
    <td><span class="crit-badge crit-${d.criticidade}">${d.crit_label}</span></td>
    <td>
      <div style="font-weight:600;font-size:.82rem">${d.dispositivo_nome || '—'}</div>
      <div style="font-size:.69rem;color:var(--muted)">ID ${d.dispositivo_id}</div>
    </td>
    <td class="td-loja" title="${d.loja_nome}">${d.loja_nome}</td>
    <td class="num-col">${tempStr}</td>
    <td class="num-col">${errStr}</td>
    <td class="num-col">${stdStr}</td>
    <td class="num-col">${degeloStr}</td>
    <td>${scoreCell}</td>
    <td class="text-center">${tratativa}</td>
    <td style="font-size:.78rem;color:var(--muted)">${d.tempo || '—'}</td>
    <td class="text-center">
      <button class="btn-action" onclick="abrirChamado(${JSON.stringify(d).replace(/"/g, '&quot;')})">
        <i class="bi bi-tools"></i> Chamado
      </button>
    </td>
  </tr>`;
}

function applyFilters() {
  const lojaFilter = document.getElementById('loja-filter').value;
  const sortBy     = document.getElementById('sort-filter').value;
  const historyMap = getScoreHistory();

  let filtered = allData.filter(d => activeCrits.has(d.criticidade));
  if (lojaFilter) filtered = filtered.filter(d => d.loja_nome === lojaFilter);

  if (sortBy === 'prioridade') filtered.sort((a, b) => calcCompositeScore(b) - calcCompositeScore(a));
  else if (sortBy === 'score')  filtered.sort((a, b) => (b.risk_score ?? 0) - (a.risk_score ?? 0));
  else if (sortBy === 'degelo') filtered.sort((a, b) => b.degelo_fracao - a.degelo_fracao);
  else if (sortBy === 'temp')   filtered.sort((a, b) => (b.temp_atual ?? -999) - (a.temp_atual ?? -999));
  else filtered.sort((a, b) => (CRIT_ORDER[a.criticidade] ?? 99) - (CRIT_ORDER[b.criticidade] ?? 99));

  const tbody = document.getElementById('risco-tbody');
  const empty = document.getElementById('risco-empty');
  document.getElementById('risco-count').textContent = filtered.length;

  if (filtered.length === 0) {
    tbody.innerHTML = '';
    empty.style.display = 'flex';
  } else {
    empty.style.display = 'none';
    tbody.innerHTML = filtered.map(d => renderRow(d, historyMap)).join('');
  }
}

function populateLojaFilter(data) {
  const lojas = [...new Set(data.map(d => d.loja_nome).filter(Boolean))].sort();
  const sel = document.getElementById('loja-filter');
  lojas.forEach(l => {
    const opt = document.createElement('option');
    opt.value = l;
    opt.textContent = l;
    sel.appendChild(opt);
  });
}

function updateKPIs(data) {
  document.getElementById('kpi-total').textContent = data.length;

  const critHigh = data.filter(d => d.criticidade === 'C' || d.criticidade === 'A').length;
  const pct = data.length > 0 ? Math.round(critHigh / data.length * 100) : 0;
  document.getElementById('kpi-crit-pct').textContent = pct + '%';

  const semTrat = data.filter(d => d.sem_tratativa).length;
  document.getElementById('kpi-sem-trat').textContent = semTrat;

  const scores = data.map(d => d.risk_score).filter(s => s !== null && s !== undefined);
  const avgScore = scores.length > 0 ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length * 100) : null;
  document.getElementById('kpi-score-medio').textContent = avgScore !== null ? avgScore + '%' : '—';
}

async function loadData() {
  try {
    const res = await fetch('/api/dashboard/risco');
    const json = await res.json();
    if (json.status !== 'ok') throw new Error(json.mensagem);

    allData = json.dados;
    saveScoreHistory(allData);
    document.getElementById('risco-loading').style.display = 'none';
    updateKPIs(allData);
    populateLojaFilter(allData);
    applyFilters();
    document.getElementById('risco-update').innerHTML = `<i class="bi bi-arrow-clockwise"></i> ${new Date().toLocaleTimeString('pt-BR')}`;
    _initExportRisco();
  } catch (err) {
    document.getElementById('risco-loading').innerHTML = `<i class="bi bi-x-circle text-danger" style="font-size:1.5rem"></i><span>Erro ao carregar: ${err.message}</span>`;
  }
}

function abrirChamado(d) {
  abrirChamadoModal(d);
}

let _exportRiscoInit = false;
function _initExportRisco() {
  if (_exportRiscoInit) return;
  _exportRiscoInit = true;
  const ref = document.getElementById('risco-update');
  if (!ref) return;
  const btn = document.createElement('button');
  btn.className = 'btn-action ms-2';
  btn.style.cssText = 'font-size:.72rem;padding:.2rem .55rem';
  btn.innerHTML = '<i class="bi bi-download"></i> CSV';
  btn.onclick = () => {
    const headers = ['Criticidade', 'Dispositivo', 'ID', 'Loja', 'Score ML', 'Temp Atual', 'Erro Temp', 'Volatilidade', 'Degelo %', 'Sem Tratativa'];
    const rows = allData.map(d => [
      d.crit_label,
      d.dispositivo_nome,
      d.dispositivo_id,
      d.loja_nome,
      d.risk_score != null ? (d.risk_score * 100).toFixed(1) + '%' : '',
      d.temp_atual != null ? d.temp_atual + '°C' : '',
      d.temp_erro != null ? d.temp_erro + '°C' : '',
      d.temp_std != null ? d.temp_std + '°C' : '',
      d.degelo_fracao + '%',
      d.sem_tratativa ? 'Sim' : 'Não',
    ]);
    exportarCSV(headers, rows, `mapa_risco_${new Date().toISOString().slice(0,10)}.csv`);
  };
  ref.after(btn);
}

document.querySelectorAll('.crit-check-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const crit = btn.dataset.crit;
    if (activeCrits.has(crit)) {
      activeCrits.delete(crit);
      btn.classList.add('inactive');
    } else {
      activeCrits.add(crit);
      btn.classList.remove('inactive');
    }
    applyFilters();
  });
});

document.getElementById('loja-filter').addEventListener('change', applyFilters);
document.getElementById('sort-filter').addEventListener('change', applyFilters);

loadData();
setInterval(loadData, 60000);
