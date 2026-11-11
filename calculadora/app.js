const brl = v => v.toLocaleString('pt-BR', {style:'currency', currency:'BRL'});
const $ = id => document.getElementById(id);
let token = null;
try { token = sessionStorage.getItem('drm_token'); } catch (e) {}

let tela = 'menu';
function ir(t) { tela = t; mostrar(); if (t === 'lista') carregarLista(); if (t === 'os') carregarOS(); }
function mostrar() {
  $('login').style.display = !token ? 'block' : 'none';
  $('menu').style.display = token && tela === 'menu' ? 'block' : 'none';
  $('app').style.display = token && tela === 'calc' ? 'block' : 'none';
  $('lista').style.display = token && tela === 'lista' ? 'block' : 'none';
  $('os').style.display = token && tela === 'os' ? 'block' : 'none';
  $('osform').style.display = token && tela === 'osform' ? 'block' : 'none';
  document.querySelector('.card').classList.toggle('larga', ['lista', 'os', 'osform'].includes(tela) && !!token);
}
async function api(caminho, opcoes = {}, tk) {
  const h = {'Content-Type':'application/json'};
  if (tk) h['Authorization'] = 'Bearer ' + tk;
  const r = await fetch(caminho, {...opcoes, headers: h});
  let d = null;
  try { d = await r.json(); } catch (e) {}
  return {r, d};
}
function finalizar(t) {
  token = t; tela = 'menu';
  try { sessionStorage.setItem('drm_token', token); } catch (e) {}
  $('senha').value = '';
  mostrar();
}
async function entrar(ev) {
  ev.preventDefault();
  $('erro').textContent = '';
  try {
    const {r, d} = await api('/api/login', {method:'POST',
      body: JSON.stringify({email: $('email').value, senha: $('senha').value})});
    if (!r.ok) { $('erro').textContent = (d && d.erro) || 'Não foi possível entrar.'; return; }
    finalizar(d.token);
  } catch (e) { $('erro').textContent = 'Erro de conexão. Tente de novo.'; }
}
function sair(msg) {
  if (token) api('/api/logout', {method:'POST', body:'{}'}, token).catch(() => {});  // revoga a sessão no servidor
  token = null; tela = 'menu';
  try { sessionStorage.removeItem('drm_token'); } catch (e) {}
  $('res').style.display = 'none';
  mostrar();
  $('erro').textContent = typeof msg === 'string' ? msg : '';
}
async function calcular() {
  const body = {
    custo: parseFloat($('custo').value) || 0,
    motoboy: parseFloat($('motoboy').value) || 0,
    mao_de_obra: parseFloat($('mao').value) || 0,
    modelo: $('modelo').value,
    qualidade: $('qualidade').value,
  };
  const {r, d} = await api('/api/calcular', {method:'POST', body: JSON.stringify(body)}, token);
  if (r.status === 401) { sair('Sessão expirada. Entre novamente.'); return; }
  if (!r.ok) { alert((d && d.erro) || 'Não foi possível calcular.'); return; }
  $('titulo').textContent = ($('modelo').value || 'Sem modelo') + ' — tela ' + $('qualidade').value;
  $('r_custo').textContent = brl(d.custo);
  $('r_moto').textContent = brl(d.motoboy);
  $('r_mao').textContent = brl(d.mao_de_obra);
  $('r_taxa').textContent = brl(d.taxa_cartao_valor);
  $('r_final').textContent = brl(d.preco_final);
  $('res').style.display = 'block';
}

/* ---- Lista de valores (estilo planilha) ---- */
const COLS = [
  {k:'criado_em', t:'Data', f:v => { const d = new Date(v.replace(' ','T') + (/[zZ+]/.test(v.slice(10)) ? '' : 'Z')); return isNaN(d) ? v : d.toLocaleString('pt-BR'); }},
  {k:'modelo', t:'Modelo'},
  {k:'qualidade', t:'Qualidade de tela'},
  {k:'custo', t:'Custo', n:1},
  {k:'motoboy', t:'Motoboy', n:1},
  {k:'mao_de_obra', t:'Mão de obra', n:1},
  {k:'taxa_cartao_valor', t:'Taxa cartão', n:1},
  {k:'preco_final', t:'Preço final', n:1, fin:1},
];
let dados = [], ordem = {k:'criado_em', dir:-1};
const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
const celula = (c, d) => c.n ? brl(d[c.k]) : c.f ? c.f(d[c.k]) : (d[c.k] ?? '');

