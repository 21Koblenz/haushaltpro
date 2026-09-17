'use strict';
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const assert=require('node:assert/strict');
const {JSDOM}=require('jsdom');
const root=path.resolve(__dirname,'../..');
const source=name=>fs.readFileSync(path.join(root,'static',name),'utf8');
const settle=async()=>{for(let i=0;i<4;i++)await new Promise(setImmediate)};
const emptyList={items:[],page:1,pages:1,total:0,totals:{payable:0,receivable:0,overdue:0}};
async function fixture(t,{storage={}}={}) {
  const dom = new JSDOM(source('index.html'), {url:'https://haushaltpro.test', runScripts:'outside-only', pretendToBeVisual:true});
  t.after(() => dom.window.close());
  const w = dom.window, $ = id => w.document.getElementById(id);
  for(const [key,value] of Object.entries(storage))w.localStorage.setItem(key,value);
  w.matchMedia = () => ({matches:false, addEventListener(){}});
  w.HTMLDialogElement.prototype.showModal = function(){this.open=true;};
  w.HTMLDialogElement.prototype.close = function(){this.open=false;};
  w.confirm = () => true;
  const requests = [], messages = [], downloads = [];
  let handle = async () => emptyList, refreshes = 0;
  w.fetch = async (url, options={}) => {
    if (url === '/api/status') return {json:async()=>({initialized:true})};
    if (url === '/api/me') return {status:401};
    requests.push({url,options});
    const body = await handle(url,options);
    if (body?.csv) return {ok:true,status:200,headers:{get:()=> 'text/csv'},blob:async()=>new w.Blob([body.csv])};
    return {ok:true,status:200,headers:{get:()=> 'application/json'},json:async()=>body};
  };
  for (const script of ['transaction-cards.js','overview-cards.js','dashboard-charts.js','report-flow.js','app.js','open-items.js']) {
    vm.runInContext(source(script), dom.getInternalVMContext(), {filename:script});
  }
  await settle();
  vm.runInContext(`currentMe={role:'owner',permissions:['read','write'],book:{id:'test'}};
    accountsCache=[{id:1,name:'Giro & Privat'},{id:2,name:'Sparen'}];
    categoriesCache=[{id:1,name:'Wohnen',direction:'expense'},{id:5,name:'Einnahmen',direction:'income'}];`,
    dom.getInternalVMContext());
  w.toast = message => messages.push(message);
  w.loadCommon = async () => {refreshes++;};
  w.URL.createObjectURL = () => 'blob:test';
  w.URL.revokeObjectURL = () => {};
  w.HTMLAnchorElement.prototype.click = function(){downloads.push({name:this.download,href:this.href});};
  w.initMonthControls();
  return {w,$,requests,messages,downloads,setHandler(fn){handle=fn;},
    run:script=>vm.runInContext(script,dom.getInternalVMContext()),get refreshes(){return refreshes;},
    async submit(){
      assert.equal($('modalForm').checkValidity(),true,'dialog must satisfy native constraints');
      await $('modalForm').onsubmit({preventDefault(){},currentTarget:$('modalForm')});
      await settle();
    }};
}

module.exports={fixture,settle,emptyList};
