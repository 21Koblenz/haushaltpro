'use strict';
// Use the actual renderers, observer, translations and form submissions. Canvas
// spies inspect drawn labels; they do not replace a visual browser check.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const {fixture,settle,emptyList}=require('./helpers/ui-fixture.cjs');
const source=name=>fs.readFileSync(path.join(__dirname,'../static',name),'utf8');
const privateOptions={storage:{hp_hide_values:'1',hp_lang:'de'}};
function mockCanvas(f,id){
  const canvas=f.$(id),labels=[];
  const ctx=new Proxy({measureText:text=>({width:String(text).length*7}),fillText:text=>labels.push(String(text))},{
    get:(target,key)=>key in target?target[key]:()=>{}
  });
  canvas.getContext=()=>ctx;
  canvas.getBoundingClientRect=canvas.parentElement.getBoundingClientRect=()=>({width:360,height:280,left:0,top:0});
  Object.defineProperty(canvas,'clientWidth',{value:360});Object.defineProperty(canvas,'clientHeight',{value:280});
  return {canvas,labels};
}
const financial=/(?:\d[\d.,\s]*(?:€|EUR|%)|€\s*\d)/;
function assertMasked(root){
  assert.doesNotMatch(root.textContent,financial);
  for(const el of [root,...root.querySelectorAll('[title],[aria-label],[aria-valuetext],[alt],[placeholder]')]){
    for(const attr of ['title','aria-label','aria-valuetext','alt','placeholder'])assert.doesNotMatch(el.getAttribute(attr)||'',financial,attr);
  }
}

test('fixed masks cover signed German/English, compact, EUR and percent values without hiding dates or counts',async t=>{
  const f=await fixture(t,privateOptions),privacy=f.w.HaushaltProPrivacy;
  for(const raw of ['0 €','-1.234,56 €','+1,234.56 EUR','−12\u202f345,67 €','€1,234.56','-€ 12.34','EUR -12,34','12.5%','-100 %','1.2m €','1,2 Mio. €','999 Tsd. €','€ 2.5 million','12\u00a0345 €',"1’234.56 €"]){
    assert.equal(privacy.displayText(raw),raw.includes('%')?'**** %':'**** €',raw);
  }
  const line='17.09.2026 · 12 Buchungen · -1.234,56 € · 25,5 % · 2026-10-01';
  assert.equal(privacy.displayText(line),'17.09.2026 · 12 Buchungen · **** € · **** % · 2026-10-01');
  assert.equal(privacy.displayNumber('1,2 Mio.'),'****');
  privacy.setHidden(false);assert.equal(privacy.displayText(line),line);
  assert.equal(privacy.displayNumber('1,2 Mio.'),'1,2 Mio.');
});

test('preference survives reload, both controls and cross-tab changes work without network or storage access',async t=>{
  const f=await fixture(t,privateOptions),privacy=f.w.HaushaltProPrivacy;
  assert.equal(privacy.hidden(),true);assert.equal(f.w.document.documentElement.dataset.privacy,'hidden');
  for(const id of ['privacyToggle','modalPrivacyToggle']){
    assert.equal(f.$(id).getAttribute('aria-pressed'),'true');assert.match(f.$(id).title,/anzeigen/);
  }
  f.requests.length=0;f.$('privacyToggle').click();assert.equal(privacy.hidden(),false);
  f.$('modalPrivacyToggle').click();assert.equal(privacy.hidden(),true);
  assert.equal(f.w.localStorage.getItem('hp_hide_values'),'1');
  const next=await fixture(t,{storage:{hp_hide_values:f.w.localStorage.getItem('hp_hide_values')}});
  assert.equal(next.w.HaushaltProPrivacy.hidden(),true);
  f.w.dispatchEvent(new f.w.StorageEvent('storage',{key:'hp_hide_values',newValue:'0'}));
  assert.equal(privacy.hidden(),false);
  Object.defineProperty(f.w,'localStorage',{get(){throw new Error('Storage blocked')}});
  f.$('privacyToggle').click();assert.equal(privacy.hidden(),true);
  f.$('privacyToggle').click();assert.equal(privacy.hidden(),false);
  assert.equal(f.requests.length,0);
});

