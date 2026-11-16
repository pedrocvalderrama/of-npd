'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const state = { context: null, order: null, product: null, preview: null, draft: null, lookup: 'pedidos', productVersion: 0, orderVersion: 0, previewVersion: 0, finishEdited: false, today: '', lookupPart: null };
  const requests = new Map();
  let timer, lookupTimer, toastTimer;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const icon = name => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
  const company = () => $('empresa').value || '1';
  const date = value => value ? String(value).slice(0,10).split('-').reverse().join('/') : '—';
  function decimal(value) {
    let text = String(value ?? '0'), neg = text.startsWith('-');
    if (neg) text = text.slice(1);
    let [integer, fraction = ''] = text.split('.');
    fraction = fraction.replace(/0+$/, '');
    return (neg ? '-' : '') + integer.replace(/\B(?=(\d{3})+(?!\d))/g,'.') + (fraction ? ','+fraction : '');
  }
  function inputQuantity(value) { return String(value ?? '').replace('.', ','); }
  function normalizedQuantity(value) {
    const text = String(value).trim();
    if (text.includes(',')) return text.replace(/\./g,'').replace(',','.');
    if (/^\d{1,3}(\.\d{3})+$/.test(text)) return text.replace(/\./g,'');
    return text;
  }
  function updateTotals() {
    let sum = 0n;
    for (const row of $('grade-body').rows) {
      const value = normalizedQuantity(row.querySelector('.qty-input').value);
      if (!/^\d+(?:\.\d{1,3})?$/.test(value)) continue;
      const [i,f=''] = value.split('.');
      sum += BigInt(i)*1000n + BigInt(f.padEnd(3,'0'));
    }
    const total = (sum/1000n).toString()+'.'+(sum%1000n).toString().padStart(3,'0');
    $('grade-total').textContent = $('summary-total').textContent = decimal(total);
    $('summary-start').textContent = date($('inicio').value);
    $('summary-end').textContent = date($('fim').value);
    $('summary-order').textContent = state.order?.numero || '—';
    $('summary-product').textContent = state.product?.codigo || '—';
    $('summary-parts').textContent = document.querySelectorAll('.part-check:checked').length;
  }
  function error(message) {
    $('global-error').textContent = message;
    $('global-error').hidden = !message;
  }
  function toast(message) {
    clearTimeout(toastTimer); $('toast').textContent = message; $('toast').hidden = false;
    toastTimer = setTimeout(() => { $('toast').hidden = true; }, 5000);
  }
  async function api(path, options={}, key) {
    if (key) { requests.get(key)?.abort(); const c = new AbortController(); requests.set(key,c); options.signal=c.signal; }
    const response = await fetch(path, { cache:'no-store', ...options });
    let data;
    try { data = await response.json(); } catch { throw new Error('O servidor não retornou uma resposta válida.'); }
    if (!response.ok) throw new Error(data.error || 'Não foi possível consultar o SISPLAN.');
    return data;
  }
  function fillSelect(id, rows, value, label, preferred) {
    const el = $(id); el.replaceChildren(new Option('Selecione…',''));
    for (const item of rows) el.add(new Option(label(item), String(item[value])));
    if (preferred != null && [...el.options].some(o => o.value===String(preferred))) el.value=String(preferred);
  }
  function addGrade(cor='', tam='', qty='') {
    if ($('grade-body').rows.length >= 100) return toast('A grade aceita até 100 linhas nesta conferência.');
    const tr=document.createElement('tr');
    tr.innerHTML=`<td><input aria-label="Cor da linha" class="color-input" list="colors-list" maxlength="14" placeholder="Cor" value="${esc(cor)}"></td><td><input aria-label="Tamanho da linha" class="size-input" list="sizes-list" maxlength="12" placeholder="Tam." value="${esc(tam)}"></td><td class="numeric"><input aria-label="Quantidade da linha" class="qty-input" inputmode="decimal" autocomplete="off" maxlength="18" placeholder="0" value="${esc(inputQuantity(qty))}" title="Use vírgula para casas decimais"></td><td><button type="button" class="icon-button remove-row" aria-label="Remover linha da grade">${icon('close')}</button></td>`;
    tr.querySelector('.remove-row').onclick=() => { tr.remove(); if (!$('grade-body').rows.length) addGrade(); changed(); };
    tr.addEventListener('input',changed); $('grade-body').append(tr); updateTotals();
  }
  function clearCalculated() {
    state.preview=null; state.draft=null; state.previewVersion++;
    requests.get('preview')?.abort(); $('download').disabled=true;
    $('consumption-table').hidden=true; $('consumption-empty').hidden=false;
    $('calculation-status').textContent=state.product ? 'Preencha a grade' : 'Aguardando produto';
    $('summary-materials').innerHTML='<h3>Materiais previstos</h3><p>Preencha a grade para calcular.</p>';
    $('summary-sector').textContent='—';
  }
  function changed() {
    updateTotals(); clearCalculated(); clearTimeout(timer);
    if (state.product) timer=setTimeout(() => calculate(false),450);
  }
  function invalidateDraft() {
    clearTimeout(timer);state.previewVersion++;requests.get('preview')?.abort();state.preview=null;state.draft=null;$('download').disabled=true;
  }
  function renderParts() {
    const product=state.product;
    if (!product) { $('parts-list').innerHTML='<div class="empty compact">Selecione um produto para carregar as partes e os setores cadastrados.</div>'; $('route-list').replaceChildren(); return; }
    if (!product.partes.length) { $('parts-list').innerHTML='<div class="empty compact">Este produto não possui partes ou fluxo cadastrado.</div>'; $('route-list').replaceChildren(); return; }
    $('parts-list').innerHTML=product.partes.map(p => `<div class="part-block"><div class="part-option"><label class="checkbox"><input type="checkbox" class="part-check" value="${esc(p.id)}" checked><span><strong>Parte ${esc(p.parte)}</strong> · ${esc(p.desc_parte || 'Parte do produto')}</span></label><span class="part-meta"><span>Fluxo <strong>${esc(p.fluxo || '—')}</strong></span><span>Múltiplo ${esc(p.multiplo || 1)}</span></span></div><div class="form-group faction-field"><label for="faccao-${esc(p.id)}">Facção / terceiro da parte ${esc(p.parte)}</label><div class="input-action"><input id="faccao-${esc(p.id)}" class="faction-input" data-part="${esc(p.id)}" value="${esc(product.fornecedor || '')}" maxlength="8" placeholder="Código da entidade"><button type="button" class="input-button faction-search" data-part="${esc(p.id)}" aria-label="Pesquisar facção da parte ${esc(p.parte)}">${icon('search')}</button></div><span class="field-help faction-name">${esc(product.fornecedor_nome || 'Selecione a entidade responsável pela facção.')}</span><span class="field-help">Sugestão do fornecedor do produto; confira a facção para esta ordem.</span></div></div>`).join('');
    document.querySelectorAll('.part-check').forEach(c => c.addEventListener('change',() => { renderRoutes(); changed(); }));
    document.querySelectorAll('.faction-input').forEach(c => c.addEventListener('input',() => { c.closest('.faction-field').querySelector('.faction-name').textContent='O código será validado na conferência.'; changed(); }));
    document.querySelectorAll('.faction-search').forEach(c => c.onclick=()=>{state.lookupPart=c.dataset.part;openLookup('entidades');});
    renderRoutes();
  }
  function renderRoutes() {
    if (!state.product) return;
    const ids=new Set([...document.querySelectorAll('.part-check:checked')].map(c=>c.value));
    $('route-list').innerHTML=state.product.partes.filter(p => ids.has(String(p.id))).map(p => {
      const sectors=state.product.setores.filter(s => s.parte===p.parte && s.fluxo===p.fluxo).sort((a,b)=>(a.ordem ?? 99999)-(b.ordem ?? 99999));
      return `<p class="route-label">FLUXO ${esc(p.fluxo)} · PARTE ${esc(p.parte)}</p><div class="route-steps">${sectors.length ? sectors.map((s,i)=>`${i ? '<span class="route-arrow">→</span>' : ''}<span class="route-step ${i===0?'first':''}"><strong>${esc(s.setor)}</strong> ${esc(s.descricao || 'Setor')}${i===0 ? ' · início' : ''}</span>`).join('') : '<span class="field-help">Nenhum setor cadastrado para esse fluxo.</span>'}</div>`;
    }).join('');
  }
  async function loadOrder(number) {
    if (!state.context) return toast('Aguarde a conexão com o SISPLAN.');
    const version=++state.orderVersion;
    error(''); $('order-help').textContent='Consultando pedido…';
    try {
      const order=await api(`/api/pedidos/${encodeURIComponent(number)}?empresa=${encodeURIComponent(company())}`,{},'order');
      if (version!==state.orderVersion) return;
      state.order=order; $('pedido').value=order.numero;
      $('customer-name').textContent=order.cliente || order.fantasia || order.codcli;
      $('customer-detail').textContent=`Cliente ${order.codcli} · Pedido ${order.numero} · Entrega ${date(order.entrega)}`;
      $('order-status').textContent=`Status ${order.status || '—'}`; $('customer-card').hidden=false;
      $('observacao').value=order.obs || '';
      if ([...$('deposito').options].some(o=>o.value===order.deposito)) $('deposito').value=order.deposito;
      if (!state.finishEdited && order.entrega && String(order.entrega).slice(0,10)>=$('inicio').value) $('fim').value=String(order.entrega).slice(0,10);
      $('order-help').textContent='Pedido carregado. Escolha um produto abaixo ou pesquise outro código.';
      $('order-items').hidden=false; $('order-items').open=true; $('order-item-count').textContent=order.itens.length;
      $('order-items-body').innerHTML=order.itens.map((i,n)=>`<tr><td><strong>${esc(i.codigo)}</strong><small>${esc(i.descricao || 'Produto sem descrição')}</small></td><td>${esc(i.cor || '—')} / ${esc(i.tam || '—')}</td><td class="numeric">${decimal(i.qtde || 0)}</td><td><button class="btn btn-small btn-outline choose-order-product" type="button" data-item="${n}">Selecionar</button></td></tr>`).join('');
      $('order-items-body').querySelectorAll('button').forEach(button=>button.onclick=()=>loadProduct(order.itens[Number(button.dataset.item)].codigo));
      if (state.product && order.itens.some(i=>i.codigo===state.product.codigo)) await loadProduct(state.product.codigo);
      else if (order.itens.length===1) await loadProduct(order.itens[0].codigo);
      changed();
    } catch (exc) {
      if (exc.name==='AbortError') return;
      state.order=null; $('customer-card').hidden=true; $('order-items').hidden=true;
      $('order-help').textContent='Pedido não carregado.'; error(exc.message);
    }
  }
  async function loadProduct(code) {
    const version=++state.productVersion;
    error(''); clearCalculated(); $('calculation-status').textContent='Carregando produto…';
    try {
      const product=await api(`/api/produtos/${encodeURIComponent(code)}`,{},'product');
      if (version!==state.productVersion) return;
      state.product=product; $('produto').value=product.codigo;
      $('product-selected').hidden=false; $('product-code').textContent=product.codigo;
      $('product-description').textContent=product.descricao;
      $('product-unit').textContent=$('grade-unit').textContent=product.unidade || 'UN';
      $('summary-unit').textContent=product.unidade==='UN' ? 'peças' : product.unidade || 'unidades';
      $('sizes-list').innerHTML=product.tamanhos.map(t=>`<option value="${esc(t)}"></option>`).join('');
      $('grade-body').replaceChildren();
      const items=state.order?.itens.filter(i=>i.codigo===product.codigo) || [];
      if (items.length) {
        const grouped=new Map();
        for (const item of items) {
          const key=JSON.stringify([item.cor || '0',item.tam || '0']);
          const value=String(item.qtde || '0'); const [a,b='']=value.split('.');
          const raw=BigInt(a)*1000n+BigInt(b.padEnd(3,'0').slice(0,3));
          grouped.set(key,(grouped.get(key) || 0n)+raw);
        }
        for (const [key,q] of grouped) { const [cor,tam]=JSON.parse(key); addGrade(cor,tam,`${q/1000n}.${String(q%1000n).padStart(3,'0')}`); }
      } else {
        const cor=product.combinacoes[0]?.cor || '';
        addGrade(cor,product.tamanhos[0] || '', '');
      }
      renderParts(); changed();
    } catch (exc) {
      if (exc.name==='AbortError') return;
      state.product=null; $('product-selected').hidden=true; renderParts(); clearCalculated(); error(exc.message);
    }
  }
  function draft() {
    return {produto:state.product?.codigo,pedido:state.order?.numero || '',periodo:$('periodo').value,
      inicio:$('inicio').value,fim:$('fim').value,cadastro:$('cadastro').value,deposito:$('deposito').value,
      tipo_id:$('tipo').value,programacao:$('programacao').value,percentual:$('percentual').value,
      volumes:$('volumes').value,observacao:$('observacao').value,
      gerar_faccao:$('gerar-faccao').checked,gerar_consumos:$('gerar-consumos').checked,
      desconsiderar_fim_semana:$('semana').checked,empresa:company(),
      partes:[...document.querySelectorAll('.part-check:checked')].map(c=>c.value),
      faccoes:Object.fromEntries([...document.querySelectorAll('.faction-input')].map(c=>[c.dataset.part,c.value.trim()])),
      grade:[...$('grade-body').rows].map(r=>({cor:r.querySelector('.color-input').value,tam:r.querySelector('.size-input').value,qtde:normalizedQuantity(r.querySelector('.qty-input').value)})),
      complementos:[...document.querySelectorAll('.complement-input')].map(i=>({codigo:i.dataset.codigo,descricao:i.value,valor:$(`comp-val-${i.dataset.codigo}`).value.replace(',','.')}))};
  }
  function renderCalculation(data) {
    $('summary-total').textContent=$('grade-total').textContent=decimal(data.total_pecas);
    $('summary-sector').textContent=data.roteiros.map(r=>r.primeiro).join(' / ') || '—';
    $('calculation-status').textContent=data.erros.length ? 'Confira os dados' : 'Consumos calculados';
    $('consumption-table').hidden=!data.consumos.length; $('consumption-empty').hidden=!!data.consumos.length;
    if (!data.consumos.length) $('calculation-status').textContent=$('gerar-consumos').checked ? 'Sem consumo calculado' : 'Geração desmarcada';
    $('consumption-body').innerHTML=data.consumos.map(c=>`<tr><td><strong>${esc(c.codigo)}</strong><small>${esc(c.descricao)}</small></td><td>${esc(c.setor || '—')}</td><td>${esc(c.unidade)}</td><td class="numeric">${decimal(c.coeficiente)}</td><td class="numeric"><strong>${decimal(c.quantidade)}</strong></td></tr>`).join('');
    const totals=Object.entries(data.totais_unidade);
    $('summary-materials').innerHTML='<h3>Materiais previstos</h3>'+(totals.length ? totals.map(([unit,total])=>`<div class="material-total"><span>${esc(unit)}</span><strong>${decimal(total)}</strong></div>`).join('') : '<p>Nenhum consumo calculado.</p>');
  }
  function consumptionTable(rows) {
    return `<div class="table-scroll"><table class="data-table"><thead><tr><th>Material</th><th>Setor</th><th class="numeric">Quantidade</th></tr></thead><tbody>${rows.map(r=>`<tr><td><strong>${esc(r.codigo)}</strong><small>${esc(r.descricao)}</small></td><td>${esc(r.setor || '—')}</td><td class="numeric">${decimal(r.quantidade ?? r.consumo)} ${esc(r.unidade || '')}</td></tr>`).join('')}</tbody></table></div>`;
  }
  function showReview(data) {
    $('review-eyebrow').textContent='CONFERÊNCIA · SEM GRAVAÇÃO'; $('review-title').textContent='Conferência da ordem';
    const p=state.product;
    $('review-content').innerHTML=`<div class="review-message">Dados conferidos para consulta. Nenhuma OF foi criada ou número reservado.</div>${data.avisos.length ? `<div class="review-message warning" style="margin-top:12px"><strong>Pontos para conferir</strong><ul>${data.avisos.map(a=>`<li>${esc(a)}</li>`).join('')}</ul></div>` : ''}<div class="review-grid" style="margin-top:18px"><div class="review-stat"><span>QUANTIDADE</span><strong>${decimal(data.total_pecas)} ${esc(p.unidade || '')}</strong></div><div class="review-stat"><span>PARTES</span><strong>${data.roteiros.length}</strong></div><div class="review-stat"><span>PRIMEIRO SETOR</span><strong>${esc(data.roteiros.map(r=>r.primeiro).join(' / ') || '—')}</strong></div></div><div class="review-facts"><div><span>Produto</span>${esc(p.codigo)} · ${esc(p.descricao)}</div><div><span>Pedido / cliente</span>${esc(state.order?.numero || 'Sem pedido')} · ${esc(state.order?.cliente || '')}</div><div><span>Período de produção</span>${date($('inicio').value)} a ${date($('fim').value)}</div><div><span>Depósito</span>${esc($('deposito').selectedOptions[0]?.text || '')}</div></div><section class="review-section"><h3>Consumos previstos</h3>${data.consumos.length ? consumptionTable(data.consumos) : '<p class="field-help">Nenhum consumo nesta conferência.</p>'}</section><section class="review-section"><h3>Observações</h3><div class="review-observation">${esc($('observacao').value || 'Sem observações.')}</div></section>`;
    $('review-dialog').showModal();
  }
  async function calculate(show=false) {
    clearTimeout(timer);
    if (!$('empresa').value) { if(show)error('Selecione a empresa antes de conferir.'); return; }
    if (!state.product || $('produto').value!==state.product.codigo) { if(show) error('Selecione e carregue um produto antes de conferir.'); return; }
    if ($('pedido').value && (!state.order || state.order.numero!==$('pedido').value)) { if(show) error('Carregue o pedido informado antes de conferir.'); return; }
    const payload=draft(); const version=++state.previewVersion;
    $('calculation-status').textContent='Calculando…';
    try {
      const data=await api(`/api/conferencia?empresa=${encodeURIComponent(company())}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)},'preview');
      if (version!==state.previewVersion) return;
      state.preview=data; state.draft=payload; renderCalculation(data); $('download').disabled=!data.conferido;
      if (show) {
        if (data.erros.length) { error(data.erros.join(' ')); $('global-error').scrollIntoView({behavior:'smooth',block:'center'}); }
        else { error(''); showReview(data); }
      }
    } catch (exc) {
      if (exc.name==='AbortError') return;
      $('calculation-status').textContent='Conferência pendente'; $('download').disabled=true;
      if (show) error(exc.message);
    }
  }
  async function lookupSearch() {
    const term=$('lookup-search').value.trim(); $('lookup-message').textContent='Consultando o SISPLAN…';
    $('lookup-results').innerHTML='<div class="empty compact">Carregando resultados…</div>';
    try {
      const data=await api(`/api/${state.lookup}?q=${encodeURIComponent(term)}&empresa=${encodeURIComponent(company())}`,{},'lookup');
      $('lookup-message').textContent=data.more ? 'Mostrando os primeiros 30 resultados. Refine sua pesquisa.' : `${data.items.length} resultado(s) encontrado(s).`;
      $('lookup-results').innerHTML=data.items.length ? data.items.map((item,n)=>`<button type="button" class="lookup-item" data-index="${n}"><span><span class="lookup-code">${esc(item.numero || item.codigo)}</span><strong>${esc(item.cliente || item.descricao || 'Sem descrição')}</strong><small>${state.lookup==='pedidos' ? `${esc(item.fantasia || '')} · Entrega ${date(item.entrega)} · Status ${esc(item.status || '—')}` : state.lookup==='entidades' ? `${esc(item.fantasia || '')} · Cadastro de entidades` : `${esc(item.unidade || '')} · ${item.ativo==='N' ? 'Inativo' : 'Cadastro de produto'}`}</small></span>${icon('arrow')}</button>`).join('') : '<div class="empty"><strong>Nenhum resultado</strong><p>Confira o código, o nome ou a empresa selecionada.</p></div>';
      $('lookup-results').querySelectorAll('button').forEach(button=>button.onclick=()=>{ const item=data.items[Number(button.dataset.index)]; $('lookup-dialog').close(); if(state.lookup==='entidades') { const input=$(`faccao-${state.lookupPart}`); if(input){input.value=item.codigo;input.closest('.faction-field').querySelector('.faction-name').textContent=item.descricao;changed();} } else {state.lookup==='pedidos' ? loadOrder(item.numero) : loadProduct(item.codigo);} });
    } catch (exc) {
      if (exc.name==='AbortError') return;
      $('lookup-message').textContent='Consulta não concluída.'; $('lookup-results').innerHTML=`<div class="alert error" role="alert">${esc(exc.message)}</div>`;
    }
  }
  function openLookup(kind) {
    if (!state.context) return toast('Aguarde a conexão com o SISPLAN.');
    state.lookup=kind; $('lookup-title').textContent=kind==='pedidos' ? 'Pesquisar pedido' : kind==='entidades' ? 'Pesquisar facção / terceiro' : 'Pesquisar produto';
    $('lookup-label').textContent=kind==='pedidos' ? 'Número do pedido ou nome do cliente' : kind==='entidades' ? 'Código ou nome da entidade' : 'Código ou descrição do produto';
    $('lookup-search').value=kind==='pedidos' ? $('pedido').value : kind==='entidades' ? $(`faccao-${state.lookupPart}`).value : $('produto').value;
    $('lookup-dialog').showModal(); $('lookup-search').focus(); lookupSearch();
  }
  async function existingSearch() {
    $('existing-message').textContent='Consultando ordens no SISPLAN…';
    try {
      const data=await api(`/api/ofs?q=${encodeURIComponent($('existing-search').value.trim())}&empresa=${encodeURIComponent(company())}`,{},'existing');
      $('existing-message').textContent=`${data.items.length} ordem(ns) encontrada(s).${data.more?' Refine a pesquisa para ver outros resultados.':''}`;
      $('existing-body').innerHTML=data.items.length ? data.items.map(o=>`<tr><td><strong class="of-code">${esc(o.numero)}</strong></td><td><strong>${esc(o.codigo)}</strong><small>${esc(o.descricao)}</small></td><td>${esc(o.pedido || '—')}</td><td>${date(o.dt_inicio)}<small>${date(o.dt_final)}</small></td><td class="numeric">${decimal(o.ativos || 0)}</td><td><span class="tag ${o.finalizado==='S'?'green':'blue'}">${o.finalizado==='S'?'Finalizada':'Em andamento'}</span></td><td><button class="btn btn-small btn-outline" type="button" data-of="${esc(o.numero)}">Consultar</button></td></tr>`).join('') : '<tr><td colspan="7"><div class="empty">Nenhuma OF encontrada com esses filtros.</div></td></tr>';
      $('existing-body').querySelectorAll('button').forEach(b=>b.onclick=()=>showExisting(b.dataset.of));
    } catch (exc) { if(exc.name!=='AbortError') { $('existing-message').textContent=exc.message; $('existing-body').replaceChildren(); } }
  }
  async function showExisting(number) {
    try {
      const o=await api(`/api/ofs/${encodeURIComponent(number)}?empresa=${encodeURIComponent(company())}`);
      $('review-eyebrow').textContent='CONSULTA AO SISPLAN'; $('review-title').textContent=`Ordem de facção ${o.numero}`;
      $('review-content').innerHTML=`<div class="review-grid"><div class="review-stat"><span>QUANTIDADE</span><strong>${decimal(o.ativos || 0)}</strong></div><div class="review-stat"><span>PEDIDO</span><strong>${esc(o.pedido || '—')}</strong></div><div class="review-stat"><span>SITUAÇÃO</span><strong>${o.finalizado==='S'?'Finalizada':'Em andamento'}</strong></div></div><div class="review-facts"><div><span>Produto</span>${esc(o.codigo)} · ${esc(o.descricao)}</div><div><span>Cliente</span>${esc(o.cliente || o.codcli || '—')}</div><div><span>Início / fim</span>${date(o.dt_inicio)} a ${date(o.dt_final)}</div><div><span>Cadastro / operador</span>${date(o.data_cad)} · ${esc(o.usuario || '—')}</div></div><section class="review-section"><h3>Grade registrada</h3><div class="table-scroll"><table class="data-table"><thead><tr><th>Cor</th><th>Tamanho</th><th class="numeric">Quantidade</th></tr></thead><tbody>${o.grade.map(g=>`<tr><td>${esc(g.cor)}</td><td>${esc(g.tam)}</td><td class="numeric">${decimal(g.qtde || 0)}</td></tr>`).join('')}</tbody></table></div></section><section class="review-section"><h3>Setores registrados</h3><div class="route-steps">${o.setores.map(s=>`<span class="route-step ${s.ordem===1?'first':''}"><strong>${esc(s.setor)}</strong> ${esc(s.descricao)}</span>`).join('')}</div></section><section class="review-section"><h3>Consumos registrados</h3>${o.consumos.length ? consumptionTable(o.consumos) : '<p class="field-help">Sem consumos registrados.</p>'}</section><section class="review-section"><h3>Observações</h3><div class="review-observation">${esc(o.observacao || 'Sem observações.')}</div></section>`;
      $('review-dialog').showModal();
    } catch(exc) { toast(exc.message); }
  }
  function page(existing) {
    $('page-new').hidden=existing; $('page-existing').hidden=!existing;
    $('nav-new').classList.toggle('active',!existing); $('nav-existing').classList.toggle('active',existing);
    $('nav-new').setAttribute('aria-current',existing ? 'false' : 'page'); $('nav-existing').setAttribute('aria-current',existing ? 'page' : 'false');
    if (existing) existingSearch(); window.scrollTo({top:0,behavior:'smooth'});
  }
  function reset() {
    state.productVersion++;state.orderVersion++;state.order=null;state.product=null;state.finishEdited=false;
    ['order','product','preview'].forEach(key=>requests.get(key)?.abort());
    ['pedido','produto','observacao'].forEach(id=>$(id).value='');
    ['cadastro','inicio','fim'].forEach(id=>$(id).value=state.today);
    $('programacao').value='00000000';$('percentual').value='0';$('volumes').value='0';$('deposito').value='';
    ['gerar-faccao','gerar-consumos','semana'].forEach(id=>$(id).checked=true);
    if(state.context){$('periodo').value='99';$('tipo').value=String(state.context.tipos.find(t=>t.descricao==='NORMAL')?.id || '');}
    document.querySelectorAll('.complement-input').forEach(input=>{input.value=state.context?.complementos.find(c=>String(c.codigo)===input.dataset.codigo)?.descricao || '';});
    document.querySelectorAll('.complement-value').forEach(input=>{input.value=inputQuantity(state.context?.complementos.find(c=>String(c.codigo)===input.dataset.codigo)?.valor || '0');});
    ['customer-card','product-selected','order-items'].forEach(id=>$(id).hidden=true);
    $('order-help').textContent='Busque pelo número ou pelo cliente.';
    $('grade-body').replaceChildren();addGrade();renderParts();clearCalculated();error('');updateTotals();
    toast('Formulário limpo. Nenhuma informação foi alterada no ERP.');
  }
  async function boot() {
    const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Sao_Paulo',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
    const take=type=>parts.find(p=>p.type===type).value;
    const today=`${take('year')}-${take('month')}-${take('day')}`;
    state.today=today;
    ['cadastro','inicio','fim'].forEach(id=>$(id).value=today);addGrade();
    try {
      const context=await api('/api/contexto');state.context=context;
      fillSelect('empresa',context.empresas,'id',e=>`${e.id} · ${e.nome || e.razao}`,1);
      fillSelect('periodo',context.periodos,'codigo',p=>`${p.codigo} · ${p.descricao}`,'99');
      fillSelect('tipo',context.tipos,'id',t=>`${t.id} · ${t.descricao}`,context.tipos.find(t=>t.descricao==='NORMAL')?.id);
      fillSelect('deposito',context.depositos,'codigo',d=>`${d.codigo} · ${d.descricao}`);
      $('colors-list').innerHTML=context.cores.map(c=>`<option value="${esc(c.codigo)}">${esc(c.descricao)}</option>`).join('');
      $('complement-count').textContent=`${context.complementos.length} campos`;
      $('complements-grid').innerHTML=context.complementos.map(c=>`<div class="complement-block span-2"><div class="form-group"><label for="comp-${esc(c.codigo)}">${esc(c.codigo)} · ${esc(c.campo)}</label><input class="complement-input" id="comp-${esc(c.codigo)}" data-codigo="${esc(c.codigo)}" maxlength="130" value="${esc(c.descricao || '')}" placeholder="Descrição"></div><div class="form-group complement-number"><label for="comp-val-${esc(c.codigo)}">Valor · ${esc(c.campo)}</label><input class="complement-value" id="comp-val-${esc(c.codigo)}" data-codigo="${esc(c.codigo)}" inputmode="decimal" maxlength="9" value="${esc(inputQuantity(c.valor || '0'))}"></div></div>`).join('');
      $('connection').className='connection online';$('connection').innerHTML='<span class="status-dot"></span>Conectado ao SISPLAN';
    } catch(exc) {
      $('connection').className='connection offline';$('connection').innerHTML='<span class="status-dot"></span>SISPLAN indisponível';
      error(exc.message);
    }
    updateTotals();
  }
  $('find-order').onclick=()=>openLookup('pedidos');$('find-product').onclick=()=>openLookup('produtos');
  $('pedido').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault(); /^\d+$/.test(e.target.value.trim()) ? loadOrder(e.target.value.trim()) : openLookup('pedidos');}});
  $('pedido').addEventListener('change',e=>{if(/^\d{3,16}$/.test(e.target.value.trim()) && e.target.value!==state.order?.numero)loadOrder(e.target.value.trim());});
  $('produto').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault(); /^[\d.]{3,40}$/.test(e.target.value.trim()) ? loadProduct(e.target.value.trim()) : openLookup('produtos');}});
  $('produto').addEventListener('change',e=>{if(/^[\d.]{3,40}$/.test(e.target.value.trim()) && e.target.value!==state.product?.codigo)loadProduct(e.target.value.trim());});
  $('produto').addEventListener('input',()=>{clearCalculated();});
  $('empresa').addEventListener('change',reset);
  ['inicio','fim','periodo','deposito','tipo','gerar-faccao','gerar-consumos','semana'].forEach(id=>$(id).addEventListener('change',changed));
  $('fim').addEventListener('input',()=>state.finishEdited=true);
  ['programacao','percentual','volumes','observacao'].forEach(id=>$(id).addEventListener('input',invalidateDraft));
  $('complements-grid').addEventListener('input',invalidateDraft);
  $('add-grade').onclick=()=>{addGrade();changed();};$('clear-form').onclick=reset;
  $('review').onclick=$('review-top').onclick=()=>calculate(true);
  $('lookup-button').onclick=lookupSearch;$('lookup-search').addEventListener('input',()=>{clearTimeout(lookupTimer);lookupTimer=setTimeout(lookupSearch,300);});
  $('lookup-search').addEventListener('keydown',e=>{if(e.key==='Enter')lookupSearch();});
  document.querySelectorAll('[data-close]').forEach(button=>button.onclick=()=>$(button.dataset.close).close());
  $('nav-new').onclick=$('back-new').onclick=()=>page(false);$('nav-existing').onclick=()=>page(true);
  $('existing-search-button').onclick=existingSearch;$('existing-search').addEventListener('keydown',e=>{if(e.key==='Enter')existingSearch();});
  $('download').onclick=()=>{
    if(!state.preview?.conferido || !state.draft)return;
    const data={tipo:'conferencia_sem_gravacao',numero_of:null,entrada:state.draft,conferencia:state.preview};
    const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json;charset=utf-8'}));
    const a=document.createElement('a');a.href=url;a.download=`conferencia-of-${state.product.codigo}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  boot();
})();
