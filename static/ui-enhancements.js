(() => {
  'use strict';
  const SIGNED_MONEY_NAMES = new Set(['opening_balance', 'actual_balance']);
  const tr=(key,fallback)=>window.HaushaltProI18n?.t(key) || fallback;
  function normalizeSignedMoneyInput(raw) {
    let value = String(raw ?? '').trim().replace(/\s/g, '').replace(/[−–—]/g, '-');
    if (!value) return '0';
    if (value.includes(',') && value.includes('.')) {
      if (value.lastIndexOf(',') > value.lastIndexOf('.')) value = value.replace(/\./g, '').replace(',', '.');
      else value = value.replace(/,/g, '');
    } else if (value.includes(',')) value = value.replace(',', '.');
    if (!/^[+-]?\d+(?:\.\d{1,2})?$/.test(value)) throw new Error(tr('validation.invalidMoney','Ungültiger Geldbetrag. Beispiel: -1234,56'));
    return value.replace(/^\+/, '');
  }
  function addSignToggle(input) {
    if (!input || input.dataset.signedMoney === '1' || !SIGNED_MONEY_NAMES.has(input.name)) return;
    input.dataset.signedMoney = '1'; input.type = 'text'; input.inputMode = 'decimal'; input.autocomplete = 'off';
    const wrap = document.createElement('div'); wrap.className = 'signed-money-input'; input.parentNode.insertBefore(wrap, input);
    const toggle = document.createElement('button'); toggle.type='button'; toggle.className='ghost signed-money-toggle'; toggle.textContent='±';
    toggle.title=tr('common.toggleSign','Vorzeichen wechseln'); toggle.setAttribute('aria-label',toggle.title);
    toggle.addEventListener('click',()=>{const current=String(input.value||'').trim();input.value=current.startsWith('-')?current.slice(1):'-'+current;input.focus();try{input.setSelectionRange(input.value.length,input.value.length)}catch(_){}});
    wrap.append(toggle,input);
    if(input.name==='opening_balance'&&!wrap.nextElementSibling?.classList.contains('signed-money-help')){
      const help=document.createElement('small');help.className='signed-money-help';help.dataset.i18n='accounts.signedHelp';help.textContent=tr('accounts.signedHelp','Guthaben positiv, Soll/Dispo negativ. Beispiel: -1234,56 €.');wrap.after(help);
    }
  }
  function enhanceSignedMoneyInputs(root=document){root.querySelectorAll?.('input[name="opening_balance"], input[name="actual_balance"]').forEach(addSignToggle)}
  const modalContent=document.getElementById('modalContent'),modalForm=document.getElementById('modalForm');
  if(modalContent){enhanceSignedMoneyInputs(modalContent);new MutationObserver(()=>enhanceSignedMoneyInputs(modalContent)).observe(modalContent,{childList:true,subtree:true})}
  if(modalForm)modalForm.addEventListener('submit',(event)=>{try{modalForm.querySelectorAll('input[data-signed-money="1"]').forEach(input=>input.value=normalizeSignedMoneyInput(input.value))}catch(error){event.preventDefault();event.stopImmediatePropagation();const toast=document.getElementById('toast');if(toast){toast.textContent=error.message;toast.classList.add('show');setTimeout(()=>toast.classList.remove('show'),3000)}}},true);
  window.HaushaltProSignedMoney=Object.freeze({normalize:normalizeSignedMoneyInput});
})();
