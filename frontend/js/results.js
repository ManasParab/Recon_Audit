let resultsSort={key:'reference',direction:'asc'};

function resultIsResolved(x){return x.agent?.outcome==='RESOLVED'}
function resultSortValue(x,key){
  if(key==='reference')return String(x.evidence?.reference||'').toLowerCase();
  if(key==='type')return String(exceptionLabels[x.exception_type]||x.exception_type||'').toLowerCase();
  return resultIsResolved(x)?'matched':'review';
}
function sortedResults(items){return [...items].sort((a,b)=>{const left=resultSortValue(a,resultsSort.key),right=resultSortValue(b,resultsSort.key);return (left<right?-1:left>right?1:0)*(resultsSort.direction==='asc'?1:-1)})}
function resultDetail(x){return `<details class="row-details"><summary>Show details</summary><div class="plain-language"><p><b>Flagged because:</b> ${esc(flaggedBecause(x))}</p><p><b>Investigated using:</b> ${esc(investigatedUsing(x))}</p><p><b>Concluded:</b> ${esc(explanationFor(x))}</p></div><table class="evidence-table mt-3"><tbody>${evidenceRows(x).map(([label,value])=>`<tr><th>${esc(label)}</th><td>${esc(value)}</td></tr>`).join('')}</tbody></table></details>`}
function exceptionTable(type,items){
  const rows=sortedResults(items).map(x=>`<tr><td><b>${esc(x.evidence?.reference||'Not provided')}</b><small>${esc(x.order_id||x.matched_txn_ids?.[0]||'Record')}</small></td><td>${exceptionLabels[x.exception_type]||esc(x.exception_type||'Record issue')}</td><td>${statusBadge(x)}</td><td>${resultDetail(x)}</td></tr>`).join('');
  return `<section class="exception-group"><header><b>${exceptionLabels[type]}</b><span>${items.length} record${items.length===1?'':'s'}</span></header><div class="table-wrap"><table class="exception-table"><thead><tr><th><button data-sort="reference" type="button">Reference <span>↕</span></button></th><th><button data-sort="type" type="button">Type <span>↕</span></button></th><th><button data-sort="status" type="button">Status <span>↕</span></button></th><th>Evidence and explanation</th></tr></thead><tbody>${rows}</tbody></table></div></section>`
}
function renderExceptionResults(){
  const type=document.querySelector('#exception-type-filter').value,status=document.querySelector('#exception-status-filter').value;
  const filtered=currentExceptions.filter(x=>(type==='all'||x.exception_type===type)&&(status==='all'||(status==='resolved'?resultIsResolved(x):!resultIsResolved(x))));
  document.querySelector('#exception-count').textContent=`${filtered.length} of ${currentExceptions.length} exception${currentExceptions.length===1?'':'s'}`;
  const groups=Object.keys(exceptionLabels).map(typeName=>[typeName,filtered.filter(x=>x.exception_type===typeName)]).filter(([,items])=>items.length);
  document.querySelector('#exceptions').innerHTML=groups.length?groups.map(([typeName,items])=>exceptionTable(typeName,items)).join(''):'<div class="empty-state">No exceptions match these filters.</div>';
  document.querySelectorAll('[data-sort]').forEach(button=>button.addEventListener('click',()=>{const key=button.dataset.sort;resultsSort=resultsSort.key===key?{key,direction:resultsSort.direction==='asc'?'desc':'asc'}:{key,direction:'asc'};renderExceptionResults()}));
}
function setupResultsTabs(){document.querySelectorAll('.results-tab').forEach(tab=>tab.addEventListener('click',()=>{const target=tab.dataset.tab;document.querySelectorAll('.results-tab').forEach(item=>{const active=item===tab;item.classList.toggle('is-active',active);item.setAttribute('aria-selected',active)});document.querySelectorAll('.tab-panel').forEach(panel=>{const active=panel.dataset.panel===target;panel.classList.toggle('is-active',active);panel.hidden=!active})}))}
function setupExceptionFilters(){const typeFilter=document.querySelector('#exception-type-filter');Object.entries(exceptionLabels).forEach(([value,label])=>typeFilter.insertAdjacentHTML('beforeend',`<option value="${value}">${label}</option>`));[typeFilter,document.querySelector('#exception-status-filter')].forEach(filter=>filter.addEventListener('change',renderExceptionResults));document.querySelector('#clear-exception-filters').addEventListener('click',()=>{typeFilter.value='all';document.querySelector('#exception-status-filter').value='all';renderExceptionResults()})}
async function renderClientResults(){
  const run=JSON.parse(sessionStorage.reconRun||'null');if(!run)return location.href='index.html';
  const m=run.evaluation;document.querySelector('#summary').textContent=`${m.matched_records} of ${m.total_records} orders were matched automatically. Review any exceptions before closing this case.`;
  document.querySelector('#workflow').innerHTML=(run.workflow||[]).map(x=>`<span class="workflow-item">✓ ${esc(x)}</span>`).join('');
  const value=x=>x==null?'Not estimated':x+'%';const cards=[['Automatic match rate',m.match_rate+'%'],['Orders reviewed',m.total_records],['Items needing review',run.results.filter(x=>x.status==='EXCEPTION').length],['Resolution accuracy',value(m.resolution_accuracy)],['Honesty score',value(m.honesty_score)]];
  document.querySelector('#metrics').innerHTML=cards.map(([key,value])=>`<article class="metric"><p>${key}</p><strong>${value}</strong></article>`).join('');
  currentExceptions=run.results.filter(x=>x.status==='EXCEPTION');setupResultsTabs();setupExceptionFilters();renderExceptionResults();document.querySelector('#audit-sequence').innerHTML=currentExceptions.map(x=>`<p>${esc(auditSequence(x))}</p>`).join('');
  if(!run.batch_id){document.querySelector('#uploaded-data').innerHTML='<p class="muted">This was the fixed-seed synthetic demonstration. The hidden answer key was available only to evaluation.</p>';return}
  try{const batch=await request('/batches/'+run.batch_id);document.querySelector('#uploaded-data').innerHTML=`<p class="mb-3 muted">${batch.records.length} normalized records loaded.</p><table class="evidence-table"><thead><tr><th>Source</th><th>Accepted</th><th>Needs attention</th></tr></thead><tbody>${Object.entries(batch.files).map(([source,file])=>`<tr><td>${esc(source)}</td><td>${file.accepted_rows}</td><td>${file.failed_rows||0}</td></tr>`).join('')}</tbody></table>`}catch(e){document.querySelector('#uploaded-data').textContent='File checks are unavailable: '+e.message}
}
