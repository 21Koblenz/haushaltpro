'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {fixture,settle}=require('./helpers/ui-fixture.cjs');
const fs=require('node:fs'),path=require('node:path');

function chartFixture(f,id='chart',initialWidth=280){
  let width=initialWidth;
  const canvas=f.$(id),calls=[];
  const ctx=new Proxy({measureText:label=>({width:String(label).length*7})},{
    get(target,key){if(key in target)return target[key];return (...args)=>calls.push({key,args});}
  });
  canvas.getContext=()=>ctx;
  canvas.parentElement.getBoundingClientRect=()=>({width,height:250,left:0,top:0});
  canvas.getBoundingClientRect=()=>({width,height:250,left:10,top:0});
  Object.defineProperty(canvas,'clientWidth',{get:()=>width});
  Object.defineProperty(canvas,'clientHeight',{get:()=>250});
  Object.defineProperty(f.w,'devicePixelRatio',{value:2,configurable:true});
  return {canvas,calls,setWidth(value){width=value},paint(){f.run("paintDashboardChart(dashboardCharts.get("+JSON.stringify(id)+"))");},
    state(){return f.run("dashboardCharts.get("+JSON.stringify(id)+")");}};
}
const dailyRows=count=>Array.from({length:count},(_,i)=>({
  date:(count===31?'2028-10-':count===30?'2028-09-':count===29?'2028-02-':'2026-02-')+String(i+1).padStart(2,'0'),
  balance:1000-i*37.01,opening_balance:i===0?-450:null
}));

test('recurring bookings and transfers load as collapsed cards with working series actions',async t=>{
  const f=await fixture(t),edited=[];
  const series={id:41,series_id:9,name:'Miete <img src=x onerror=alert(1)>',account_id:1,
    category_id:1,payee:'Vermieter',next_date:'2028-02-20',first_date:'2026-01-20',
    amount:-850.01,frequency:'monthly',interval_count:1,valid_until:null,journal_count:8,
    note:'Vertrag <script>bad()</script>',future_change_from:'2028-03-01',fixed_cost:true};
  const transfer={id:51,name:'Rücklage',from_account_name:'Giro & Privat',to_account_name:'Sparen',
    amount:150,frequency:'monthly',interval_count:3,next_date:'2028-02-10',first_date:'2026-01-10'};
  f.setHandler(async url=>url==='/api/recurring'?[series]:url==='/api/recurring-transfers'?[transfer]:{});
  f.w.recDialog=r=>edited.push(['series',r.id]);
  f.w.recurringOverrideDialog=r=>edited.push(['occurrence',r.id]);
  f.w.recurringTransferDialog=id=>edited.push(['transfer',id]);
  await f.w.loadRecurring();
  assert.equal(f.$('txRecurringCount').textContent,'2');
  const cards=f.$('recBody').querySelectorAll('details');
  assert.equal(cards.length,2);
  cards.forEach(card=>{
    assert.equal(card.open,false);
    assert.ok(card.querySelector('summary .recurring-mark'));
    assert.ok(card.querySelector('summary time'));
    assert.equal(card.querySelectorAll('script,img').length,0);
    assert.doesNotMatch(card.querySelector('summary').textContent,/Vermieter|Vertrag|2026/);
    card.querySelector('summary').click();assert.equal(card.open,true);
  });
  assert.match(cards[0].querySelector('.tx-summary-amount').textContent,/850,01/);
  assert.match(cards[0].querySelector('.recurring-future-change').textContent,/1.3.2028/);
  assert.match(cards[1].querySelector('summary').textContent,/Giro & Privat → Sparen/);
  cards[0].querySelector('[data-redit]').click();cards[0].querySelector('[data-roverride]').click();
  cards[1].querySelector('[data-rtedit]').click();
  assert.deepEqual(edited,[['series',41],['occurrence',41],['transfer',51]]);
  f.run("currentMe={role:'viewer',permissions:['read']}");
  await f.w.loadRecurring();
  assert.equal(f.$('recBody').querySelectorAll('button').length,0);
  assert.equal(f.$('recBody').querySelectorAll('details[open]').length,0);
});