test('live text, SVG titles, tooltips and accessible progress restore the latest value after repeated toggles',async t=>{
  const f=await fixture(t,privateOptions),privacy=f.w.HaushaltProPrivacy,root=f.w.document.createElement('section');
  root.innerHTML='<p title="Limit 1.234,56 €" aria-label="Anteil 20 %">1.234,56 € · 20 %</p><svg><title>Saldo -234,56 €</title><text>20 %</text></svg><progress value="20" max="100"></progress><span role="progressbar" aria-valuenow="20" aria-valuetext="20 % genutzt"></span>';
  f.w.document.body.append(root);await settle();assertMasked(root);
  assert.equal(root.querySelector('progress').getAttribute('aria-valuetext'),'**** %');
  const p=root.querySelector('p');
  p.firstChild.nodeValue='9.876,54 € · 30 %';p.title='Limit 9.876,54 €';p.setAttribute('aria-label','Anteil 30 %');
  await settle();assertMasked(root);
  for(let i=0;i<3;i++){
    privacy.setHidden(false);await settle();
    assert.equal(p.textContent,'9.876,54 € · 30 %');assert.equal(p.title,'Limit 9.876,54 €');
    assert.equal(p.getAttribute('aria-label'),'Anteil 30 %');
    assert.equal(root.querySelector('progress').getAttribute('aria-valuetext'),null);
    assert.equal(root.querySelector('[role=progressbar]').getAttribute('aria-valuetext'),'20 % genutzt');
    privacy.setHidden(true);await settle();assertMasked(root);
  }
  root.remove();await settle();privacy.setHidden(false);
});

test('accounts, bookings, recurring entries, open payments and investments mask financial output while retaining data',async t=>{
  const f=await fixture(t,privateOptions);
  const account={id:1,name:'Giro',type:'checking',balance:987.65,month_start_balance:1100.01,month_end_balance:-55.99,balance_cutoff:'2026-09-17'};
  f.run('accountsCache='+JSON.stringify([account]));f.w.renderAccounts();
  f.$('txBody').innerHTML=f.w.transactionCards([{id:42,booking_date:'2026-09-17',name:'Miete',account_name:'Giro',amount:-987.65,recurring:true,category_name:'Wohnen',status:'executed'}]);
  f.setHandler(async url=>{
    if(url==='/api/recurring')return [{id:41,name:'Miete',account_id:1,category_id:1,next_date:'2026-10-20',amount:-850.01,frequency:'monthly',interval_count:1}];
    if(url==='/api/recurring-transfers')return [];
    if(url.startsWith('/api/open-items'))return {items:[{id:7,kind:'receivable',name:'Darlehen',amount:200,paid:50,remaining:150,status:'partial',payments:[]}],pages:1,page:1,total:1,totals:{payable:0,receivable:150,overdue:0}};
    if(url==='/api/investments')return {assets:[{id:1,name:'Anlage',quantity:3,purchase_price:123.45,current_price:234.56,market_value:703.68,gain:333.33,performance_pct:90.01}],total_cost:370.35,total_value:703.68,gain:333.33,performance_pct:90.01};
    return emptyList;
  });
  await f.w.loadRecurring();await f.w.loadOpenItems();await f.w.loadInvestments();await settle();
  for(const id of ['accounts','txBody','recBody','view-open-items','view-investments'])assertMasked(f.$(id));
  assert.match(f.$('accounts').querySelector('summary').textContent,/\*{4}.*Monatsende/s);
  assert.match(f.$('txBody').textContent,/17.9.2026/);assert.match(f.$('recBody').textContent,/Miete/);
  assert.equal(f.run('accountsCache[0].balance'),987.65);assert.equal(f.run('fmt(-987.65)'),'-987,65\u00a0€');
  f.w.HaushaltProPrivacy.setHidden(false);await settle();
  assert.match(f.$('accounts').textContent,/987,65/);assert.match(f.$('recBody').textContent,/850,01/);
  assert.match(f.$('view-open-items').textContent,/150,00/);assert.match(f.$('view-investments').textContent,/90.01 %/);
});

