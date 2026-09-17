'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {fixture,settle}=require('./helpers/ui-fixture.cjs');
const fs=require('node:fs'),path=require('node:path');

const report={income:3500.31,expense:2000.20,savings:500.01,net:1000.10,items:[
  {category_id:1,category_name:'Gehalt',direction:'income',amount:3000.10},
  {category_id:2,category_name:'Nebeneinkommen',direction:'income',amount:500.21},
  {category_id:3,category_name:'Miete',direction:'expense',amount:1500.10},
  {category_id:4,category_name:'Lebensmittel',direction:'expense',amount:500.10},
  {category_id:5,category_name:'Rücklagen',direction:'savings',amount:500.01}
]};
async function setup(t,width=900,options){
  const f=await fixture(t,options),root=f.$('reportFlowSankey');
  f.$('view-reports').hidden=false;
  root.getBoundingClientRect=()=>({width,left:0,top:0});
  return {...f,root,setWidth(n){width=n;},render(r=report,period='month',label='September 2026'){
    f.w.renderReportFlow(r,period,label);
  },state(){return f.run('reportFlowState');},switchTo(value){
    f.$('reportFlowView').value=value;
    f.$('reportFlowView').dispatchEvent(new f.w.Event('change'));
  }};
}
const sum=xs=>xs.reduce((n,x)=>n+x.cents,0);

test('Sure is the default; classic selection persists across reports and a fresh page',async t=>{
  const f=await setup(t);f.render();
  assert.equal(f.$('reportFlowView').value,'sure');
  assert.equal(f.root.hidden,false);assert.equal(f.$('reportFlowClassic').hidden,true);
  assert.ok(f.root.querySelector('svg .sankey-band'));
  assert.match(f.$('reportFlowClassic').textContent,/Gehalt/);
  const requests=f.requests.length;
  f.switchTo('classic');
  assert.equal(f.root.hidden,true);assert.equal(f.$('reportFlowClassic').hidden,false);
  assert.equal(f.w.localStorage.getItem('hp_report_flow_view'),'classic');
  f.render({...report,income:4000.31,net:1500.10},'year','2027');
  assert.equal(f.$('reportFlowView').value,'classic');
  assert.equal(f.$('reportFlowPeriodLabel').textContent,'2027');
  const next=await setup(t,390,{storage:{hp_report_flow_view:f.w.localStorage.getItem('hp_report_flow_view')}});
  next.render();assert.equal(next.root.hidden,true);
  next.switchTo('sure');assert.ok(next.root.querySelector('svg'));
  assert.equal(next.w.localStorage.getItem('hp_report_flow_view'),'sure');
  f.switchTo('sure');assert.equal(f.state().model.net,150010);
  assert.equal(f.requests.length,requests,'view changes must not request or mutate financial data');
  const unknown=await setup(t,390,{storage:{hp_report_flow_view:'bad'}});
  unknown.render();assert.equal(unknown.$('reportFlowView').value,'sure');
});

test('both sides conserve independently specified cents, including deficit, savings and no income',async t=>{
  const f=await setup(t);
  const cases=[
    [report,350031,100010],
    [{income:100,expense:150,savings:25,items:[]},17500,-7500],
    [{income:0,expense:0,savings:0.03,items:[]},3,-3],
    [{income:0.30,expense:0.10,savings:0.20,items:[]},30,0],
    [{income:0.01,expense:0,savings:0,items:[]},1,1],
    [{income:0,expense:987.65,savings:0,items:[]},98765,-98765]
  ];
  for(const [data,total,net] of cases){
    f.render(data);
    const {model,layout}=f.state();
    assert.equal(model.total,total);assert.equal(model.net,net);
    assert.equal(sum(layout.links.filter(x=>x.source)),total);
    assert.equal(sum(layout.links.filter(x=>!x.source)),total);
    assert.equal(model.groups.some(x=>x.kind==='deficit'),net<0);
    assert.equal(model.groups.some(x=>x.kind==='surplus'),net>0);
    if(net<0)assert.match(f.root.textContent,/keine zusätzliche Einnahme/);
    for(const l of layout.links)assert.ok(Math.abs(l.size/layout.scale-l.cents)<1e-6);
  }
});

test('mobile vertical and desktop horizontal geometry stays within 240–1280px without losing amounts',async t=>{
  const f=await setup(t);
  for(const width of [240,280,320,360,390,639,640,768,1024,1280]){
    f.setWidth(width);f.render();
    const {layout,model}=f.state();
    assert.equal(layout.width,width);assert.ok(layout.scale>0);
    assert.equal(layout.mobile,width<640);
    assert.equal(f.root.querySelector('svg').getAttribute('width'),String(width));
    assert.equal(f.root.querySelector('svg').dataset.orientation,width<640?'vertical':'horizontal');
    assert.equal(f.root.querySelectorAll('.sankey-category').length,6);
    for(const n of [...layout.nodes,layout.center]){
      for(const k of ['x','y','w','h'])assert.ok(Number.isFinite(n[k]),k);
      assert.ok(n.x>=0&&n.y>=0);
      assert.ok(n.x+n.w<=width+0.01);assert.ok(n.y+n.h<=layout.height+0.01);
    }
    for(const link of layout.links)assert.doesNotMatch(link.d,/NaN|Infinity/);
    assert.equal(sum(layout.links.filter(x=>x.source)),350031);
    assert.equal(sum(layout.links.filter(x=>!x.source)),350031);
    assert.equal(model.leaves.find(x=>x.name==='Rücklagen').cents,50001);
    if(width<640)assert.match(f.root.querySelector('.sankey-mobile-groups.targets').textContent,/1.000,10/);
  }
});

