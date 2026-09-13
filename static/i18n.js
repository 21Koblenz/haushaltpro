(() => {
  'use strict';

  const STORAGE_KEY = 'hp_lang';
  const BASE_PATH = '/assets/i18n/';
  const originalText = new WeakMap();
  const lastApplied = new WeakMap();
  const originalAttrs = new WeakMap();
  let manifest = null;
  let baseCatalog = null;
  let catalog = null;
  let currentCode = 'de';
  let currentLocale = 'de-DE';
  let applying = false;

  const escRe = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const interpolate = (text, vars = {}) => String(text ?? '').replace(/\{([A-Za-z0-9_]+)\}/g, (_m, k) => vars[k] ?? `{${k}}`);

  async function fetchJson(path) {
    const r = await fetch(path, {cache: 'no-cache', credentials: 'same-origin'});
    if (!r.ok) throw new Error(`i18n: ${path} -> HTTP ${r.status}`);
    return r.json();
  }

  function supported(code) {
    return manifest?.languages?.some(x => x.code === code);
  }

  function detectLanguage() {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && supported(saved)) return saved;
    const candidates = navigator.languages || [navigator.language || 'de'];
    for (const raw of candidates) {
      const code = String(raw || '').toLowerCase().split('-')[0];
      if (supported(code)) return code;
    }
    return manifest?.default || 'de';
  }

  function languageMeta(code = currentCode) {
    return manifest?.languages?.find(x => x.code === code) || manifest?.languages?.[0] || {code:'de',locale:'de-DE',name:'Deutsch'};
  }

  function t(key, fallback = '', vars = {}) {
    const selected = catalog?.messages?.[key];
    const base = baseCatalog?.messages?.[key];
    const value = selected || base || fallback || key;
    return interpolate(value, vars);
  }

  function translateLegacy(source) {
    if (!source || currentCode === (manifest?.default || 'de')) return source;
    const direct = catalog?.legacy?.[source];
    if (direct) return direct;
    for (const rule of (catalog?.patterns || [])) {
      try {
        const re = new RegExp(rule.source);
        if (re.test(source)) return source.replace(re, rule.target || source);
      } catch (e) {
        console.warn('Invalid i18n regex', rule, e);
      }
    }
    return source;
  }

  function splitWhitespace(value) {
    const m = String(value).match(/^(\s*)([\s\S]*?)(\s*)$/);
    return {lead:m?.[1] || '', core:m?.[2] || '', tail:m?.[3] || ''};
  }

  function translateTextNode(node) {
    if (!node || node.nodeType !== Node.TEXT_NODE) return;
    const parent = node.parentElement;
    if (!parent || /^(SCRIPT|STYLE|CODE|PRE|TEXTAREA)$/i.test(parent.tagName)) return;
    const now = String(node.nodeValue ?? '');
    const prevApplied = lastApplied.get(node);
    if (!originalText.has(node) || (prevApplied !== undefined && now !== prevApplied)) originalText.set(node, now);
    const original = originalText.get(node) ?? now;
    const {lead, core, tail} = splitWhitespace(original);
    if (!core.trim()) return;
    const translated = lead + translateLegacy(core) + tail;
    if (node.nodeValue !== translated) node.nodeValue = translated;
    lastApplied.set(node, translated);
  }

  function getOriginalAttr(el, attr) {
    let map = originalAttrs.get(el);
    if (!map) { map = {}; originalAttrs.set(el, map); }
    const now = el.getAttribute(attr);
    if (!(attr in map)) map[attr] = now;
    return map[attr];
  }

  function applyKeyedElement(el) {
    const key = el.dataset.i18n;
    if (key) el.textContent = t(key, el.textContent);
    for (const [dataAttr, realAttr] of [
      ['i18nPlaceholder','placeholder'],['i18nTitle','title'],['i18nAriaLabel','aria-label'],['i18nAlt','alt']
    ]) {
      const k = el.dataset[dataAttr];
      if (k) el.setAttribute(realAttr, t(k, el.getAttribute(realAttr) || ''));
    }
  }

  function applyLegacyAttributes(el) {
    for (const attr of ['placeholder','title','aria-label','alt']) {
      if (!el.hasAttribute?.(attr)) continue;
      const original = getOriginalAttr(el, attr);
      if (!original) continue;
      const translated = translateLegacy(original);
      if (translated !== el.getAttribute(attr)) el.setAttribute(attr, translated);
    }
  }


  function formatIsoDate(value, options = {}) {
    if (!value) return '';
    const raw = String(value);
    const d = new Date(/^\d{4}-\d{2}-\d{2}$/.test(raw) ? raw + 'T12:00:00' : raw);
    return Number.isNaN(d.getTime()) ? raw : d.toLocaleDateString(currentLocale, options);
  }

  function formatDateTime(value) {
    if (!value) return '';
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? String(value) : new Intl.DateTimeFormat(currentLocale, {dateStyle:'medium', timeStyle:'medium'}).format(d);
  }

  function displayDateFromIso(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value || ''))) return '';
    const [y,m,d] = String(value).split('-');
    return currentCode === 'de' ? `${d}.${m}.${y}` : `${d}/${m}/${y}`;
  }

  function isoFromDisplayDate(value) {
    const raw = String(value || '').trim();
    if (!raw) return '';
    let m;
    if (currentCode === 'de') m = raw.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/);
    else m = raw.match(/^(\d{1,2})[\/.](\d{1,2})[\/.](\d{4})$/);
    if (!m) return null;
    const day=Number(m[1]),month=Number(m[2]),year=Number(m[3]);
    const d=new Date(Date.UTC(year,month-1,day));
    if(d.getUTCFullYear()!==year||d.getUTCMonth()!==month-1||d.getUTCDate()!==day)return null;
    return `${year}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
  }

  function syncLocalizedDate(input) {
    const display=input?._hpDateDisplay;
    if(!display)return;
    display.placeholder=t('date.placeholder', currentCode==='de'?'TT.MM.JJJJ':'DD/MM/YYYY');
    display.lang=currentCode;
    display.value=displayDateFromIso(input.value);
    display.setCustomValidity('');
    const button=input?._hpDateButton;
    if(button){button.title=t('date.openPicker', currentCode==='de'?'Kalender öffnen':'Open calendar');button.setAttribute('aria-label',button.title)}
  }

  function enhanceDateInput(input) {
    if (!input || input.dataset.hpLocalizedDate === '1') { if(input)syncLocalizedDate(input); return; }
    if (input.type !== 'date') return;
    input.dataset.hpLocalizedDate='1';
    input.lang=currentCode;
    const required=input.required;
    input.required=false;
    const wrap=document.createElement('span');
    wrap.className='hp-date-input';
    input.parentNode.insertBefore(wrap,input);
    wrap.append(input);
    input.classList.add('hp-date-native');
    const display=document.createElement('input');
    display.type='text';display.inputMode='numeric';display.autocomplete='off';display.className='hp-date-display';display.required=required;
    const button=document.createElement('button');
    button.type='button';button.className='ghost hp-date-picker';button.textContent='📅';
    wrap.append(display,button);
    input._hpDateDisplay=display;input._hpDateButton=button;
    const commit=()=>{
      const iso=isoFromDisplayDate(display.value);
      if(iso===null){display.setCustomValidity(t('date.invalid',currentCode==='de'?'Datum im Format TT.MM.JJJJ eingeben.':'Enter the date as DD/MM/YYYY.'));input.value='';return false;}
      display.setCustomValidity('');input.value=iso||'';input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));return true;
    };
    display.addEventListener('input',()=>{const iso=isoFromDisplayDate(display.value);if(iso!==null){display.setCustomValidity('');input.value=iso||'';}else if(!display.value.trim()){display.setCustomValidity('');input.value='';}});
    display.addEventListener('change',commit);display.addEventListener('blur',()=>{if(display.value.trim())commit()});
    input.addEventListener('change',()=>syncLocalizedDate(input));
    button.addEventListener('click',()=>{try{input.showPicker?.()}catch(_){input.click?.()}});
    syncLocalizedDate(input);
  }

  function syncFileInput(input) {
    if(!input?._hpFileButton)return;
    input._hpFileButton.textContent=t('file.choose',currentCode==='de'?'Datei auswählen':'Choose file');
    input._hpFileName.textContent=input.files?.[0]?.name||t('file.none',currentCode==='de'?'Keine Datei ausgewählt':'No file selected');
  }

  function enhanceFileInput(input) {
    if (!input || input.dataset.hpLocalizedFile === '1') { if(input)syncFileInput(input); return; }
    if(input.type!=='file')return;
    input.dataset.hpLocalizedFile='1';
    const wrap=document.createElement('span');wrap.className='hp-file-input';input.parentNode.insertBefore(wrap,input);wrap.append(input);input.classList.add('hp-file-native');
    const button=document.createElement('button');button.type='button';button.className='ghost hp-file-button';
    const name=document.createElement('span');name.className='hp-file-name';wrap.append(button,name);
    input._hpFileButton=button;input._hpFileName=name;
    button.addEventListener('click',()=>input.click());input.addEventListener('change',()=>syncFileInput(input));syncFileInput(input);
  }

  function enhanceLocalizedControls(root=document) {
    const start=root.nodeType===Node.ELEMENT_NODE?root:document.documentElement;
    if(start.matches?.('input[type="date"]'))enhanceDateInput(start);
    if(start.matches?.('input[type="file"]'))enhanceFileInput(start);
    start.querySelectorAll?.('input[type="date"],input[data-hp-localized-date="1"]').forEach(enhanceDateInput);
    start.querySelectorAll?.('input[type="file"],input[data-hp-localized-file="1"]').forEach(enhanceFileInput);
    start.querySelectorAll?.('input,select,textarea').forEach(el=>el.lang=currentCode);
  }

  function translateTree(root = document) {
    if (applying) return;
    applying = true;
    try {
      const start = root.nodeType === Node.ELEMENT_NODE ? root : document.documentElement;
      if (start.matches?.('[data-i18n], [data-i18n-placeholder], [data-i18n-title], [data-i18n-aria-label], [data-i18n-alt]')) applyKeyedElement(start);
      start.querySelectorAll?.('[data-i18n], [data-i18n-placeholder], [data-i18n-title], [data-i18n-aria-label], [data-i18n-alt]').forEach(applyKeyedElement);
      if (start.nodeType === Node.ELEMENT_NODE) applyLegacyAttributes(start);
      start.querySelectorAll?.('[placeholder],[title],[aria-label],[alt]').forEach(applyLegacyAttributes);
      enhanceLocalizedControls(start);
      const walker = document.createTreeWalker(start, NodeFilter.SHOW_TEXT);
      let n;
      while ((n = walker.nextNode())) translateTextNode(n);
      document.documentElement.lang = currentCode;
      document.documentElement.dataset.language = currentCode;
      document.dispatchEvent(new CustomEvent('haushaltpro:language-applied',{detail:{language:currentCode,locale:currentLocale}}));
    } finally {
      applying = false;
    }
  }

  function addLanguageSwitcher() {
    if (document.getElementById('hpLanguageSwitcher')) return;
    const wrap = document.createElement('div');
    wrap.id = 'hpLanguageSwitcher';
    wrap.className = 'hp-language-switcher';
    const label = document.createElement('label');
    label.htmlFor = 'hpLanguageSelect';
    label.dataset.i18n = 'language.label';
    label.textContent = t('language.label','Sprache');
    const select = document.createElement('select');
    select.id = 'hpLanguageSelect';
    select.setAttribute('aria-label', t('language.label','Sprache'));
    for (const lang of manifest.languages || []) {
      const opt = document.createElement('option');
      opt.value = lang.code;
      opt.textContent = lang.nativeName || lang.name || lang.code;
      opt.selected = lang.code === currentCode;
      select.append(opt);
    }
    select.addEventListener('change', async () => setLanguage(select.value));
    wrap.append(label, select);
    document.body.append(wrap);
  }

  async function loadCatalog(code) {
    const meta = languageMeta(code);
    const loaded = await fetchJson(BASE_PATH + meta.file);
    return {meta, loaded};
  }

  async function setLanguage(code, {persist=true} = {}) {
    if (!supported(code)) code = manifest?.default || 'de';
    const {meta, loaded} = await loadCatalog(code);
    currentCode = code;
    currentLocale = meta.locale || loaded?.meta?.locale || (code === 'en' ? 'en-GB' : 'de-DE');
    catalog = loaded;
    if (persist) localStorage.setItem(STORAGE_KEY, code);
    const select = document.getElementById('hpLanguageSelect');
    if (select) select.value = code;
    translateTree(document.documentElement);
    document.dispatchEvent(new CustomEvent('haushaltpro:language-changed',{detail:{language:currentCode,locale:currentLocale}}));
  }

  function audit() {
    const missing = new Set();
    if (currentCode === (manifest?.default || 'de')) return [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = walker.nextNode())) {
      const parent = n.parentElement;
      if (!parent || /^(SCRIPT|STYLE|CODE|PRE)$/i.test(parent.tagName)) continue;
      const original = (originalText.get(n) ?? n.nodeValue ?? '').trim();
      if (!original || /^[-–—+±‹›«»·↔↗↻\d\s.,:%/€()#]+$/.test(original)) continue;
      if (!catalog?.legacy?.[original] && !Object.values(catalog?.messages || {}).includes(n.nodeValue?.trim())) {
        const patternHit = (catalog?.patterns || []).some(x => { try { return new RegExp(x.source).test(original); } catch { return false; } });
        if (!patternHit && original === (n.nodeValue || '').trim()) missing.add(original);
      }
    }
    return [...missing].sort();
  }

  async function init() {
    manifest = await fetchJson(BASE_PATH + 'languages.json');
    const baseMeta = languageMeta(manifest.default || 'de');
    baseCatalog = await fetchJson(BASE_PATH + baseMeta.file);
    currentCode = detectLanguage();
    const selected = await loadCatalog(currentCode);
    catalog = selected.loaded;
    currentLocale = selected.meta.locale || catalog?.meta?.locale || 'de-DE';
    addLanguageSwitcher();
    translateTree(document.documentElement);
    const observer = new MutationObserver(mutations => {
      if (applying) return;
      for (const m of mutations) {
        if (m.type === 'characterData') translateTextNode(m.target);
        for (const node of m.addedNodes || []) {
          if (node.nodeType === Node.TEXT_NODE) translateTextNode(node);
          else if (node.nodeType === Node.ELEMENT_NODE) translateTree(node);
        }
      }
    });
    observer.observe(document.body,{childList:true,subtree:true,characterData:true});
    window.HaushaltProI18n = Object.freeze({
      t, translateText:translateLegacy, formatDate:formatIsoDate, formatDateTime, language:()=>currentCode, locale:()=>currentLocale, setLanguage,
      retranslate:()=>translateTree(document.documentElement), audit,
      languages:()=>manifest.languages.map(x=>({...x}))
    });
    document.dispatchEvent(new CustomEvent('haushaltpro:i18n-ready',{detail:{language:currentCode,locale:currentLocale}}));
  }

  // App code may ask for locale before async catalogs are ready.
  window.HaushaltProI18n = Object.freeze({
    t:(key,fallback='')=>fallback||key, translateText:s=>String(s??''), formatDate:v=>String(v??''), formatDateTime:v=>String(v??''),
    language:()=>localStorage.getItem(STORAGE_KEY)||'de',
    locale:()=>((localStorage.getItem(STORAGE_KEY)||'de')==='en'?'en-GB':'de-DE'),
    setLanguage:async code=>{localStorage.setItem(STORAGE_KEY,code);location.reload()},
    retranslate:()=>{}, audit:()=>[], languages:()=>[]
  });

  init().catch(err => console.error('HaushaltPro i18n init failed', err));
})();