test('hidden money fields retain exact form values and constraints, with explicit reveal inside a modal',async t=>{
  const f=await fixture(t,privateOptions);
  const style=f.w.document.createElement('style');style.textContent=source('privacy-values.css');f.w.document.head.append(style);
  f.setHandler(async(_url,options)=>options.method==='POST'?{id:7}:emptyList);
  f.w.openItemDialog({id:7,kind:'receivable',name:'Privatdarlehen',payee:'Max',amount:200.01,due_date:'2026-10-01',note:'200 € verliehen, 25 % zurück'});
  const form=f.$('modalForm'),input=form.elements.amount,button=input.nextElementSibling;
  assert.equal(input.value,'200.01');assert.equal(input.type,'number');assert.equal(input.min,'0.01');assert.equal(input.step,'0.01');assert.equal(input.required,true);
  assert.equal(new f.w.FormData(form).get('amount'),'200.01');
  assert.equal(f.w.getComputedStyle(input).display,'none');assert.equal(f.w.getComputedStyle(button).display,'block');assert.equal(button.textContent,'****');
  assert.equal(form.elements.due_date.classList.contains('privacy-sensitive-input'),false);
  assert.equal(f.w.getComputedStyle(form.elements.note).display,'none');
  assert.equal(new f.w.FormData(form).get('note'),'200 € verliehen, 25 % zurück');
  input.value='0';assert.equal(form.checkValidity(),false);assert.equal(f.w.HaushaltProPrivacy.hidden(),true);
  assert.equal(f.w.document.activeElement,button);
  button.click();assert.equal(f.w.HaushaltProPrivacy.hidden(),false);assert.equal(f.w.document.activeElement,input);
  input.value='250.09';f.$('modalPrivacyToggle').click();assert.equal(f.w.HaushaltProPrivacy.hidden(),true);
  await f.submit();
  const request=f.requests.find(x=>x.options.method==='PUT');assert.equal(JSON.parse(request.options.body).amount,'250.09');
  assert.equal(f.w.HaushaltProPrivacy.hidden(),true,'saving never reveals values');
  f.w.accountDialog({id:1,name:'Giro',type:'checking',opening_balance:-1234.56,start_date:'2026-01-01'});
  f.run(source('ui-enhancements.js'));await settle();
  const signed=form.elements.opening_balance;
  assert.equal(signed.type,'text');assert.equal(signed.value,'-1234.56');assert.equal(f.w.getComputedStyle(signed).display,'none');
  assert.equal(f.$('modalContent').querySelectorAll('.privacy-input-mask').length,1);
  assertMasked(f.$('modalContent'));
  f.$('modalPrivacyToggle').click();await settle();
  assert.equal(new f.w.FormData(form).get('opening_balance'),'-1234.56');assert.notEqual(f.w.getComputedStyle(signed).display,'none');
});

test('all canvas renderers redraw masked axes, amounts and hover percentages with dates intact',async t=>{
  const f=await fixture(t),charts=['chart','dashboardYearChart','analysisChart','expenseDonut','planningChart','planningYearChart'].map(id=>mockCanvas(f,id));
  const rows=[{date:'2026-09-17',balance:1234.56,opening_balance:1000},{date:'2026-09-18',balance:1250.67}];
  f.w.drawChart(rows,rows[0].date);
  f.w.interactiveMonthlyChart('dashboardYearChart',[{month:'2026-09',month_end_balance:1234.56}],'month_end_balance');
  f.w.drawAnalysisChart([{month:'2026-09',income:3000,expense:1200,savings:300}]);
  f.w.drawDonut('expenseDonut','expenseDonutLegend',[{category_name:'Miete',amount:1200},{category_name:'Strom',amount:300}]);
  for(const id of ['planningChart','planningYearChart'])f.w.interactiveMonthlyChart(id,[{month:'2026-09',end_balance:1234.56},{month:'2026-10',end_balance:1250.67}]);
  charts.forEach(c=>c.labels.length=0);f.requests.length=0;f.$('privacyToggle').click();await settle();
  for(const c of charts){assert.ok(c.labels.some(x=>x.includes('****')),c.canvas.id);c.labels.forEach(label=>assert.doesNotMatch(label,financial));}
  assert.equal(charts[2].labels.slice(0,4).join(','),'****,****,****,****','analysis axes have no printed currency suffix');
  charts[3].labels.length=0;f.$('expenseDonutLegend').querySelector('button').click();
  assert.ok(charts[3].labels.includes('Miete · **** %'));
  for(const c of charts.slice(4)){c.labels.length=0;c.canvas.onmousemove({clientX:120});assert.ok(c.labels.some(x=>x==='2026-09 · **** €'));}
  f.$('chartSelect').value='1';f.$('chartSelect').dispatchEvent(new f.w.Event('input'));await settle();
  assert.match(f.$('chartReadout').textContent,/18. September 2026/);assertMasked(f.$('chartReadout'));
  assert.doesNotMatch(f.$('chartSelect').getAttribute('aria-valuetext'),financial);
  assert.doesNotMatch(charts[0].canvas.getAttribute('aria-label'),financial);
  charts.forEach(c=>c.labels.length=0);f.$('privacyToggle').click();await settle();
  assert.ok(charts[3].labels.includes('Miete · 80,0 %'));assert.match(f.$('chartReadout').textContent,/1.250,67/);
  assert.equal(f.requests.length,0);
});

