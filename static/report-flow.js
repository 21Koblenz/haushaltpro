/* Connected Sankey presentation inspired by we-promise/sure (AGPL-3.0).
 * Original HaushaltPro implementation; see docs/THIRD-PARTY-NOTICES.md.
 * Both presentations use the existing report, without new requests or balances.
 */
const REPORT_FLOW_VIEW_KEY='hp_report_flow_view';
const reportFlowState={report:null,period:'month',label:'',view:'sure',width:0,frame:0,active:null};
const FLOW_COLORS={income:'#23a779',expense:'#ed7961',savings:'#bb90ed',surplus:'#569fdf',deficit:'#e3a83c',center:'#91a3b6'};
const FLOW_EXPENSE_COLORS=['#ed7961','#759dea','#d79b48','#c48bcb','#56abb0','#d57396','#9293d2','#8ca45b'];
function flowText(de,en){return hpLang()==='en'?en:de;}
function flowKindLabel(kind){return {
  income:flowText('Einnahmen','Income'),expense:flowText('Ausgaben','Expenses'),savings:flowText('Sparen','Savings'),
  surplus:flowText('Übrig','Surplus'),deficit:flowText('Fehlbetrag','Deficit'),center:flowText('Geldfluss','Cash flow')
}[kind];}
function flowCents(value){const n=Number(value||0);return Number.isFinite(n)?Math.max(0,Math.round(n*100)):0;}

function reportFlowModel(report){
  // Work in cents so both sides also balance for e.g. 0.10 + 0.20 EUR.
  const totals={income:flowCents(report.income),expense:flowCents(report.expense),savings:flowCents(report.savings)};
  const leaves=[];
  let invalid=false;
  for(const kind of ['income','expense','savings']){
    const rows=(report.items||[]).filter(x=>x.direction===kind&&flowCents(x.amount)>0)
      .map((x,i)=>({id:`${kind}-${i}`,kind,name:categoryDisplayName(x.category_name||'Nicht kategorisiert'),cents:flowCents(x.amount),
        color:kind==='expense'?FLOW_EXPENSE_COLORS[Math.abs(Number(x.category_id)||i)%FLOW_EXPENSE_COLORS.length]:FLOW_COLORS[kind]}))
      .sort((a,b)=>b.cents-a.cents);
    const sum=rows.reduce((n,x)=>n+x.cents,0);
    if(sum>totals[kind])invalid=true;
    if(sum<totals[kind])rows.push({id:`${kind}-other`,kind,name:flowText('Ohne Kategorie','Uncategorized'),cents:totals[kind]-sum,color:FLOW_COLORS[kind]});
    leaves.push(...rows);
  }
  const net=totals.income-totals.expense-totals.savings;
  if(net)leaves.push({id:net>0?'surplus':'deficit',kind:net>0?'surplus':'deficit',name:flowKindLabel(net>0?'surplus':'deficit'),cents:Math.abs(net),color:FLOW_COLORS[net>0?'surplus':'deficit']});
  const total=Math.max(totals.income,totals.expense+totals.savings);
  const groups=Object.entries({...totals,surplus:Math.max(0,net),deficit:Math.max(0,-net)})
    .filter(([,cents])=>cents>0).map(([kind,cents])=>({id:kind,kind,cents,name:flowKindLabel(kind),color:FLOW_COLORS[kind]}));
  return {totals,net,total,leaves,groups,invalid};
}

function flowDesktopNodes(model){
  // Limit visual density only. Every category remains in the accessible list.
  const nodes=[];
  for(const kind of ['income','deficit','expense','savings','surplus']){
    const rows=model.leaves.filter(x=>x.kind===kind),limit=kind==='expense'?7:4;
    if(rows.length<=limit+1)nodes.push(...rows);
    else nodes.push(...rows.slice(0,limit),{id:`${kind}-more`,kind,
      name:flowText(`Weitere Kategorien (${rows.length-limit})`,`Other categories (${rows.length-limit})`),
      cents:rows.slice(limit).reduce((n,x)=>n+x.cents,0),color:FLOW_COLORS[kind],members:rows.slice(limit).map(x=>x.id)});
  }
  return nodes;
}