test('dashboard and account manager share collapsed balances with correct cutoff and edit actions',async t=>{
  const f=await fixture(t);
  const account={id:1,name:'Privat <svg onload=alert(1)>',type:'checking',iban:'DE123456789',
    balance:987.65,month_start_balance:1100.01,month_end_balance:-55.99,
    balance_cutoff:f.w.localToday(),start_date:'2024-01-01'};
  f.run('accountsCache='+JSON.stringify([account]));
  f.w.renderAccounts();
  let card=f.$('accounts').querySelector('details');
  assert.equal(card.open,false);
  assert.match(card.querySelector('summary').textContent,/987,65.*Bis heute/s);
  assert.doesNotMatch(card.querySelector('summary').textContent,/1.100,01|55,99/);
  assert.equal(card.querySelectorAll('svg').length,0);
  card.querySelector('summary').click();assert.equal(card.open,true);
  const amounts=Array.from(card.querySelectorAll('.account-balance-grid dd'),e=>e.textContent.replace(/\s/g,''));
  assert.deepEqual(amounts,['1.100,01€','987,65€','-55,99€']);
  assert.equal(card.querySelectorAll('button').length,0);
  account.balance_cutoff='2024-02-29';
  f.setHandler(async()=>[account]);
  f.w.setMonthControls('accountMonthName','accountYear','2024-02');
  const actions=[];
  f.w.accountDialog=a=>actions.push(['edit',a.id]);
  f.w.accountCorrectionDialog=(a,month)=>actions.push(['correct',a.id,month]);
  f.w.accountReconcileDialog=a=>actions.push(['reconcile',a.id]);
  await f.w.loadAccountManager();
  card=f.$('accountManager').querySelector('details');
  assert.equal(card.open,false);
  assert.match(card.querySelector('summary').textContent,/Bis Stichtag.*29.2.2024/s);
  card.querySelector('summary').click();
  assert.match(card.textContent,/DE123456789/);
  for(const name of ['aedit','acorrect','areconcile'])card.querySelector('[data-'+name+']').click();
  assert.deepEqual(actions,[['edit',1],['correct',1,'2024-02'],['reconcile',1]]);
  f.run("currentMe={role:'viewer',permissions:['read']}");
  await f.w.loadAccountManager();
  assert.equal(f.$('accountManager').querySelectorAll('button').length,0);
});

test('day charts fit 280–1100px with readable tick spacing and every day remains selectable',async t=>{
  const f=await fixture(t),chart=chartFixture(f);
  for(const width of [280,320,360,390,768,1100]){
    chart.setWidth(width);
    for(const count of [28,29,30,31]){
      const rows=dailyRows(count);
      f.w.drawChart(rows,rows[14].date);chart.paint();
      assert.equal(chart.canvas.width,width*2);
      assert.equal(chart.canvas.style.width,'','never force a minimum canvas CSS width');
      assert.equal(f.$('chartSelect').max,String(count-1));
      assert.equal(f.$('chartSelect').value,'14');
      const layout=chart.state().layout,ticks=Array.from(layout.indices);
      assert.equal(ticks[0],0);assert.equal(ticks.at(-1),count-1);
      if(width<400)assert.ok(ticks.length<=8);
      for(let i=1;i<ticks.length;i++)assert.ok(layout.xFor(ticks[i])-layout.xFor(ticks[i-1])>=23);
      for(let i=0;i<count;i++){
        f.$('chartSelect').value=String(i);
        f.$('chartSelect').dispatchEvent(new f.w.Event('input'));
        const expected=new Intl.NumberFormat('de-DE',{minimumFractionDigits:2,maximumFractionDigits:2}).format(rows[i].balance);
        assert.ok(f.$('chartReadout').textContent.includes(expected));
      }
      assert.ok(layout.yFor(-450)>=layout.top&&layout.yFor(-450)<=layout.top+layout.plotH,'opening balance remains part of the scale');
      assert.ok(chart.calls.filter(x=>['moveTo','lineTo','arc','fillText'].includes(x.key)).every(x=>x.args.filter(v=>typeof v==='number').every(Number.isFinite)));
    }
  }
});

test('touch and range selection, resize, theme, short months and empty charts update without fetching',async t=>{
  const f=await fixture(t),chart=chartFixture(f),observers=[];
  f.w.ResizeObserver=class{constructor(callback){observers.push(callback)}observe(){}};
  const rows=dailyRows(31);
  f.w.drawChart(rows,rows[0].date);chart.paint();
  chart.canvas.onpointerdown({clientX:10+chart.state().layout.left+chart.state().layout.plotW,pointerType:'touch'});
  assert.equal(f.$('chartSelect').value,'30');
  chart.canvas.onpointermove({clientX:10+chart.state().layout.left,pointerType:'touch',buttons:1});
  assert.equal(f.$('chartSelect').value,'0');
  f.requests.length=0;
  chart.setWidth(390);observers[0]();await new Promise(resolve=>setTimeout(resolve,25));
  assert.equal(chart.canvas.width,780);
  f.w.document.documentElement.dataset.theme='light';await settle();
  f.w.drawChart(dailyRows(28),'2026-02-28');chart.paint();
  assert.equal(f.$('chartSelect').value,'27');
  assert.match(f.$('chartReadout').textContent,/28. Februar 2026/);
  f.w.drawChart([]);chart.paint();
  assert.equal(f.$('chartSelect').disabled,true);
  assert.equal(f.$('chartReadout').textContent,'Keine Daten für diesen Zeitraum.');
  f.w.drawChart([{date:'2026-02-01',balance:0,opening_balance:0}]);chart.paint();
  assert.equal(f.$('chartSelect').disabled,true);
  assert.ok(Number.isFinite(chart.state().layout.yFor(0)));
  f.w.drawChart([]);
  f.w.drawChart([{date:'2026-02-01',balance:0,opening_balance:0}]);
  assert.match(f.$('chartReadout').textContent,/0,00/,'restoring identical data must restore the readout');
  assert.equal(f.requests.length,0);
});

