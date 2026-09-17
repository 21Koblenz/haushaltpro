'use strict';
// Exercise the shipped HTML/scripts with a DOM and mocked HTTP responses.
// This verifies interaction and escaping, not browser layout or native styling.
const test = require('node:test');
const assert = require('node:assert/strict');
const {fixture,settle,emptyList}=require('./helpers/ui-fixture.cjs');
const debt = {id:7,kind:'receivable',name:'Darlehen <Max>',payee:'Max & Eva',amount:200,paid:50,
  remaining:150,due_date:'2026-01-10',note:'Privat',status:'partial',overdue:true,cancelled:false,payments:[]};

test('booking cards start collapsed, keep the five summary fields and escape user data', async t => {
  const f = await fixture(t);
  const row = {id:42,booking_date:'2026-06-02',name:'Miete <img src=x onerror=alert(1)>',
    account_name:'Giro & Privat',amount:-987.65,recurring:true,recurring_frequency:'monthly',
    recurring_interval_count:1,recurring_due_date:'2026-06-01',status:'executed',
    category_name:'Wohnen',payee:'Vermieter',note:'Nur im aufgeklappten Bereich',tags:['Privat'],
    splits:[{category_id:1,amount:-987.65,note:'<script>bad()</script>'}]};
  f.$('txBody').innerHTML=f.w.transactionCards([row,{...row,id:43,recurring:false,transfer:true,
    recurring_transfer_id:8,transfer_side:'out',transfer_to_account_name:'Sparen',status:'planned'}]);
  const cards=f.$('txBody').querySelectorAll('details');
  assert.equal(cards.length,2);
  for (const card of cards) {
    assert.equal(card.open,false);
    assert.ok(card.querySelector('summary .recurring-mark[aria-label="Wiederkehrend"]'));
    assert.equal(card.querySelector('summary time').dateTime,'2026-06-02');
    assert.equal(card.querySelector('summary .tx-summary-account').textContent,'Giro & Privat');
    assert.match(card.querySelector('summary .tx-summary-amount').textContent,/987,65/);
    assert.doesNotMatch(card.querySelector('summary').textContent,/Nur im|Vermieter|Wohnen/);
    assert.equal(card.querySelectorAll('img,script').length,0);
  }
  const summary=cards[0].querySelector('summary');
  const status=card=>Array.from(card.querySelectorAll('dt')).find(e=>e.textContent==='Status').nextElementSibling.textContent;
  assert.equal(status(cards[0]),'Gebucht');
  assert.equal(status(cards[1]),'Geplant');
  summary.click();
  assert.equal(cards[0].open,true);
  assert.match(cards[0].textContent,/Ursprünglicher Termin/);
  summary.click();
  assert.equal(cards[0].open,false);
  f.run("currentMe={role:'viewer',permissions:['read']}");
  f.$('txBody').innerHTML=f.w.transactionCards([row]);
  assert.equal(f.$('txBody').querySelectorAll('[data-edit],[data-delete],[data-cancel]').length,0);
  assert.ok(f.$('txBody').querySelector('[data-attach]'));
});

test('new item dialog restores Save after attachments and posts exact cents and counterparty', async t => {
  const f = await fixture(t);
  f.$('modalSave').hidden=true; // attachments use the same dialog without a save action
  f.setHandler(async (_url, options) => options.method==='POST'?{id:7}:emptyList);
  f.w.openItemDialog();
  assert.equal(f.$('modalSave').hidden,false);
  const form=f.$('modalForm');
  form.elements.kind.value='receivable';
  form.elements.name.value='Privatdarlehen';
  form.elements.payee.value='Max';
  form.elements.amount.value='200.01';
  form.elements.due_date.value='2026-10-01';
  await f.submit();
  const request=f.requests.find(x=>x.options.method==='POST');
  assert.equal(request.url,'/api/open-items');
  assert.deepEqual(JSON.parse(request.options.body),{kind:'receivable',name:'Privatdarlehen',payee:'Max',
    amount:'200.01',due_date:'2026-10-01',note:null,cancelled:false});
  assert.equal(f.$('modal').open,false);
  assert.equal(f.refreshes,1);
});

test('partial payment links existing cash without new booking fields; mode switch enables new cash entry', async t => {
  const f = await fixture(t);
  f.w.loadTransactions=async()=>{};
  f.setHandler(async (url, options) => {
    if (options.method==='POST') return {id:12,transaction_id:91};
    if (url.includes('/candidates?')) return {items:[{id:91,booking_date:'2026-01-11',name:'Rückzahlung',
      account_name:'Giro',available:50}],has_more:false};
    if (url==='/api/open-items/7') return debt;
    return emptyList;
  });
  await f.w.paymentDialog(7);
  await settle();
  const form=f.$('modalForm');
  assert.equal(form.elements.account_id.disabled,true);
  f.$('paymentCandidate').value='91';
  f.$('paymentCandidate').dispatchEvent(new f.w.Event('change'));
  assert.equal(f.$('paymentAmount').value,'50.00');
  assert.equal(f.$('paymentAmount').max,'50');
  await f.submit();
  assert.deepEqual(JSON.parse(f.requests.find(x=>x.options.method==='POST').options.body),
    {amount:'50.00',transaction_id:91});

  await f.w.paymentDialog(7);
  await settle();
  f.$('paymentMode').value='new';
  f.$('paymentMode').dispatchEvent(new f.w.Event('change'));
  assert.equal(form.elements.transaction_id.disabled,true);
  assert.equal(form.elements.account_id.disabled,false);
  assert.deepEqual(Array.from(form.elements.category_id.options,o=>o.value),['','5']);
  form.elements.account_id.value='2';
  form.elements.category_id.value='5';
  form.elements.booking_date.value='2026-01-11';
  form.elements.amount.value='49.99';
  await f.submit();
  assert.deepEqual(JSON.parse(f.requests.filter(x=>x.options.method==='POST').at(-1).options.body),
    {amount:'49.99',account_id:2,booking_date:'2026-01-11',category_id:5,note:null});
});