function flowSankeyLayout(model,width){
  const mobile=width<640,margin=10,bar=mobile?10:12;
  const nodes=mobile?model.groups:flowDesktopNodes(model);
  const incoming=nodes.filter(x=>['income','deficit'].includes(x.kind));
  const outgoing=nodes.filter(x=>!['income','deficit'].includes(x.kind));
  const maxCount=Math.max(incoming.length,outgoing.length,1);
  const height=mobile?234:Math.max(380,maxCount*58+84);
  const span=mobile?Math.max(1,width-margin*2):height-84;
  const gap=mobile?14:18;
  // Reserve label space for tiny categories on desktop. One common scale is
  // used on both sides, so a 100 EUR flow has the same width everywhere.
  const scale=mobile?(span-gap*(maxCount-1))/Math.max(1,model.total)
    :Math.min(...[incoming,outgoing].filter(x=>x.length).map(rows=>{
      let low=0,high=span/Math.max(1,model.total);
      for(let i=0;i<35;i++){
        const mid=(low+high)/2,used=rows.reduce((n,x)=>n+Math.max(36,x.cents*mid),0)+gap*(rows.length-1);
        if(used>span)high=mid;else low=mid;
      }
      return low;
    }));
  const thickness=model.total*scale;
  const centralStart=mobile?(width-thickness)/2:62+(span-thickness)/2;
  const labelWidth=mobile?0:Math.min(215,Math.max(134,width*.20));
  const center=mobile?{x:centralStart,y:112,w:thickness,h:bar}:{x:width/2-bar/2,y:centralStart,w:bar,h:thickness};
  const placed=[],links=[];
  for(const [rows,source] of [[incoming,true],[outgoing,false]]){
    const used=rows.reduce((n,x)=>n+(mobile?x.cents*scale:Math.max(36,x.cents*scale)),0)+gap*Math.max(0,rows.length-1);
    let pos=mobile?(width-used)/2:62+(span-used)/2,offset=centralStart;
    for(const row of rows){
      const size=row.cents*scale,slot=mobile?size:Math.max(36,size),start=pos+(slot-size)/2;
      const rect=mobile?{x:start,y:source?18:206,w:size,h:bar}:
        {x:source?labelWidth:width-labelWidth-bar,y:start,w:bar,h:size};
      const node={...row,...rect,source,labelWidth};placed.push(node);
      const from=mobile?{x:source?start:offset,y:source?rect.y+bar:center.y+bar}:
        {x:source?rect.x+bar:center.x+bar,y:source?start:offset};
      const to=mobile?{x:source?offset:start,y:source?center.y:rect.y}:
        {x:source?center.x:rect.x,y:source?offset:start};
      const mid=mobile?(from.y+to.y)/2:(from.x+to.x)/2;
      const d=mobile
        ?`M ${from.x} ${from.y} C ${from.x} ${mid} ${to.x} ${mid} ${to.x} ${to.y} L ${to.x+size} ${to.y} C ${to.x+size} ${mid} ${from.x+size} ${mid} ${from.x+size} ${from.y} Z`
        :`M ${from.x} ${from.y} C ${mid} ${from.y} ${mid} ${to.y} ${to.x} ${to.y} L ${to.x} ${to.y+size} C ${mid} ${to.y+size} ${mid} ${from.y+size} ${from.x} ${from.y+size} Z`;
      links.push({id:row.id,kind:row.kind,cents:row.cents,color:row.color,source,from,to,d,size});
      pos+=slot+gap;offset+=size;
    }
  }
  return {width,height,mobile,center,nodes:placed,links,scale};
}