test('touch, keyboard, resize and report changes keep selection/readout useful without requests',async t=>{
  const f=await setup(t,320);f.render();
  const requests=f.requests.length;
  f.root.querySelector('.sankey-group[data-flow-node="expense"]').click();
  assert.match(f.$('reportFlowReadout').textContent,/Ausgaben: 2.000,20/);
  assert.equal(f.root.querySelector('.sankey-band.is-active').dataset.flowKind,'expense');
  f.setWidth(900);f.w.paintReportSankey();
  assert.equal(f.root.querySelectorAll('.sankey-band.is-active[data-flow-kind="expense"]').length,2);
  f.setWidth(320);f.w.paintReportSankey();
  const details=f.root.querySelector('details');details.querySelector('summary').click();
  f.root.querySelector('.sankey-category[data-flow-node="expense-1"]').click();
  assert.match(f.$('reportFlowReadout').textContent,/Lebensmittel: 500,10/);
  f.setWidth(900);f.w.dispatchEvent(new f.w.Event('resize'));
  await new Promise(resolve=>f.w.requestAnimationFrame(resolve));
  assert.equal(f.state().layout.mobile,false);
  assert.equal(f.root.querySelector('details').open,true);
  assert.match(f.$('reportFlowReadout').textContent,/Lebensmittel: 500,10/);
  const node=f.root.querySelector('g[data-flow-node="surplus"]');
  node.dispatchEvent(new f.w.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
  assert.equal(node.getAttribute('aria-pressed'),'true');
  assert.match(f.$('reportFlowReadout').textContent,/Übrig: 1.000,10/);
  node.dispatchEvent(new f.w.KeyboardEvent('keydown',{key:' ',bubbles:true}));
  assert.equal(node.getAttribute('aria-pressed'),'false');
  assert.match(f.$('reportFlowReadout').textContent,/Tippe/);
  f.render({income:10,expense:20,savings:0,items:[]},'year','2025');
  assert.equal(f.state().active,null);assert.equal(f.$('reportFlowPeriodLabel').textContent,'2025');
  assert.equal(f.requests.length,requests);
});

test('many categories, tiny and large amounts, malicious names and empty reports remain complete',async t=>{
  const f=await setup(t,1000);
  const items=Array.from({length:60},(_,i)=>({category_id:i+1,category_name:i===0?'<img src=x onerror=alert(1)> & Test':'Kategorie '+i,direction:'expense',amount:i+0.01}));
  const expense=1770.60;
  f.render({income:99999999.99,expense,savings:0,items});
  assert.ok(f.state().layout.nodes.length<20);
  assert.ok(f.state().layout.scale>0);
  assert.equal(f.root.querySelectorAll('.sankey-category[data-flow-kind="expense"]').length,60);
  assert.equal(f.root.querySelectorAll('img,script,svg svg').length,0);
  assert.match(f.root.textContent,/<img src=x onerror=alert\(1\)> & Test/);
  f.root.querySelector('.sankey-category[data-flow-node="expense-0"]').click();
  assert.match(f.$('reportFlowReadout').textContent,/0,01/);
  assert.equal(f.root.querySelector('.sankey-band.is-active').dataset.flowNode,'expense-more');
  f.setWidth(240);f.render({income:99999999.99,expense,savings:0,items});
  assert.match(f.root.querySelector('.sankey-group').textContent,/99.999.999,99/);
  f.render({income:0,expense:0,savings:0,items:[]});
  assert.equal(f.root.querySelector('svg'),null);assert.match(f.root.textContent,/Keine Geldbewegungen/);
  f.render();assert.ok(f.root.querySelector('svg'));
  f.render({income:10,expense:0,savings:0,items:[{direction:'income',amount:15,category_name:'Fehler'}]});
  assert.equal(f.root.querySelector('svg'),null);assert.match(f.root.textContent,/Kategoriesummen/);
});

test('language changes translate the connected view without a repeated i18n redraw loop',async t=>{
  const f=await setup(t,390);f.render();
  let writes=0;
  const inner=Object.getOwnPropertyDescriptor(f.w.Element.prototype,'innerHTML');
  Object.defineProperty(f.root,'innerHTML',{get(){return inner.get.call(this);},set(value){
    assert.ok(++writes<12,'i18n must not repeatedly rebuild the Sankey');inner.set.call(this,value);
  }});
  const originalFetch=f.w.fetch;
  f.w.fetch=async (url,options)=>String(url).startsWith('/assets/i18n/')?
    {ok:true,json:async()=>JSON.parse(fs.readFileSync(path.join(__dirname,'../static/i18n',String(url).split('/').pop()),'utf8'))}:originalFetch(url,options);
  f.run(fs.readFileSync(path.join(__dirname,'../static/i18n.js'),'utf8'));
  await settle();await f.w.HaushaltProI18n.setLanguage('en');await settle();
  assert.match(f.root.textContent,/Income|Expenses/);
  assert.match(f.$('reportFlowHelp').textContent,/Connected bands/);
  assert.match(f.$('reportFlowView').textContent,/Classic/);
  assert.equal(f.$('reportFlowView').value,'sure');
  await f.w.HaushaltProI18n.setLanguage('de');await settle();
  assert.match(f.root.textContent,/Einnahmen/);assert.ok(writes<=4);
});

test('a blocked preference store does not break switching or render the wrong view',async t=>{
  const f=await setup(t,390);f.render();
  f.w.Storage.prototype.setItem=()=>{throw new f.w.DOMException('Blocked','SecurityError');};
  f.switchTo('classic');assert.equal(f.$('reportFlowClassic').hidden,false);
  f.switchTo('sure');assert.equal(f.root.hidden,false);assert.ok(f.root.querySelector('svg'));
});