test('year chart uses the mobile renderer, independent month selection and full exact amounts',async t=>{
  const f=await fixture(t),chart=chartFixture(f,'dashboardYearChart',280);
  const rows=Array.from({length:12},(_,i)=>({month:'2028-'+String(i+1).padStart(2,'0'),month_end_balance:-1000000.01+i*1000}));
  f.run("selectedMonth='2028-04'");
  f.w.interactiveMonthlyChart('dashboardYearChart',rows,'month_end_balance','month');chart.paint();
  assert.equal(chart.canvas.width,560);
  assert.equal(f.$('dashboardYearChartSelect').value,'3');
  assert.match(f.$('dashboardYearChartReadout').textContent,/April 2028.*-997.000,01/s);
  f.$('dashboardYearChartSelect').value='11';f.$('dashboardYearChartSelect').dispatchEvent(new f.w.Event('input'));
  assert.match(f.$('dashboardYearChartReadout').textContent,/Dezember 2028.*-989.000,01/s);
  assert.equal(f.$('chartSelect').value,'0','year selection must not change daily selection');
  assert.ok(chart.state().layout.indices.length<12);
  assert.ok(chart.calls.filter(c=>c.key==='fillText').every(c=>c.args[1]>=0&&c.args[1]<=280));
});

test('analysis bars respect narrow widths and redraw when their container changes',async t=>{
  const f=await fixture(t),chart=chartFixture(f,'analysisChart',240),observers=[];
  f.w.ResizeObserver=class{constructor(callback){observers.push(callback)}observe(){}};
  const rows=Array.from({length:12},(_,i)=>({month:'2028-'+String(i+1).padStart(2,'0'),income:2000,expense:1500,savings:250}));
  f.w.drawAnalysisChart(rows);
  assert.equal(chart.canvas.width,480);
  assert.equal(chart.calls.filter(c=>c.key==='fillRect').length,36);
  chart.setWidth(360);observers[0]();
  assert.equal(chart.canvas.width,720);
});

test('chart readouts and real language translation settle without a mutation loop',async t=>{
  const f=await fixture(t),chart=chartFixture(f);
  const originalFetch=f.w.fetch;
  f.w.localStorage.setItem('hp_lang','de');
  f.w.fetch=async(url,options)=>String(url).startsWith('/assets/i18n/')?
    {ok:true,json:async()=>JSON.parse(fs.readFileSync(path.join(__dirname,'../static/i18n',String(url).split('/').at(-1)),'utf8'))}:originalFetch(url,options);
  const ready=new Promise(resolve=>f.w.document.addEventListener('haushaltpro:i18n-ready',resolve,{once:true}));
  f.run(fs.readFileSync(path.join(__dirname,'../static/i18n.js'),'utf8'));
  await ready;await settle();
  let replacements=0;
  const readoutObserver=new f.w.MutationObserver(()=>{
    // Break a regression loop deterministically, so a failing test cannot hang CI.
    if(++replacements>10)f.$('chartReadout')?.remove();
  });
  readoutObserver.observe(f.$('chartReadout'),{childList:true});
  t.after(()=>readoutObserver.disconnect());
  f.w.drawChart(dailyRows(29),'2028-02-15');chart.paint();
  await settle();
  assert.ok(replacements<=2);
  assert.match(f.$('chartReadout').textContent,/15. Februar 2028/);
  await f.w.HaushaltProI18n.setLanguage('en');await settle();
  assert.ok(replacements<=3,'language changes must settle after updating the readout');
  assert.match(f.$('chartReadout').textContent,/15 February 2028/);
  const child=f.$('chartReadout').firstChild;
  f.w.document.documentElement.lang='en';await settle();
  assert.equal(f.$('chartReadout').firstChild,child);
});