function flowShortName(name,available){
  // Keep chart labels within their column; full names are in titles and list.
  const chars=Array.from(name),cost=ch=>ch.codePointAt(0)>0x2e7f?14:9.5;
  if(chars.reduce((n,ch)=>n+cost(ch),0)<=available)return name;
  let used=10,short='';
  for(const ch of chars){if(used+cost(ch)>available)break;short+=ch;used+=cost(ch);}
  return short+'…';
}
function flowNodeDescription(node,model){
  const groupTotal=model.totals[node.kind]||model.total;
  const pct=groupTotal?node.cents/groupTotal*100:0;
  const share=pct.toLocaleString(hpLocale(),{maximumFractionDigits:pct<1?2:1});
  return `${node.name}: ${fmt(node.cents/100)} · ${share} % ${flowText('von','of')} ${flowKindLabel(node.kind)}`;
}
function flowSankeySvg(model,layout){
  const {width,height,mobile,center,nodes,links}=layout;
  const money=mobile?'':`<text class="sankey-center-value" x="${width/2}" y="39" text-anchor="middle">${esc(fmt(model.total/100))}</text>`;
  const defs=links.map((l,i)=>`<linearGradient id="hp-flow-${i}" gradientUnits="userSpaceOnUse" x1="${l.from.x}" y1="${l.from.y}" x2="${l.to.x}" y2="${l.to.y}"><stop offset="0" stop-color="${l.source?l.color:FLOW_COLORS.center}" stop-opacity=".36"/><stop offset="1" stop-color="${l.source?FLOW_COLORS.center:l.color}" stop-opacity=".36"/></linearGradient>`).join('');
  const paths=links.map((l,i)=>`<path class="sankey-band" data-flow-node="${l.id}" data-flow-kind="${l.kind}" data-cents="${l.cents}" d="${l.d}" fill="url(#hp-flow-${i})"/>`).join('');
  const bars=nodes.map((node,index)=>{
    const x=node.source?node.x-9:node.x+node.w+9,y=node.y+node.h/2;
    const amount=fmt(node.cents/100),amountLength=amount.length*7;
    // Extremely large amounts use the full list/readout rather than overlap.
    const amountText=amountLength<node.labelWidth-12?amount:new Intl.NumberFormat(hpLocale(),{style:'currency',currency:'EUR',notation:'compact',maximumFractionDigits:1}).format(node.cents/100);
    const clipX=node.source?8:node.x+node.w+6;
    const label=mobile?'':`<clipPath id="hp-flow-label-${index}"><rect x="${clipX}" y="${y-20}" width="${node.labelWidth-14}" height="42"/></clipPath><text class="sankey-node-label" clip-path="url(#hp-flow-label-${index})" x="${x}" y="${y-3}" text-anchor="${node.source?'end':'start'}"><tspan>${esc(flowShortName(node.name,node.labelWidth-14))}</tspan><tspan class="sankey-node-amount" x="${x}" dy="18">${esc(amountText)}</tspan></text>`;
    return `<g class="sankey-node" data-flow-node="${node.id}" data-flow-kind="${node.kind}" role="button" tabindex="0" aria-pressed="false" aria-label="${esc(flowNodeDescription(node,model))}"><title>${esc(flowNodeDescription(node,model))}</title><rect x="${node.x}" y="${node.y}" width="${Math.max(.75,node.w)}" height="${Math.max(.75,node.h)}" rx="2" fill="${node.color}"/>${label}</g>`;
  }).join('');
  return `<svg class="report-sankey-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" role="group" aria-label="${esc(flowText('Geldfluss: Einnahmen zu Ausgaben, Sparen und Überschuss','Cash flow: income to expenses, savings and surplus'))}" data-orientation="${mobile?'vertical':'horizontal'}"><defs>${defs}</defs>${paths}<rect x="${center.x}" y="${center.y}" width="${center.w}" height="${center.h}" rx="2" fill="${FLOW_COLORS.center}"/>${bars}<text class="sankey-center-label" x="${width/2}" y="${mobile?101:18}" text-anchor="middle">${esc(flowKindLabel('center'))}</text>${money}</svg>`;
}

