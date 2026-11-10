const brl = v => v.toLocaleString('pt-BR', {style:'currency', currency:'BRL'});
const $ = id => document.getElementById(id);
// Só o token FINAL (após 2FA) é guardado; o intermediário fica apenas em memória.
let token = null, tokenParcial = null, factorId = null;
try { token = sessionStorage.getItem('drm_token'); } catch (e) {}

let tela = 'menu', etapa = 'login';   // etapa: login | mfa | cadastro
function ir(t) { tela = t; mostrar(); if (t === 'lista') carregarLista(); }
function mostrar() {
  $('login').style.display = !token && etapa === 'login' ? 'block' : 'none';
  $('mfa').style.display = !token && etapa === 'mfa' ? 'block' : 'none';
  $('cadastro').style.display = !token && etapa === 'cadastro' ? 'block' : 'none';
  $('menu').style.display = token && tela === 'menu' ? 'block' : 'none';
  $('app').style.display = token && tela === 'calc' ? 'block' : 'none';
  $('lista').style.display = token && tela === 'lista' ? 'block' : 'none';
  document.querySelector('.card').classList.toggle('larga', tela === 'lista' && !!token);
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
  token = t; tokenParcial = null; factorId = null; etapa = 'login'; tela = 'menu';
  try { sessionStorage.setItem('drm_token', token); } catch (e) {}
  ['senha', 'codigo', 'codigo2'].forEach(id => $(id).value = '');
  mostrar();
}
async function entrar(ev) {
  ev.preventDefault();
  $('erro').textContent = '';
  try {
    const {r, d} = await api('/api/login', {method:'POST',
      body: JSON.stringify({email: $('email').value, senha: $('senha').value})});
    if (!r.ok) { $('erro').textContent = (d && d.erro) || 'Não foi possível entrar.'; return; }
    $('senha').value = '';
    if (d.proximo === 'ok') return finalizar(d.token);
    tokenParcial = d.token; factorId = d.factor_id;
    if (d.proximo === 'verificar') { etapa = 'mfa'; mostrar(); $('codigo').focus(); return; }
    const c = await api('/api/mfa', {method:'POST', body: JSON.stringify({acao:'cadastrar'})}, tokenParcial);
    if (!c.r.ok) { $('erro').textContent = (c.d && c.d.erro) || 'Não foi possível ativar o 2FA.'; return; }
    factorId = c.d.factor_id;
    // só aceita imagem SVG em data URI (nunca uma URL externa)
    $('qr').src = /^data:image\/svg\+xml/.test(c.d.qr || '') ? c.d.qr : '';
    $('segredo').textContent = c.d.segredo || '';
    etapa = 'cadastro'; mostrar(); $('codigo2').focus();
  } catch (e) { $('erro').textContent = 'Erro de conexão. Tente de novo.'; }
}
async function verificar(ev, campo, saida) {
  ev.preventDefault();
  $(saida).textContent = '';
  try {
    const {r, d} = await api('/api/mfa', {method:'POST',
      body: JSON.stringify({acao:'verificar', factor_id: factorId, codigo: $(campo).value.trim()})}, tokenParcial);
    if (!r.ok) { $(saida).textContent = (d && d.erro) || 'Não foi possível verificar.'; return; }
    finalizar(d.token);
  } catch (e) { $(saida).textContent = 'Erro de conexão. Tente de novo.'; }
}
function sair(msg) {
  const t = token || tokenParcial;
  if (t) api('/api/logout', {method:'POST', body:'{}'}, t).catch(() => {});  // revoga a sessão no servidor
  token = tokenParcial = factorId = null; etapa = 'login'; tela = 'menu';
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

// ---- eventos (sem handlers inline, para a CSP bloquear scripts injetados) ----
$('login').addEventListener('submit', entrar);
$('mfa').addEventListener('submit', e => verificar(e, 'codigo', 'erro2'));
$('cadastro').addEventListener('submit', e => verificar(e, 'codigo2', 'erro3'));
document.addEventListener('click', e => {
  const el = e.target.closest('[data-ir],[data-acao]');
  if (!el) return;
  if (el.dataset.ir) return ir(el.dataset.ir);
  ({sair: () => sair(), csv: exportarCsv, atualizar: carregarLista, calcular})[el.dataset.acao]();
});
mostrar();
