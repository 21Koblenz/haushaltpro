/* Draw in CSS pixels: real container width, readable ticks and a separate readout. */
const dashboardCharts=new Map();
function chartTickIndices(count,width,minGap){
  if(count<=1)return count?[0]:[];
  const step=Math.max(1,Math.ceil((count-1)/Math.max(1,Math.floor(width/minGap))));
  const ticks=[0];
  for(let i=step;i<count-1;i+=step){
    if((count-1-i)*width/(count-1)>=minGap)ticks.push(i);
  }
  ticks.push(count-1);
  return ticks;
}
function chartAxisMoney(value,compact){
  if(Math.abs(value)<0.005)value=0;
  const magnitude=Math.abs(value),en=hpLang()==='en';
  const scale=compact&&magnitude>=1e6?1e6:compact&&magnitude>=1000?1000:1;
  const suffix=scale===1e6?(en?'m':'Mio.'):scale===1000?(en?'k':'Tsd.'):'';
  const number=new Intl.NumberFormat(hpLocale(),{maximumFractionDigits:scale===1?0:1}).format(value/scale);
  return number+(suffix?' '+suffix:'')+' €';
}
function balanceChartLayout(rows,options,width,height,measure){
  const values=rows.map(r=>Number(r[options.key]));
  if(options.opening&&rows[0]?.opening_balance!=null)values.push(Number(rows[0].opening_balance));
  const rawMin=Math.min(...values),rawMax=Math.max(...values);
  const padding=Math.max(1,(rawMax-rawMin)*.1),min=rawMin-padding,max=rawMax+padding,span=max-min;
  const ticks=Array.from({length:5},(_,i)=>({value:max-span*i/4}));
  ticks.forEach(t=>t.label=chartAxisMoney(t.value,width<600));
  const left=Math.min(Math.ceil(Math.max(...ticks.map(t=>measure(t.label)))+12),width*.42);
  const right=14,top=18,bottom=34,plotW=Math.max(1,width-left-right),plotH=Math.max(1,height-top-bottom);
  const xFor=i=>left+(rows.length===1?plotW/2:plotW*i/(rows.length-1));
  const yFor=v=>top+(max-v)/span*plotH;
  return {left,right,top,bottom,plotW,plotH,xFor,yFor,ticks,
    indices:chartTickIndices(rows.length,plotW,options.monthly?52:width>=700?24:36)};
}
function scheduleDashboardChart(state){
  if(state.frame!=null)return;
  state.frame=requestAnimationFrame(()=>{state.frame=null;paintDashboardChart(state)});
}
function paintDashboardChart(state){
  const {canvas,rows,options}=state,ctx=canvas.getContext('2d');
  if(!ctx)return;
  const box=canvas.parentElement.getBoundingClientRect(),width=Math.floor(box.width),height=Math.floor(box.height);
  if(width<=0||height<=0)return; // ResizeObserver redraws when a hidden view becomes visible.
  const ratio=Math.min(3,Math.max(1,window.devicePixelRatio||1));
  const pixelW=Math.round(width*ratio),pixelH=Math.round(height*ratio);
  if(canvas.width!==pixelW||canvas.height!==pixelH){canvas.width=pixelW;canvas.height=pixelH}
  ctx.setTransform(ratio,0,0,ratio,0,0);ctx.clearRect(0,0,width,height);
  if(!rows.length){state.layout=null;return}
  const css=getComputedStyle(document.documentElement),grid=css.getPropertyValue('--line').trim()||'#273445',
    text=css.getPropertyValue('--muted').trim()||'#94a3b8',accent=css.getPropertyValue('--accent').trim()||'#77e0b5';
  ctx.font='12px system-ui';
  const layout=balanceChartLayout(rows,options,width,height,label=>ctx.measureText(label).width);
  state.layout=layout;
  const {left,right,top,bottom,plotW,plotH,xFor,yFor,ticks,indices}=layout;
  ctx.textAlign='right';ctx.textBaseline='middle';
  ticks.forEach((tick,i)=>{
    const y=top+plotH*i/4;
    ctx.strokeStyle=grid;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(width-right,y);ctx.stroke();
    ctx.fillStyle=text;ctx.fillText(tick.label,left-8,y,left-10);
  });
  ctx.textBaseline='top';ctx.fillStyle=text;
  indices.forEach(i=>{
    const raw=String(rows[i][options.labelKey]);
    const label=options.monthly?new Intl.DateTimeFormat(hpLocale(),{month:'short'}).format(new Date(raw+'-01T12:00:00')):
      String(new Date(raw+'T12:00:00').getDate());
    ctx.textAlign=i===0?'left':i===rows.length-1?'right':'center';
    ctx.fillText(label,xFor(i),height-bottom+12);
  });
  const trace=()=>{
    rows.forEach((r,i)=>{
      const x=xFor(i),y=yFor(Number(r[options.key]));
      if(i===0){
        ctx.moveTo(x,yFor(options.opening&&r.opening_balance!=null?Number(r.opening_balance):Number(r[options.key])));
        ctx.lineTo(x,y);
      }else ctx.lineTo(x,y);
    });
  };
  ctx.beginPath();trace();ctx.lineTo(xFor(rows.length-1),top+plotH);ctx.lineTo(xFor(0),top+plotH);ctx.closePath();
  ctx.fillStyle=accent;ctx.globalAlpha=.08;ctx.fill();ctx.globalAlpha=1;
  ctx.beginPath();trace();ctx.strokeStyle=accent;ctx.lineWidth=2.5;ctx.lineJoin='round';ctx.stroke();
  const selected=rows[state.index],x=xFor(state.index),y=yFor(Number(selected[options.key]));
  ctx.save();ctx.strokeStyle=text;ctx.lineWidth=1;ctx.setLineDash([4,4]);
  ctx.beginPath();ctx.moveTo(x,top);ctx.lineTo(x,top+plotH);ctx.moveTo(left,y);ctx.lineTo(left+plotW,y);ctx.stroke();ctx.restore();
  ctx.fillStyle=accent;ctx.beginPath();ctx.arc(x,y,5,0,Math.PI*2);ctx.fill();
}
function updateChartSelection(state,index){
  const {canvas,rows,options}=state,slider=document.getElementById(canvas.id+'Select'),readout=document.getElementById(canvas.id+'Readout');
  if(!rows.length){
    state.description=null;
    if(slider){slider.disabled=true;slider.min=slider.max=slider.value='0';slider.removeAttribute('aria-valuetext')}
    if(readout)readout.textContent=hpText('Keine Daten für diesen Zeitraum.');
    canvas.setAttribute('aria-label',hpText('Keine Daten für diesen Zeitraum.'));
    scheduleDashboardChart(state);return;
  }
  state.index=Math.max(0,Math.min(rows.length-1,Math.round(index)));
  const row=rows[state.index],raw=String(row[options.labelKey]);
  const label=options.monthly?formatMonthValue(raw):formatDateValue(raw,{day:'numeric',month:'long',year:'numeric'});
  const amount=fmt(row[options.key]),description=label+' · '+amount;
  if(slider){slider.disabled=rows.length<2;slider.min='0';slider.max=String(rows.length-1);slider.step='1';slider.value=String(state.index);slider.setAttribute('aria-valuetext',description)}
  if(readout&&state.description!==description)readout.innerHTML=`<span>${esc(label)}</span><strong class="amount ${row[options.key]<0?'neg':''}">${esc(amount)}</strong>`;
  state.description=description;
  canvas.setAttribute('aria-label',hpText('Kontoverlauf')+' · '+description);
  scheduleDashboardChart(state);
}
function drawResponsiveBalanceChart(canvasId,rows,options={}){
  const canvas=document.getElementById(canvasId);if(!canvas)return;
  let state=dashboardCharts.get(canvasId);
  if(!state){
    state={canvas,rows:[],options:{},index:0,frame:null,layout:null};dashboardCharts.set(canvasId,state);
    const selectAt=clientX=>{
      if(!state.rows.length||!state.layout)return;
      const rect=canvas.getBoundingClientRect(),{left,plotW}=state.layout;
      updateChartSelection(state,(clientX-rect.left-left)/plotW*Math.max(0,state.rows.length-1));
    };
    canvas.onpointerdown=e=>selectAt(e.clientX);
    canvas.onpointermove=e=>{if(e.pointerType==='mouse'||e.buttons)selectAt(e.clientX)};
    const slider=document.getElementById(canvasId+'Select');
    if(slider)slider.oninput=()=>updateChartSelection(state,Number(slider.value));
    if(typeof ResizeObserver!=='undefined'){
      state.observer=new ResizeObserver(()=>scheduleDashboardChart(state));state.observer.observe(canvas.parentElement);
    }
  }
  state.options={key:'balance',labelKey:'date',...options};
  state.rows=(rows||[]).filter(r=>Number.isFinite(Number(r[state.options.key])));
  const selected=state.rows.findIndex(r=>r[state.options.labelKey]===options.selectedDate);
  updateChartSelection(state,selected<0?Math.max(0,state.rows.length-1):selected);
}
function redrawDashboardCharts(){
  dashboardCharts.forEach(scheduleDashboardChart);
  const analysis=document.getElementById('analysisChart');
  if(analysis?._hpAnalysisRows)drawAnalysisChart(analysis._hpAnalysisRows);
}
window.addEventListener('resize',redrawDashboardCharts);
let dashboardChartAppearance=document.documentElement.dataset.theme+'|'+document.documentElement.lang;
new MutationObserver(()=>{
  // i18n writes lang again when translating newly rendered nodes. Only react
  // to an actual language/theme change, avoiding a readout/translation loop.
  const appearance=document.documentElement.dataset.theme+'|'+document.documentElement.lang;
  if(appearance===dashboardChartAppearance)return;
  dashboardChartAppearance=appearance;
  dashboardCharts.forEach(state=>updateChartSelection(state,state.index));
  const analysis=document.getElementById('analysisChart');
  if(analysis?._hpAnalysisRows)drawAnalysisChart(analysis._hpAnalysisRows);
}).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme','lang']});