function flowGroupButtons(groups,side){
  return `<div class="sankey-mobile-groups ${side}">${groups.map(x=>`<button type="button" class="sankey-group" data-flow-node="${x.id}" data-flow-kind="${x.kind}" aria-pressed="false"><span><i style="background:${x.color}" aria-hidden="true"></i>${esc(x.name)}</span><strong>${fmt(x.cents/100)}</strong></button>`).join('')}</div>`;
}
function flowCategoryList(model){
  const sections=['income','deficit','expense','savings','surplus'].map(kind=>{
    const rows=model.leaves.filter(x=>x.kind===kind);if(!rows.length)return '';
    return `<section><h3>${esc(flowKindLabel(kind))}</h3>${rows.map(x=>`<button type="button" class="sankey-category" data-flow-node="${x.id}" data-flow-kind="${x.kind}" aria-pressed="false"><span><i style="background:${x.color}" aria-hidden="true"></i>${esc(x.name)}</span><strong>${fmt(x.cents/100)}</strong></button>`).join('')}</section>`;
  }).join('');
  return `<details class="sankey-breakdown"><summary>${esc(flowText('Alle Kategorien und Beträge','All categories and amounts'))}</summary><div class="sankey-category-list">${sections}</div></details>`;
}
function selectReportFlowNode(id){
  const state=reportFlowState,root=$('reportFlowSankey');
  state.active=state.active===id?null:id;
  const node=state.model?.leaves.find(x=>x.id===state.active)||state.model?.groups.find(x=>x.id===state.active)||state.layout?.nodes.find(x=>x.id===state.active)||(state.model&&flowDesktopNodes(state.model).find(x=>x.id===state.active));
  const group=!!node&&state.model.groups.some(x=>x.id===node.id);
  const visual=node&&(state.layout.nodes.find(x=>x.id===node.id||x.members?.includes(node.id))||state.layout.nodes.find(x=>x.id===node.kind));
  root?.querySelectorAll('[data-flow-node]').forEach(el=>{
    const selected=!!node&&(group?el.dataset.flowKind===node.kind:(el.dataset.flowNode===node.id||el.dataset.flowNode===visual?.id));
    el.classList.toggle('is-active',selected);
    if(el.hasAttribute('aria-pressed'))el.setAttribute('aria-pressed',String(selected));
    el.classList.toggle('is-muted',!!node&&!selected&&(el.classList.contains('sankey-band')||el.classList.contains('sankey-node')));
  });
  const readout=$('reportFlowReadout');
  if(readout)readout.textContent=node?flowNodeDescription(node,state.model):flowText('Tippe auf einen Geldstrom oder eine Kategorie für den genauen Betrag.','Tap a flow or category for the exact amount.');
}
function paintReportSankey(){
  const state=reportFlowState,root=$('reportFlowSankey');
  if(!root||!state.report||state.view!=='sure'||root.closest('section.view[hidden]'))return;
  const measured=root.getBoundingClientRect().width||root.clientWidth;
  if(!measured)return; // ResizeObserver draws when the reports view is shown.
  const width=Math.max(120,Math.floor(measured)),model=reportFlowModel(state.report);
  state.width=width;state.model=model;
  if(model.invalid||!model.total){
    root.innerHTML=`<p class="muted sankey-empty">${esc(model.invalid?flowText('Die Kategoriesummen passen nicht zur Auswertung. Bitte lade die Auswertung neu.','Category totals do not match the report. Please reload the report.'):flowText('Keine Geldbewegungen in diesem Zeitraum.','No money movements in this period.'))}</p>`;
    state.layout=null;state.active=null;return;
  }
  const expanded=!!root.querySelector('.sankey-breakdown[open]'),layout=flowSankeyLayout(model,width);
  state.layout=layout;
  root.innerHTML=(layout.mobile?flowGroupButtons(model.groups.filter(x=>['income','deficit'].includes(x.kind)),'sources'):'')+
    flowSankeySvg(model,layout)+(layout.mobile?flowGroupButtons(model.groups.filter(x=>!['income','deficit'].includes(x.kind)),'targets'):'')+
    `<p id="reportFlowReadout" class="sankey-readout" role="status" aria-live="polite"></p>`+
    (model.net<0?`<p class="sankey-deficit-note">${esc(flowText('Fehlbetrag: Ausgaben und Sparen übersteigen die Einnahmen. Er ist keine zusätzliche Einnahme.','Deficit: expenses and savings exceed income. It is not additional income.'))}</p>`:'')+flowCategoryList(model);
  root.querySelector('.sankey-breakdown').open=expanded;
  root.querySelectorAll('[data-flow-node]').forEach(el=>{
    el.addEventListener('click',()=>selectReportFlowNode(el.dataset.flowNode));
    if(el.tagName.toLowerCase()==='g')el.addEventListener('keydown',event=>{
      if(event.key==='Enter'||event.key===' '){event.preventDefault();selectReportFlowNode(el.dataset.flowNode);}
    });
  });
  const selected=state.active;state.active=null;selectReportFlowNode(selected);
}
function queueReportSankey(){
  if(reportFlowState.frame)return;
  reportFlowState.frame=requestAnimationFrame(()=>{reportFlowState.frame=0;paintReportSankey();});
}
function setReportFlowView(view,persist=true){
  const state=reportFlowState;state.view=view==='classic'?'classic':'sure';
  if(persist){try{localStorage.setItem(REPORT_FLOW_VIEW_KEY,state.view);}catch{}}
  const select=$('reportFlowView'),classic=$('reportFlowClassic'),sankey=$('reportFlowSankey'),help=$('reportFlowHelp');
  if(select)select.value=state.view;
  if(classic)classic.hidden=state.view!=='classic';
  if(sankey)sankey.hidden=state.view!=='sure';
  if(help){
    help.dataset.i18n=state.view==='sure'?'reports.flowSankeyHelp':'reports.flowClassicHelp';
    help.textContent=state.view==='sure'?flowText('Verbundene Bänder zeigen, wohin dein Geld fließt. Ihre Breite entspricht dem Betrag. Auf dem Smartphone siehst du die Gruppen; alle Kategorien stehen darunter.','Connected bands show where your money goes. Their width represents the amount. On phones you see the groups; all categories are listed below.'):
      flowText('Pfeile zeigen den Anteil und die Größe jeder Kategorie innerhalb ihrer Gruppe.','Arrows show the share and size of each category within its group.');
  }
  if(state.report)paintReportSankey();
}
function updateReportSankey(report,period,label){
  Object.assign(reportFlowState,{report,period,label,active:null});
  setReportFlowView(reportFlowState.view,false);
}
function initReportFlowView(){
  try{reportFlowState.view=localStorage.getItem(REPORT_FLOW_VIEW_KEY)==='classic'?'classic':'sure';}catch{}
  $('reportFlowView')?.addEventListener('change',e=>setReportFlowView(e.target.value));
  setReportFlowView(reportFlowState.view,false);
  if(typeof ResizeObserver==='function'){
    const observer=new ResizeObserver(entries=>{
      const width=Math.floor(entries[0]?.contentRect.width||0);
      if(width>0&&width!==reportFlowState.width)queueReportSankey();
    });
    observer.observe($('reportFlowSankey'));reportFlowState.observer=observer;
  }
  window.addEventListener('resize',queueReportSankey,{passive:true});
  for(const event of ['haushaltpro:language-changed','haushaltpro:i18n-ready'])document.addEventListener(event,()=>{
    setReportFlowView(reportFlowState.view,false);
  });
}