test('Sure and classic flows, selection and resizing remain masked without altering cents or refetching',async t=>{
  const f=await fixture(t,privateOptions);let width=360;
  const root=f.$('reportFlowSankey');root.getBoundingClientRect=()=>({width,left:0,top:0});f.$('view-reports').hidden=false;
  const data={income:3000.12,expense:1200.03,savings:300,net:1500.09,items:[{category_id:1,category_name:'Gehalt',direction:'income',amount:3000.12},{category_id:2,category_name:'Miete',direction:'expense',amount:1200.03},{category_id:3,category_name:'Sparen',direction:'savings',amount:300}]};
  f.w.renderReportFlow(data,'month','September 2026');await settle();assertMasked(root);assertMasked(f.$('reportFlowClassic'));
  root.querySelector('.sankey-group[data-flow-node="expense"]').click();await settle();assertMasked(f.$('reportFlowReadout'));
  assert.match(f.$('reportFlowReadout').textContent,/\*{4} €/);assert.match(f.$('reportFlowReadout').textContent,/\*{4} %/);
  width=900;f.w.paintReportSankey();await settle();assertMasked(root);
  assert.equal(f.run('reportFlowState.model.total'),300012);assert.equal(f.run('reportFlowState.model.net'),150009);
  f.$('reportFlowView').value='classic';f.$('reportFlowView').dispatchEvent(new f.w.Event('change'));await settle();assertMasked(f.$('reportFlowClassic'));
  f.w.HaushaltProPrivacy.setHidden(false);await settle();assert.match(root.textContent,/3.000,12/);assert.match(f.$('reportFlowClassic').textContent,/1.200,03/);
  assert.equal(f.requests.length,0);
});

test('real translations and privacy settle after live value changes and restore current German/English output',async t=>{
  const f=await fixture(t,privateOptions),chart=mockCanvas(f,'chart'),originalFetch=f.w.fetch;
  f.w.fetch=async(url,options)=>String(url).startsWith('/assets/i18n/')?{ok:true,json:async()=>JSON.parse(source('i18n/'+String(url).split('/').at(-1)))}:originalFetch(url,options);
  const ready=new Promise(resolve=>f.w.document.addEventListener('haushaltpro:i18n-ready',resolve,{once:true}));
  f.run(source('i18n.js'));await ready;await settle();
  let changes=0;
  const observer=new f.w.MutationObserver(()=>{if(++changes>30)f.$('chartReadout')?.remove()});
  observer.observe(f.$('chartReadout'),{subtree:true,childList:true,characterData:true});t.after(()=>observer.disconnect());
  f.w.drawChart([{date:'2026-09-17',balance:1234.56},{date:'2026-09-18',balance:9876.54}],'2026-09-17');await settle();
  assertMasked(f.$('chartReadout'));assert.match(f.$('chartReadout').textContent,/17. September 2026/);
  await f.w.HaushaltProI18n.setLanguage('en');await settle();
  assert.match(f.$('privacyToggle').title,/Show/);assertMasked(f.$('chartReadout'));
  f.$('chartSelect').value='1';f.$('chartSelect').dispatchEvent(new f.w.Event('input'));await settle();
  f.$('privacyToggle').click();await settle();
  assert.match(f.$('chartReadout').textContent,/18 September 2026/);assert.match(f.$('chartReadout').textContent,/9,876.54/);
  f.$('privacyToggle').click();await f.w.HaushaltProI18n.setLanguage('de');await settle();assertMasked(f.$('chartReadout'));
  f.$('privacyToggle').click();await settle();assert.match(f.$('chartReadout').textContent,/9.876,54/);
  assert.ok(changes<30,'translation and masking must not repeatedly overwrite each other');
  assert.ok(chart.labels.length>0);
});

test('native notices mask amounts but CSV downloads and raw formatting retain original values',async t=>{
  const f=await fixture(t,privateOptions),messages=[];
  f.w.confirm=f.w.alert=f.w.prompt=text=>{messages.push(text);return true};
  f.run("hpConfirm('Restbetrag 1.234,56 € · 20 %');hpAlert('1,234.56 EUR');hpPrompt('Anteil 30 %')");
  assert.deepEqual(messages,['Restbetrag **** € · **** %','**** €','Anteil **** %']);
  assert.equal(f.run('fmt(1234.56)'),'1.234,56\u00a0€');
  f.setHandler(async()=>({csv:'Betrag\n1234,56\n'}));
  let exported;
  f.w.URL.createObjectURL=blob=>{exported=blob;return 'blob:test'};
  f.w.exportDialog();await f.submit();
  assert.equal(f.downloads.length,1);assert.match(f.requests.at(-1).url,/\/api\/export\/transactions\.csv/);
  const exportedText=await new Promise(resolve=>{const reader=new f.w.FileReader();reader.onload=()=>resolve(reader.result);reader.readAsText(exported)});
  assert.equal(exportedText,'Betrag\n1234,56\n');
  assert.equal(f.w.HaushaltProPrivacy.hidden(),true);
});