async function carregarLista() {
  $('resumo').textContent = 'Carregando…';
  try {
    const r = await fetch('/api/historico', {headers:{'Authorization':'Bearer ' + token}});
    if (r.status === 401) { sair('Sessão expirada. Entre novamente.'); return; }
    if (!r.ok) { $('resumo').textContent = 'Não foi possível carregar a lista.'; return; }
    dados = await r.json();
  } catch (e) { $('resumo').textContent = 'Erro de conexão.'; return; }
  const atual = $('fq').value;
  const quals = [...new Set(dados.map(d => d.qualidade).filter(Boolean))].sort();
  $('fq').innerHTML = '<option value="">Todas as qualidades</option>' + quals.map(q => '<option>' + esc(q) + '</option>').join('');
  $('fq').value = atual;
  renderLista();
}
function filtrar() {
  const termos = $('q').value.toLowerCase().split(/\s+/).filter(Boolean), fq = $('fq').value;
  const l = dados.filter(d => {
    if (fq && d.qualidade !== fq) return false;
    const txt = COLS.map(c => celula(c, d) + (c.n ? ' ' + d[c.k] : '')).join(' ').toLowerCase();
    return termos.every(t => txt.includes(t));
  });
  const {k, dir} = ordem;
  l.sort((a, b) => (typeof a[k] === 'number' ? a[k] - b[k] : String(a[k]).localeCompare(String(b[k]), 'pt-BR', {numeric:true})) * dir);
  return l;
}
function renderLista() {
  $('cab').innerHTML = COLS.map(c => '<th data-k="' + c.k + '">' + c.t + (ordem.k === c.k ? (ordem.dir > 0 ? ' ▲' : ' ▼') : '') + '</th>').join('');
  const l = filtrar();
  $('corpo').innerHTML = l.map(d => '<tr>' + COLS.map(c =>
    '<td class="' + (c.n ? 'n ' : '') + (c.fin ? 'f' : '') + '">' + esc(celula(c, d)) + '</td>').join('') + '</tr>').join('');
  const media = l.length ? l.reduce((s, d) => s + d.preco_final, 0) / l.length : 0;
  $('resumo').textContent = l.length + ' de ' + dados.length + ' registros · preço final médio ' + brl(media);
}
// Evita "injeção de fórmulas": células que começam com = + - @ viram texto no Excel.
const csvSeguro = v => /^[=+\-@\t\r]/.test(String(v)) ? "'" + v : String(v);
function exportarCsv() {
  const linhas = filtrar().map(d => COLS.map(c => c.n ? String(d[c.k]).replace('.', ',') : '"' + csvSeguro(celula(c, d)).replace(/"/g, '""') + '"').join(';'));
  const csv = [COLS.map(c => c.t).join(';'), ...linhas].join('\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob(['﻿' + csv], {type:'text/csv'}));
  a.download = 'lista-de-valores.csv'; a.click();
}
$('cab').onclick = e => { const k = e.target.dataset.k; if (!k) return; ordem = {k, dir: ordem.k === k ? -ordem.dir : 1}; renderLista(); };
$('corpo').onclick = e => { const tr = e.target.closest('tr'); if (tr) tr.classList.toggle('sel'); };
$('q').oninput = renderLista; $('fq').onchange = renderLista;

/* ---- Ordens de serviço ---- */
const TEXTOS_OS = ['cliente_nome','cliente_tel','cliente_doc','marca','modelo','cor','imei','senha_aparelho',
  'acessorios','estado_aparelho','defeito','laudo','tecnico','previsao','observacao','forma_pagto','status'];
const NUMS_OS = ['valor_pecas','valor_servico','desconto'];
let ordens = [], statusOS = [], filtroOS = '', osAtual = null;
const dataBR = v => { const d = new Date(String(v).replace(' ','T') + (/[zZ+]/.test(String(v).slice(10)) ? '' : 'Z')); return isNaN(d) ? v : d.toLocaleDateString('pt-BR'); };
const dataHoraBR = v => { const d = new Date(String(v).replace(' ','T') + (/[zZ+]/.test(String(v).slice(10)) ? '' : 'Z')); return isNaN(d) ? v : d.toLocaleString('pt-BR'); };
const valorOS = id => parseFloat($(id).value) || 0;

async function chamarOS(caminho, metodo, corpo) {
  const {r, d} = await api(caminho, {method: metodo, body: corpo ? JSON.stringify(corpo) : undefined}, token);
  if (r.status === 401) { sair('Sessão expirada. Entre novamente.'); return null; }
  if (!r.ok) throw new Error((d && d.erro) || 'Não foi possível concluir.');
  return d;
}
async function carregarOS() {
  $('osresumo').textContent = 'Carregando…';
  try {
    const d = await chamarOS('/api/ordens', 'GET');
    if (!d) return;
    ordens = d.ordens; statusOS = d.status;
    if (!$('f_status').options.length) statusOS.forEach(s => $('f_status').add(new Option(s, s)));
    renderOS();
  } catch (e) { $('osresumo').textContent = 'Não foi possível carregar as ordens.'; }
}
function renderOS() {
  const abertas = ordens.filter(o => !['Entregue', 'Cancelada'].includes(o.status));
  const receber = ordens.filter(o => o.status !== 'Cancelada' && !o.pago).reduce((s, o) => s + o.total, 0);
  const mes = new Date().toISOString().slice(0, 7);
  const recebido = ordens.filter(o => o.pago && o.atualizado_em.startsWith(mes)).reduce((s, o) => s + o.total, 0);
  $('oskpis').innerHTML = [['Em aberto', abertas.length], ['Prontas p/ retirar', ordens.filter(o => o.status === 'Pronto').length],
    ['A receber', brl(receber)], ['Recebido no mês', brl(recebido)]].map(([t, v]) => '<div class="kpi">' + t + '<b>' + esc(v) + '</b></div>').join('');
  $('oschips').innerHTML = ['', ...statusOS].map(s => '<button type="button" data-fos="' + esc(s) + '" class="' + (filtroOS === s ? 'on' : '') + '">' +
    esc(s || 'Todas') + ' (' + (s ? ordens.filter(o => o.status === s).length : ordens.length) + ')</button>').join('');
  const q = $('osq').value.toLowerCase();
  const l = ordens.filter(o => (!filtroOS || o.status === filtroOS) &&
    (!q || [o.id, o.cliente_nome, o.cliente_tel, o.marca, o.modelo, o.imei, o.defeito].join(' ').toLowerCase().includes(q)));
  $('oscorpo').innerHTML = l.map(o => '<tr data-os="' + o.id + '"><td>#' + o.id + '</td><td>' + esc(dataBR(o.criado_em)) + '</td><td>' + esc(o.cliente_nome) +
    '</td><td>' + esc(o.cliente_tel) + '</td><td>' + esc((o.marca + ' ' + o.modelo).trim()) + '</td><td>' + esc(o.defeito.slice(0, 40)) +
    '</td><td><span class="tag ' + (['Pronto', 'Entregue'].includes(o.status) ? 'ok' : o.status === 'Cancelada' ? 'cancelada' : '') + '">' + esc(o.status) +
    '</span></td><td class="n">' + brl(o.total) + '</td><td>' + (o.pago ? 'Sim' : '<span class="pend">Não</span>') + '</td></tr>').join('') ||
    '<tr><td colspan="9">Nenhuma OS encontrada</td></tr>';
  $('osresumo').textContent = l.length + ' de ' + ordens.length + ' ordens';
}
async function abrirOS(id) {
  $('oserro').textContent = ''; $('oshist').innerHTML = ''; osAtual = null;
  for (const c of TEXTOS_OS) $('f_' + c).value = '';
  $('f_garantia_dias').value = 90; $('f_pago').checked = false;
  $('f_total').value = 0; $('f_status').value = 'Aberta';
  if (id) {
    try {
      const d = await chamarOS('/api/ordens?id=' + id, 'GET');
      if (!d) return;
      osAtual = d;
      for (const c of [...TEXTOS_OS, 'garantia_dias', 'total']) $('f_' + c).value = d[c];
      $('f_pago').checked = d.pago;
      $('oshist').innerHTML = d.historico.map(h => '<li>' + esc(dataHoraBR(h.criado_em)) + ' — ' + esc(h.texto) + '</li>').join('');
    } catch (e) { alert(e.message); return; }
  }
  $('ostitulo').textContent = id ? 'OS #' + id : 'Nova OS';
  $('osimprimir').style.display = id ? '' : 'none';
  tela = 'osform'; mostrar();
}
async function salvarOS(ev) {
  ev.preventDefault(); $('oserro').textContent = '';
  const corpo = {pago: $('f_pago').checked, garantia_dias: parseInt($('f_garantia_dias').value, 10) || 0};
  TEXTOS_OS.forEach(c => corpo[c] = $('f_' + c).value);
  // só o valor final: ele vira o total da OS (peças e desconto ficam zerados)
  Object.assign(corpo, {valor_pecas: 0, desconto: 0, valor_servico: valorOS('f_total')});
  try {
    const d = await chamarOS(osAtual ? '/api/ordens?id=' + osAtual.id : '/api/ordens', osAtual ? 'PUT' : 'POST', corpo);
    if (d) ir('os');
  } catch (e) { $('oserro').textContent = e.message; }
}
function imprimirOS() {
  const o = osAtual; if (!o) return;
  const lin = (t, v) => '<tr><th>' + t + '</th><td>' + (esc(v) || '&nbsp;') + '</td></tr>';
  $('impressao').innerHTML = '<h2>DRM Cell — Ordem de Serviço #' + o.id + '</h2><p>Entrada: ' + esc(dataBR(o.criado_em)) + ' · Status: ' + esc(o.status) + '</p><table>' +
    lin('Cliente', o.cliente_nome) + lin('Telefone', o.cliente_tel) + lin('Aparelho', (o.marca + ' ' + o.modelo + ' ' + o.cor).trim()) +
    lin('IMEI / Série', o.imei) + lin('Acessórios', o.acessorios) + lin('Estado do aparelho', o.estado_aparelho) +
    lin('Defeito relatado', o.defeito) + lin('Serviço realizado', o.laudo) + lin('Valor final', brl(o.total)) +
    lin('Garantia', o.garantia_dias + ' dias') + lin('Previsão', o.previsao) + '</table><p>______________________________ Assinatura do cliente</p>';
  window.print();
}
function exportarOS() {
  const cols = ['id', 'criado_em', 'cliente_nome', 'cliente_tel', 'marca', 'modelo', 'imei', 'defeito', 'status', 'total', 'pago'];
  const csv = [cols.join(';'), ...ordens.map(o => cols.map(c => '"' + csvSeguro(c === 'total' ? String(o[c]).replace('.', ',') : o[c]).replace(/"/g, '""') + '"').join(';'))].join('\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob(['﻿' + csv], {type:'text/csv'}));
  a.download = 'ordens-de-servico.csv'; a.click();
}
$('osq').oninput = renderOS;
$('osform').addEventListener('submit', salvarOS);
$('oscorpo').onclick = e => { const tr = e.target.closest('tr[data-os]'); if (tr) abrirOS(tr.dataset.os); };
$('oschips').onclick = e => { const b = e.target.closest('[data-fos]'); if (b) { filtroOS = b.dataset.fos; renderOS(); } };

// ---- eventos (sem handlers inline, para a CSP bloquear scripts injetados) ----
$('login').addEventListener('submit', entrar);
document.addEventListener('click', e => {
  const el = e.target.closest('[data-ir],[data-acao]');
  if (!el) return;
  if (el.dataset.ir) return ir(el.dataset.ir);
  ({sair: () => sair(), csv: exportarCsv, atualizar: carregarLista, calcular,
    osnova: () => abrirOS(null), osatualizar: carregarOS, oscsv: exportarOS, osimprimir: imprimirOS})[el.dataset.acao]();
});
mostrar();
