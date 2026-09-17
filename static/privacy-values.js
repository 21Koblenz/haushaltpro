/* Local display preference: never rewrite model, form or export values. */
(() => {
  'use strict';
  const KEY='hp_hide_values',MASK='****';
  let hidden=false;
  try{hidden=localStorage.getItem(KEY)==='1';}catch{}
  document.documentElement.dataset.privacy=hidden?'hidden':'visible';
  const texts=new Map(),attributes=new Map(),fields=new Map();
  const number="[+−-]?(?:\\d{1,3}(?:[.,'’\\u00a0\\u202f ]\\d{3})+|\\d+)(?:[.,]\\d+)?";
  const compact='(?:[ \\u00a0\\u202f]*(?:Mio\\.?|Mrd\\.?|Bio\\.?|Tsd\\.?|trillion|billion|million|thousand|[kmbt])(?=\\s|€|%|$|[.,;:)]))?';
  const unit='(?:€|\\bEUR\\b)';
  const values=new RegExp('(?:[+−-]?'+unit+'\\s*'+number+compact+'|'+number+compact+'\\s*(?:'+unit+'|%))','gi');
  const ATTRS=['title','aria-label','aria-valuetext','alt','placeholder'];
  const SKIP=/^(SCRIPT|STYLE|NOSCRIPT|INPUT|TEXTAREA)$/i;
  const displayText=value=>hidden?String(value??'').replace(values,match=>MASK+(match.includes('%')?' %':' €')):String(value??'');
  const containsValue=value=>{values.lastIndex=0;return values.test(String(value??''));};
  const displayNumber=value=>hidden?MASK:String(value??'');
  function readText(node){
    const old=texts.get(node);
    return old&&node.nodeValue===old.shown?old.raw:node.nodeValue;
  }
  function writeText(node,value){
    const raw=String(value??''),shown=displayText(raw);
    if(raw!==shown)texts.set(node,{raw,shown});else texts.delete(node);
    if(node.nodeValue!==shown)node.nodeValue=shown;
  }
  function readAttribute(el,name){
    const old=attributes.get(el)?.get(name),now=el.getAttribute(name);
    return old&&now===old.shown?old.raw:now;
  }
  function writeAttribute(el,name,raw,forced){
    const shown=forced!==undefined?forced:raw===null?null:displayText(raw);
    if(raw!==shown){
      if(!attributes.has(el))attributes.set(el,new Map());
      attributes.get(el).set(name,{raw,shown});
    }else{
      attributes.get(el)?.delete(name);
      if(!attributes.get(el)?.size)attributes.delete(el);
    }
    if(el.getAttribute(name)!==shown){if(shown===null)el.removeAttribute(name);else el.setAttribute(name,shown);}
  }
  const en=()=>{
    try{return (window.HaushaltProI18n?.language?.()||localStorage.getItem('hp_lang'))==='en';}catch{return false;}
  };
  function toggleLabel(){return hidden?(en()?'Show € / % values':'€ / % Werte anzeigen'):(en()?'Hide € / % values':'€ / % Werte verbergen');}
  function updateButtons(){
    document.querySelectorAll('[data-privacy-toggle]').forEach(button=>{
      const label=toggleLabel();
      button.setAttribute('aria-label',label);button.title=label;button.setAttribute('aria-pressed',String(hidden));
      const text=button.querySelector('.privacy-toggle-label');
      if(text&&text.textContent!==label)text.textContent=label;
    });
    fields.forEach(({button})=>{
      const label=en()?'Hidden amount. Show values to edit.':'Betrag ausgeblendet. Werte zum Bearbeiten anzeigen.';
      if(button.getAttribute('aria-label')!==label)button.setAttribute('aria-label',label);
    });
  }
  function sensitiveField(input){
    if(!input.matches('input,textarea')||/^(hidden|password|checkbox|radio|file|date|month|range)$/.test(input.type))return false;
    const named=/(?:^|_)(?:amount|balance|price|fees|cost|pct|percent|rate)(?:_|$)/.test(input.name);
    return named||containsValue(input.value)||((input.type==='number'||input.inputMode==='decimal')&&/€|\bEUR\b|%/i.test(input.closest('label')?.textContent||''));
  }
  function protectField(input){
    if(!sensitiveField(input)||fields.has(input))return;
    input.classList.add('privacy-sensitive-input');
    const button=document.createElement('button');button.type='button';button.className='ghost privacy-input-mask';button.textContent=MASK;
    button.setAttribute('aria-label',en()?'Hidden amount. Show values to edit.':'Betrag ausgeblendet. Werte zum Bearbeiten anzeigen.');
    button.addEventListener('click',()=>{setHidden(false);input.focus();});
    input.after(button);fields.set(input,{button});
    // Retain required/min/max/step validation without a browser popup leaking
    // an amount from a visually hidden field. The mask remains the edit target.
    input.addEventListener('invalid',event=>{if(hidden){event.preventDefault();button.focus();}});
  }
  function scanElement(el){
    if(SKIP.test(el.tagName)&&!el.matches('input,textarea'))return;
    for(const name of ATTRS){
      if(name==='aria-valuetext'&&el.matches('progress,meter,[role="progressbar"]'))continue;
      if(el.hasAttribute(name)||attributes.get(el)?.has(name))writeAttribute(el,name,readAttribute(el,name));
    }
    if(el.matches('progress,meter,[role="progressbar"]')){
      const raw=readAttribute(el,'aria-valuetext');writeAttribute(el,'aria-valuetext',raw,hidden?MASK+' %':raw);
    }
    protectField(el);
  }
  function scan(root=document.body){
    if(!root)return;
    if(root.nodeType===Node.TEXT_NODE){
      if(!SKIP.test(root.parentElement?.tagName||''))writeText(root,readText(root));return;
    }
    if(root.nodeType!==Node.ELEMENT_NODE)return;
    if(SKIP.test(root.tagName)){scanElement(root);return;}
    scanElement(root);
    root.querySelectorAll('[title],[aria-label],[aria-valuetext],[alt],[placeholder],input,textarea,progress,meter,[role="progressbar"]').forEach(scanElement);
    if(hidden){
      const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let node;
      while((node=walker.nextNode()))if(!SKIP.test(node.parentElement?.tagName||''))writeText(node,readText(node));
    }
  }
  function prune(){
    for(const node of texts.keys())if(!node.isConnected)texts.delete(node);
    for(const node of attributes.keys())if(!node.isConnected)attributes.delete(node);
    for(const [input,{button}] of fields)if(!input.isConnected){button.remove();fields.delete(input);}
  }
  function setHidden(value,persist=true){
    const changed=hidden!==!!value;hidden=!!value;
    document.documentElement.dataset.privacy=hidden?'hidden':'visible';
    if(persist){try{localStorage.setItem(KEY,hidden?'1':'0');}catch{}}
    if(!hidden){
      for(const node of [...texts.keys()])writeText(node,readText(node));
      for(const [el,names] of [...attributes])for(const name of [...names.keys()])writeAttribute(el,name,readAttribute(el,name));
    }
    prune();scan();updateButtons();
    if(hidden&&fields.has(document.activeElement))fields.get(document.activeElement).button.focus();
    if(changed)document.dispatchEvent(new CustomEvent('haushaltpro:privacy-changed',{detail:{hidden}}));
  }
  window.HaushaltProPrivacy=Object.freeze({hidden:()=>hidden,displayText,displayNumber,readText,writeText,readAttribute,writeAttribute,scan,setHidden});
  document.querySelectorAll('[data-privacy-toggle]').forEach(button=>button.addEventListener('click',()=>setHidden(!hidden)));
  for(const event of ['input','change'])document.addEventListener(event,e=>{if(e.target.matches?.('input,textarea'))protectField(e.target);});
  const observer=new MutationObserver(mutations=>{
    for(const m of mutations){
      if(m.type==='characterData'){if(hidden)scan(m.target);}
      else if(m.type==='attributes')scanElement(m.target);
      else for(const node of m.addedNodes)scan(node);
    }
    prune();
  });
  observer.observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:[...ATTRS,'type']});
  for(const event of ['haushaltpro:i18n-ready','haushaltpro:language-changed'])document.addEventListener(event,()=>{scan();updateButtons();});
  window.addEventListener('storage',event=>{if(event.key===KEY||event.key===null)setHidden(event.newValue==='1',false);});
  scan();updateButtons();
})();