test('failed candidate pagination retries the same page and stale results cannot replace a new search', async t => {
  const f=await fixture(t);
  let attempts=0, releaseOld;
  f.setHandler(async url=>{
    if(url==='/api/open-items/7')return debt;
    const p=new URL(url,'https://haushaltpro.test').searchParams;
    if(p.get('q')==='old')return new Promise(resolve=>{releaseOld=resolve;});
    if(p.get('page')==='2'&&++attempts===1)throw new Error('Network lost');
    return {items:[{id:p.get('q')==='new'?99:Number(p.get('page')),name:p.get('q')||'A',
      account_name:'Giro',booking_date:'2026-01-01',available:10}],has_more:true};
  });
  await f.w.paymentDialog(7);await settle();
  f.$('paymentMore').click();await settle();
  f.$('paymentMore').click();await settle();
  assert.deepEqual(f.requests.filter(x=>x.url.includes('/candidates?')).map(x=>new URL(x.url,'https://x').searchParams.get('page')),['1','2','2']);
  f.$('paymentSearch').value='old';f.$('paymentSearchBtn').click();await settle();
  f.$('paymentSearch').value='new';f.$('paymentSearchBtn').click();await settle();
  releaseOld({items:[{id:88,name:'Old',account_name:'Giro',booking_date:'2026-01-01',available:10}],has_more:false});
  await settle();
  assert.deepEqual(Array.from(f.$('paymentCandidate').options,o=>o.value),['','99']);
});

test('open items display overdue partial balances, lazy payments and read-only permissions', async t=>{
  const f=await fixture(t);
  f.setHandler(async url=>url==='/api/open-items/7'?{...debt,payments:[{id:1,transaction_id:91,
    name:'Zurück',account_name:'Giro',booking_date:'2026-01-11',amount:50}]}:
    {...emptyList,items:[debt],total:1,totals:{payable:0,receivable:150,overdue:1}});
  await f.w.loadOpenItems();
  assert.match(f.$('openReceivable').textContent,/150,00/);
  const card=f.$('openItemsList').querySelector('details');
  assert.equal(card.open,false);
  assert.ok(card.classList.contains('is-overdue'));
  assert.match(card.querySelector('summary').textContent,/Teilweise bezahlt.*Überfällig/);
  assert.equal(f.requests.filter(x=>x.url==='/api/open-items/7').length,0);
  card.querySelector('summary').click();
  await new Promise(resolve=>setTimeout(resolve,10));
  await settle();
  assert.match(card.querySelector('[data-payments-for]').textContent,/Zurück/);
  f.run("currentMe={role:'viewer',permissions:['read'],book:{id:'test'}}");
  await f.w.loadOpenItems();
  assert.equal(f.$('newOpenItem').hidden,true);
  assert.equal(f.$('openItemsList').querySelectorAll('[data-pay-item],[data-edit-item]').length,0);
});

test('CSV dialogs inherit filters, separate year/date reports, download and never refresh financial data', async t=>{
  const f=await fixture(t);
  f.setHandler(async()=>({csv:'Name;Betrag\r\nTest;50,00\r\n'}));
  f.$('txPeriod').value='month';
  f.w.setMonthControls('txMonthName','txYear','2028-02');
  f.w.fillAccountSelects();
  f.$('txAccountFilter').value='2';
  f.$('txSearch').value='Miete';
  f.w.exportDialog();
  const form=f.$('modalForm');
  assert.equal(form.elements.from_date.value,'2028-02-01');
  assert.equal(form.elements.to_date.value,'2028-02-29');
  assert.equal(form.elements.account_id.value,'2');
  assert.equal(form.elements.year.disabled,true);
  assert.equal(f.$('modalSave').textContent,'Herunterladen');
  form.elements.category_id.value='1';
  await f.submit();
  const url=new URL(f.requests.at(-1).url,'https://haushaltpro.test');
  assert.equal(url.pathname,'/api/export/transactions.csv');
  assert.deepEqual(Object.fromEntries(url.searchParams),{from_date:'2028-02-01',to_date:'2028-02-29',
    account_id:'2',category_id:'1',status:'all',q:'Miete'});
  assert.equal(f.downloads.at(-1).name,'haushaltpro-buchungen.csv');
  assert.equal(f.refreshes,0);
  assert.equal(f.messages.at(-1),'CSV exportiert');
  f.$('planningYear').value='2029';f.w.exportDialog(true);
  assert.equal(form.elements.from_date.disabled,true);
  assert.equal(form.elements.year.disabled,false);
  await f.submit();
  const fixed=new URL(f.requests.at(-1).url,'https://haushaltpro.test');
  assert.equal(fixed.pathname,'/api/export/fixed-costs.csv');
  assert.deepEqual(Object.fromEntries(fixed.searchParams),{year:'2029',account_id:'2'});
  assert.equal(f.downloads.at(-1).name,'haushaltpro-fixkosten-plan-2029.csv');
  f.w.openItemDialog();
  assert.equal(f.$('modalSave').textContent,'Speichern');
});
