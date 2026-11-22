import {aedName, accessState, safeURL, confidence, filterRows, labelURL, labelSVG, sourceLabel} from './core.js';
import {openTools,closeTools} from './drawer.js';

const $ = id => document.getElementById(id);
const state = {rows:[], filtered:[], page:0, pageSize:3, selected:null, map:null, layers:null, controller:null, uploadReport:null, label:null, exportController:null, view:'mapa', cityBounds:null, committedCity:'',origin:null};
let file = null;
let lastTrigger = null;
let markerLoading = null;
let markerRenderPending = false;
const deepID = new URLSearchParams(location.search).get('aed');

function element(tag, text, className) { const node=document.createElement(tag); if(text!==undefined) node.textContent=text; if(className) node.className=className; return node; }
function announce(message) { $('accessibility-announcement').textContent=message; }
function notice(id, message, kind='') { const node=$(id); node.textContent=message; node.className=`notice ${kind}`; node.hidden=!message; }
function remember(key,value) { try { localStorage.setItem(key,value); } catch {} }
function recall(key) { try { return localStorage.getItem(key); } catch { return null; } }
const fontSizes=[100,120,135];
let fontSize=fontSizes.includes(Number(recall('aed-font-size'))) ? Number(recall('aed-font-size')) : 100;
let highContrast=recall('aed-contrast')==='high';
function applyPreferences() {
  document.documentElement.style.fontSize=`${fontSize}%`;
  document.documentElement.dataset.largeText=String(fontSize>=135);
  document.documentElement.dataset.contrast=highContrast?'high':'normal';
  $('contrast-toggle').setAttribute('aria-pressed',String(highContrast));
  $('font-value').textContent=`${fontSize}%`;
  $('font-toggle').setAttribute('aria-label',`Powiększ tekst: obecnie ${fontSize} procent. Następny poziom ${fontSizes[(fontSizes.indexOf(fontSize)+1)%fontSizes.length]} procent.`);
  if (state.map) requestAnimationFrame(()=>state.map.invalidateSize());
}
applyPreferences();
$('contrast-toggle').addEventListener('click',()=>{highContrast=!highContrast;remember('aed-contrast',highContrast?'high':'normal');applyPreferences();announce(highContrast?'Włączono wysoki kontrast.':'Włączono standardowy kontrast.');});
$('font-toggle').addEventListener('click',()=>{fontSize=fontSizes[(fontSizes.indexOf(fontSize)+1)%fontSizes.length];remember('aed-font-size',String(fontSize));applyPreferences();announce(`Rozmiar tekstu: ${fontSize} procent.`);});

function setView(view,focus=false) {
  state.view='mapa';
  if(view==='qr')openQR();
  if(view==='dysponent'){openTools('tool-owner',{focus,pinned:true});if(state.selected)fillLabel(state.selected);}
  if(view==='integracja')openTools('tool-data',{focus,pinned:true});
  history.replaceState(null,'',`${location.pathname}${location.search}#${['dysponent','integracja','qr'].includes(view)?view:'mapa'}`);
  requestAnimationFrame(()=>state.map?.invalidateSize());
  document.dispatchEvent(new CustomEvent('aed:view',{detail:view}));
}
document.addEventListener('tools:section',event=>{
  if(event.detail==='tool-data'){loadExport();loadSourceStats();}
  if(event.detail==='tool-owner'&&state.selected)fillLabel(state.selected);
});
window.addEventListener('hashchange',()=>setView(location.hash.slice(1)));

function clusterIcon(cluster) {
  const count=cluster.getChildCount();
  const size=count<10?'small':count<100?'medium':'large';
  const diameter={small:44,medium:56,large:68}[size];
  // Warstwa jest ukryta dla czytników; równoważne działania są na liście AED.
  cluster.options.keyboard=false;
  cluster.options.title=`${count} punktów AED — kliknij, aby przybliżyć lub rozsunąć`;
  return L.divIcon({className:`aed-cluster aed-cluster--${size}`,html:`<span>${count}</span>`,
    iconSize:[diameter,diameter],iconAnchor:[diameter/2,diameter/2]});
}
function markerChunkProgress(processed,total) {
  if(processed!==total||!markerLoading)return;
  const batch=markerLoading;
  // addLayers kończy aktualizację klastrów po tym callbacku.
  Promise.resolve().then(()=>{
    if(markerLoading!==batch)return;
    markerLoading=null;
    if(markerRenderPending)renderMarkers();
    else $('map').setAttribute('aria-busy','false');
  });
}
function initMap() {
  if (!window.L) { $('map').append(element('p','Mapa jest niedostępna. Wszystkie punkty znajdziesz na liście.','notice'));return; }
  state.map=L.map('map',{scrollWheelZoom:false,keyboard:true,preferCanvas:true}).setView([52.05,19.4],6);
  state.map.getPane('markerPane').setAttribute('aria-hidden','true'); // Równoważna lista zapewnia nazwy i działania bez setek powtórzeń dla czytnika.
  const tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'}).addTo(state.map);
  tiles.on('tileerror',()=>{$('tile-status').hidden=false;});
  state.layers=(L.markerClusterGroup?L.markerClusterGroup({
    chunkedLoading:true,chunkInterval:40,chunkDelay:16,
    maxClusterRadius:55,disableClusteringAtZoom:15,spiderfyOnMaxZoom:true,
    showCoverageOnHover:false,animate:!(window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches??false),
    iconCreateFunction:clusterIcon,chunkProgress:markerChunkProgress
  }):L.layerGroup()).addTo(state.map);
  if(!L.markerClusterGroup)notice('map-alert','Grupowanie punktów jest niedostępne. Przybliż mapę lub skorzystaj z listy AED.','warning');
  const controls=$('map').querySelectorAll('.leaflet-control-zoom a');
  if (controls[0]) { controls[0].title='Powiększ mapę';controls[0].setAttribute('aria-label','Powiększ mapę'); }
  if (controls[1]) { controls[1].title='Pomniejsz mapę';controls[1].setAttribute('aria-label','Pomniejsz mapę'); }
}
function fitMap() {
  if (!state.map) return;
  if(state.cityBounds){const [s,n,w,e]=state.cityBounds;state.map.fitBounds([[s,w],[n,e]],{padding:[24,24],maxZoom:14,animate:false});return;}
  if(!state.filtered.length)return;
  const points=state.filtered.map(row=>[row.lat,row.lon]);
  state.map.fitBounds(L.latLngBounds(points),{padding:[32,32],maxZoom:15,animate:false});
}
function renderMarkers() {
  if(!state.layers)return;
  // Nie uruchamiaj równoległych addLayers: spóźnione porcje poprzedniego
  // filtra mogłyby przywrócić stare punkty po clearLayers().
  if(markerLoading){markerRenderPending=true;return;}
  markerRenderPending=false;
  state.layers.clearLayers();
  const markers=state.filtered.map(row=>{
    const status=accessState(row);
    const icon=L.divIcon({className:'aed-map-marker',html:`<div class="map-pin ${status.kind}"><span>${status.symbol}</span></div>`,iconSize:[32,38],iconAnchor:[16,35]});
    const marker=L.marker([row.lat,row.lon],{icon,keyboard:false,title:aedName(row)});
    marker.on('click',()=>showDetails(row));
    return marker;
  });
  if(state.layers.addLayers){
    markerLoading={};$('map').setAttribute('aria-busy','true');
    state.layers.addLayers(markers);
  }else markers.forEach(marker=>state.layers.addLayer(marker));
  fitMap();
}
function badge(row) {const status=accessState(row);return element('span',['open','all-day'].includes(status.kind)?'✓ Otwarty teraz':status.label,`badge ${status.kind}`);}
function address(row) { return [row.ulica_numer,[row.kod_pocztowy,row.miejscowosc||row.miejscowosc_wyszukiwania].filter(Boolean).join(' ')].filter(Boolean).join(', ') || 'Dokładny adres nie został podany'; }
function renderList() {
  const list=$('aed-list');list.replaceChildren();
  const from=state.page*state.pageSize;
  const fragment=document.createDocumentFragment();
  state.filtered.slice(from,from+state.pageSize).forEach(row=>{
    const card=element('li',undefined,`aed-card${state.selected?.id_aed===row.id_aed?' selected':''}`);
    card.dataset.aedId=row.id_aed;
    const top=element('div',undefined,'card-top');top.append(badge(row));
    const bottom=element('div',undefined,'card-bottom');
    const button=element('button','Jak znaleźć AED','details-button');button.type='button';button.setAttribute('aria-label',`Jak znaleźć AED: ${aedName(row)}`);button.addEventListener('click',()=>showDetails(row,button));bottom.append(button);
    card.append(top,element('h3',aedName(row)),element('p',address(row),'card-address'),element('p',row.opis_lokalizacji_wewnatrz||'Brak dokładnego opisu miejsca. Sprawdź kartę urządzenia.','card-description'));
    card.append(bottom);fragment.append(card);
  });
  list.append(fragment);
  $('empty-results').hidden=Boolean(state.filtered.length);
  $('include-osm').hidden=$('source-filter').value!=='danegov';
  $('result-count').textContent=`${state.filtered.length} punktów${state.filtered.length ? ` · pokazano ${from+1}–${Math.min(from+state.pageSize,state.filtered.length)}`:''}`;
  $('pagination').hidden=state.filtered.length<=state.pageSize;
  $('previous-page').disabled=state.page===0;
  $('next-page').disabled=(state.page+1)*state.pageSize>=state.filtered.length;
  $('page-caption').textContent=`Strona ${state.page+1} z ${Math.max(1,Math.ceil(state.filtered.length/state.pageSize))}`;
}
function applySearch() { state.filtered=filterRows(state.rows,$('aed-search').value);state.page=0;renderList();renderMarkers(); }

async function loadAED({deep=false,resolveCity=false}={}) {
  if(resolveCity)state.committedCity=$('city-filter').value.trim();
  state.controller?.abort();const controller=new AbortController();state.controller=controller;
  const timeout=setTimeout(()=>controller.abort(),resolveCity?45000:20000);
  $('results-panel').setAttribute('aria-busy','true');$('data-error').hidden=true;
  const selection=$('source-filter').value==='danegov'?' · dane.gov.pl':$('source-filter').value==='osm'?' · OpenStreetMap':'';
  $('results-heading').textContent=$('open-now').checked?'Otwarte urządzenia':'Urządzenia w okolicy';
  $('filter-explanation').textContent=$('open-now').checked?'Pomijamy urządzenia na klucz, poza godzinami dostępu i bez potwierdzonego harmonogramu.':'Pokazujemy również urządzenia zamknięte, na klucz i o nieznanej dostępności. Sprawdź oznaczenia.';
  const params=new URLSearchParams({tylko_otwarte_teraz:String($('open-now').checked),zrodlo:$('source-filter').value,geokoduj:String(resolveCity)});
  if(state.committedCity)params.set('miasto',state.committedCity);
  if(state.origin){params.set('lat',state.origin.lat);params.set('lon',state.origin.lon);params.set('radius_km',15);}
  try {
    const response=await fetch(deep&&deepID?`/api/aed/${encodeURIComponent(deepID)}`:`/api/aed?${params}`,{signal:controller.signal,headers:{Accept:'application/json'}});
    if(!response.ok){const problem=await response.json().catch(()=>({}));throw new Error(typeof problem.detail==='string'?problem.detail:'Serwer jest chwilowo niedostępny. Spróbuj ponownie.');}
    const received=await response.json().catch(()=>{throw new Error('Nie udało się odczytać listy urządzeń. Spróbuj ponownie.');});
    const payload=deep&&deepID?{items:[received],evaluated_at:new Date().toISOString(),source:{},scope:{matched_before_availability:1}}:received;
    if(state.controller!==controller)return;
    if(!Array.isArray(payload.items))throw new Error('Nie udało się odczytać listy urządzeń. Spróbuj ponownie.');
    state.rows=payload.items.filter(row=>Number.isFinite(row.lat)&&Number.isFinite(row.lon));
    state.cityBounds=payload.city?.bounds||null;
    $('evaluation-time').textContent=`Sprawdzono ${new Intl.DateTimeFormat('pl-PL',{hour:'2-digit',minute:'2-digit',timeZone:'Europe/Warsaw'}).format(new Date(payload.evaluated_at))} · Europe/Warsaw`;
    const downloaded=payload.source?.retrieved_at;
    const scope=payload.scope||{};
    $('scope-caption').textContent=`Zasięg: ${payload.city?.display_name||state.committedCity||'cała Polska'}`;
    $('scope-details').textContent=`Ogólnopolska baza: ${Number(scope.national_records||0).toLocaleString('pl-PL')} punktów. Z API dane.gov.pl: ${scope.danegov_points||0} punktów po deduplikacji. Dla wybranego miasta i źródła: ${scope.matched_before_availability||0} przed filtrem dostępności. Katalog instytucjonalny ma niepełne pokrycie kraju.`;
    $('source-caption').textContent=`Źródła: dane.gov.pl + OpenStreetMap${payload.source?.from_cache?' · OSM z lokalnej kopii':''}${downloaded?` · OSM pobrano ${new Intl.DateTimeFormat('pl-PL',{dateStyle:'short',timeStyle:'short',timeZone:'Europe/Warsaw'}).format(new Date(downloaded))}`:''}. Szczegóły w zakładce Integracja.`;
    applySearch();
    document.dispatchEvent(new CustomEvent('aed:loaded'));
    if(deep && deepID) {
      const row=state.rows.find(item=>item.id_aed===deepID||(item.merged_ids||[]).includes(deepID));
      if(row)showDetails(row);
      else notice('map-alert','Nie znaleziono AED z tego kodu QR w aktualnej bazie. Wyszukaj obiekt lub sprawdź źródło danych.');
    }
  } catch(error) {
    if(state.controller!==controller)return;
    state.rows=[];state.cityBounds=null;applySearch();
    $('data-error-text').textContent=error.name==='AbortError'?'Nie udało się pobrać aktualnych danych w wyznaczonym czasie. Spróbuj ponownie.':error.name==='TypeError'?'Brak połączenia z aplikacją. Spróbuj ponownie.':`Nie udało się wyszukać AED. ${error.message}`;
    $('data-error').hidden=false;
    $('evaluation-time').textContent='Aktualna dostępność nie została potwierdzona';
  } finally {
    clearTimeout(timeout);
    if(state.controller===controller)$('results-panel').setAttribute('aria-busy','false');
  }
}
$('open-now').addEventListener('change',()=>{
  $('results-heading').textContent=$('open-now').checked?'Dostępne w tej chwili':'Wszystkie punkty AED';
  $('filter-explanation').textContent=$('open-now').checked?'Pomijamy urządzenia na klucz, poza godzinami dostępu i bez potwierdzonego harmonogramu.':'Pokazujemy również urządzenia zamknięte, na klucz i o nieznanej dostępności. Sprawdź oznaczenia.';
  loadAED();
});
$('show-national-open').addEventListener('click',()=>{
  state.origin=null;document.dispatchEvent(new CustomEvent('aed:origin-reset'));
  $('city-filter').value='';state.committedCity='';$('aed-search').value='';$('open-now').checked=true;$('source-filter').value='wszystkie';
  $('results-heading').textContent='Dostępne w tej chwili';
  $('filter-explanation').textContent='Wszystkie miejscowości. Pomijamy urządzenia na klucz, poza godzinami dostępu i bez potwierdzonego harmonogramu.';
  loadAED();
});
$('show-danegov-points').addEventListener('click',()=>{
  state.origin=null;document.dispatchEvent(new CustomEvent('aed:origin-reset'));
  $('city-filter').value='';state.committedCity='';$('aed-search').value='';$('source-filter').value='danegov';$('open-now').checked=false;
  $('results-heading').textContent='Punkty z API dane.gov.pl — cała Polska';
  $('filter-explanation').textContent='Pokazujemy wszystkie zintegrowane punkty z API dane.gov.pl, również zamknięte i o nieznanej dostępności. Sprawdź oznaczenia.';
  loadAED();
});
$('source-filter').addEventListener('change',()=>{loadAED();document.dispatchEvent(new CustomEvent('aed:filters'));});
$('include-osm').addEventListener('click',()=>{$('source-filter').value='wszystkie';$('aed-search').value='';loadAED();});
$('show-unconfirmed').addEventListener('click',()=>{
  $('aed-search').value='';$('open-now').checked=false;
  $('results-heading').textContent='Wszystkie punkty AED';
  $('filter-explanation').textContent='Pokazujemy również urządzenia zamknięte, na klucz i o nieznanej dostępności. Sprawdź oznaczenia.';
  loadAED();
});
$('aed-search').addEventListener('input',applySearch);

$('retry-data').addEventListener('click',()=>loadAED({resolveCity:true}));$('fit-map').addEventListener('click',fitMap);
for(const [id,increment] of [['previous-page',-1],['next-page',1]])$(id).addEventListener('click',()=>{state.page+=increment;renderList();$('results-heading').tabIndex=-1;$('results-heading').focus();});

function sourceLink(url,text) {
  const safe=safeURL(url);
  if(!safe)return element('span',text || 'Nieprawidłowy adres źródła');
  const link=element('a',text||safe);link.href=safe;link.target='_blank';link.rel='noopener noreferrer';link.append(element('span',' (nowa karta)','sr-only'));return link;
}
function showDetails(row,trigger) {
  state.selected=row;if(!$('aed-dialog').open)lastTrigger=trigger||document.activeElement;
  document.querySelectorAll('.aed-card').forEach(card=>card.classList.toggle('selected',card.dataset.aedId===row.id_aed));
  const detail=$('aed-detail');detail.replaceChildren(badge(row));
  const title=element('h2',aedName(row),'detail-title');title.id='detail-name';
  const location=element('div',undefined,'detail-location');location.append(element('h3','Jak znaleźć urządzenie?'),element('p',row.opis_lokalizacji_wewnatrz||'Źródło nie zawiera opisu piętra, holu ani dokładnego położenia.'));
  detail.append(title,element('p',address(row),'detail-address'),location);
  if(row.field_access_alert||['closed','locked'].includes(accessState(row).kind))detail.append(element('p','To urządzenie może być zamknięte lub uszkodzone. Wybierz inne otwarte miejsce.','notice critical'));
  if(row.status_techniczny==='niezweryfikowany')detail.append(element('p','Opiekun nie potwierdził stanu urządzenia.','field-help'));
  const nav=element('a','Prowadź pieszo','button button-blue');
  const params=new URLSearchParams({api:1,destination:`${row.lat},${row.lon}`,travelmode:'walking'});
  if(state.origin&&state.origin.kind!=='search')params.set('origin',`${state.origin.lat},${state.origin.lon}`);
  nav.href=`https://www.google.com/maps/dir/?${params}`;nav.target='_blank';nav.rel='noopener noreferrer';nav.setAttribute('aria-label','Prowadź pieszo — otwiera nawigację w nowej karcie');detail.append(nav);
  const score=confidence(row.confidence_score);
  const hasScore=(typeof row.confidence_score==='number'||(typeof row.confidence_score==='string'&&row.confidence_score.trim()!==''))&&Number.isFinite(Number(row.confidence_score));
  const quality=element('section',undefined,'information-quality');quality.setAttribute('aria-labelledby','information-quality-title');
  const qualityHeader=element('div',undefined,'information-quality-header');
  const qualityTitle=element('h3','Jakość informacji');qualityTitle.id='information-quality-title';
  qualityHeader.append(qualityTitle,element('strong',hasScore?`${score.toLocaleString('pl-PL',{maximumFractionDigits:1})}%`:'Brak oceny','information-quality-value'));
  quality.append(qualityHeader);
  if(hasScore){const qualityTrack=element('div',undefined,'confidence-track');qualityTrack.setAttribute('aria-hidden','true');const qualityBar=element('span');qualityBar.style.width=`${score}%`;qualityTrack.append(qualityBar);quality.append(qualityTrack);}
  quality.append(element('p','Ocena kompletności danych i ich źródeł.','information-quality-help'));
  const fieldDate=row.last_field_verification?new Date(row.last_field_verification):null;
  quality.append(element('p',fieldDate&&Number.isFinite(fieldDate.getTime())?`Ostatnie zgłoszenie z miejsca: ${fieldDate.toLocaleString('pl-PL')}`:'Brak zgłoszeń z miejsca.','information-quality-date'));
  detail.append(quality);
  const expert=$('expert-device');expert.replaceChildren(element('h3',aedName(row)));
  const definition=element('dl',undefined,'detail-grid');
  const values=[['Godziny dostępu',row.godziny_otwarcia_osm||'Brak potwierdzonego harmonogramu'],['Klucz lub kod',row.wymagany_klucz_lub_kod||'Brak danych'],['Stan techniczny w źródle',({sprawny:'Sprawny',serwis:'Serwis',niezweryfikowany:'Niezweryfikowany'})[row.status_techniczny]||'Brak danych'],['Dostępność bez barier',({tak:'Tak',nie:'Nie',niezweryfikowano:'Niezweryfikowana'})[row.dostepnosc_niepelnosprawni]||'Brak danych'],['Ostatnia aktualizacja źródła',row.data_aktualizacji||'Brak potwierdzonej daty'],['Ostatnia weryfikacja terenowa',row.last_field_verification?new Date(row.last_field_verification).toLocaleString('pl-PL'):'Brak zgłoszeń'],['Identyfikator AED',row.id_aed]];
  values.forEach(([label,value])=>{const group=element('div');group.append(element('dt',label),element('dd',value));definition.append(group);});expert.append(definition);
  expert.append(element('h3',`Wiarygodność danych (Confidence Score): ${score}%`));
  const track=element('div',undefined,'confidence-track');track.setAttribute('aria-hidden','true');const bar=element('span');bar.style.width=`${score}%`;track.append(bar);expert.append(track,element('p','Wskaźnik mierzy kompletność informacji z premią 10 pkt za instytucjonalne źródło dane.gov.pl. Nie potwierdza sprawności urządzenia.','detail-footnote'));
  if(Object.keys(row.conflicts||{}).length)expert.append(element('p','Źródła podają rozbieżne informacje. Sprawdź źródła referencyjne.','notice'));
  if(row.field_access_alert)expert.append(element('p',row.field_access_alert==='damaged'?'Zgłoszono uszkodzenie lub brak wyposażenia. Nie rekomendujemy tego urządzenia.':'Zgłoszono brak dostępu. Nie rekomendujemy tego urządzenia.','notice critical'));
  expert.append(element('h3','Źródła referencyjne'));
  const sources=element('ul',undefined,'source-list');const seen=new Set();
  for(const source of [{url:row.zrodlo_referencyjne,name:'Źródło główne'},...(row.sources||[])]) {
    if(!safeURL(source.url)||seen.has(source.url))continue;seen.add(source.url);
    const li=element('li');li.append(sourceLink(source.url,`${source.name||'Źródło'} · ${source.url}`));sources.append(li);
  }
  expert.append(element('p',row.zrodlo_referencyjne||'Brak źródła głównego.','detail-footnote'),sources);
  const actions=element('div',undefined,'dialog-actions');const label=element('button','Przygotuj etykietę QR','button button-primary');label.type='button';label.addEventListener('click',()=>{$('aed-dialog').close();setView('dysponent',true);fillLabel(row);$('label-id').focus();});actions.append(label);expert.append(actions);
  if(state.map)state.map.setView([row.lat,row.lon],Math.max(15,state.map.getZoom()),{animate:false});
  if(!$('aed-dialog').open)$('aed-dialog').showModal();
  $('close-details').focus();
  document.dispatchEvent(new CustomEvent('aed:detail',{detail:row}));
}
$('close-details').addEventListener('click',()=>$('aed-dialog').close());
$('aed-dialog').addEventListener('close',()=>{if(lastTrigger?.isConnected&&!$('tools-drawer').contains(document.activeElement))lastTrigger.focus();});

function chooseFile(selected) {
  if($('upload-form').getAttribute('aria-busy')==='true') {notice('upload-message','Trwa walidacja wybranego pliku. Poczekaj na raport.');return;}
  notice('upload-message','');$('validation-results').hidden=true;state.uploadReport=null;
  if(!selected)return;
  if(!/\.(xlsx|csv)$/i.test(selected.name)){file=null;notice('upload-message','Wybierz plik .xlsx lub .csv.','error');}
  else if(selected.size>3*1024*1024){file=null;notice('upload-message','Plik przekracza limit 3 MiB. Zmniejsz plik i wybierz go ponownie.','error');}
  else if(selected.size===0){file=null;notice('upload-message','Wybrany plik jest pusty.','error');}
  else file=selected;
  $('file-name').textContent=file?`${file.name} · ${(file.size/1024).toFixed(1)} KiB`:'Nie wybrano poprawnego pliku';
  $('validate-button').disabled=!file;
}
$('upload-file').addEventListener('change',event=>chooseFile(event.target.files[0]));
for(const eventName of ['dragenter','dragover'])$('drop-zone').addEventListener(eventName,event=>{event.preventDefault();$('drop-zone').classList.add('drag-over');});
for(const eventName of ['dragleave','drop'])$('drop-zone').addEventListener(eventName,event=>{event.preventDefault();$('drop-zone').classList.remove('drag-over');});
$('drop-zone').addEventListener('drop',event=>{if(event.dataTransfer.files.length!==1){notice('upload-message','Wybierz jeden plik do walidacji.','error');return;}chooseFile(event.dataTransfer.files[0]);});
$('upload-form').addEventListener('submit',async event=>{
  event.preventDefault();if(!file)return;
  $('validate-button').disabled=true;$('validate-button').textContent='Sprawdzanie danych…';
  $('upload-form').setAttribute('aria-busy','true');notice('upload-message','Trwa walidacja pliku.');
  const form=new FormData();form.append('file',file);
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),45000);
  try {
    const response=await fetch('/api/validate-upload',{method:'POST',body:form,signal:controller.signal});
    const report=await response.json();
    if(!response.ok)throw new Error(typeof report.detail==='string'?report.detail:`Błąd walidacji: ${response.status}`);
    state.uploadReport=report;renderValidation(report);notice('upload-message','');
  } catch(error) {notice('upload-message',error.name==='AbortError'?'Walidacja trwała zbyt długo. Spróbuj ponownie.':`Nie udało się zwalidować pliku. ${error.message}`,'error');}
  finally{clearTimeout(timer);$('validate-button').disabled=!file;$('validate-button').textContent='Sprawdź poprawność danych';$('upload-form').setAttribute('aria-busy','false');}
});
function renderValidation(report) {
  $('validation-results').hidden=false;
  $('validation-summary').replaceChildren(element('p',report.valid?`Dane poprawne. Poprawne wiersze: ${report.rows_valid} z ${report.rows_total}.`:`Wymagane poprawki. Poprawne wiersze: ${report.rows_valid} z ${report.rows_total}. Odrzucone: ${report.rows_invalid}.`,`notice ${report.valid?'success':'error'}`));
  $('validation-errors').replaceChildren();$('validation-warnings').replaceChildren();
  if(report.errors?.length){
    const wrapper=element('div',undefined,'validation-table-wrap');wrapper.tabIndex=0;wrapper.setAttribute('aria-label','Tabela błędów walidacji; przewijana');
    const table=element('table');table.append(element('caption',`Co poprawić — ${report.errors.length} błędów`));
    const head=element('thead');const tr=element('tr');for(const label of ['Wiersz','Pole','Jak poprawić']){const th=element('th',label);th.scope='col';tr.append(th);}head.append(tr);table.append(head);
    const body=element('tbody');for(const error of report.errors.slice(0,200)){const tr=element('tr');tr.append(element('td',error.row??'—'),element('td',error.field||'Struktura pliku'),element('td',error.message));body.append(tr);}table.append(body);wrapper.append(table);$('validation-errors').append(wrapper);
    if(report.errors.length>200)$('validation-errors').append(element('p','Pokazano pierwsze 200 błędów. Popraw je i zwaliduj plik ponownie.','field-help'));
  }
  if(report.warnings?.length)$('validation-warnings').append(element('p',`Uwagi: ${report.warnings.slice(0,3).map(w=>`wiersz ${w.row}: ${w.message}`).join(' ')}${report.warnings.length>3?' Pozostałe rekordy również zawierają uwagi.':''}`,'notice'));
  for(const id of ['download-validated-json','download-validated-csv'])$(id).disabled=!(report.normalized_json?.length);
  $('validation-heading').focus();
}
function download(payload,type,filename) { const url=URL.createObjectURL(new Blob([payload],{type}));const link=element('a');link.href=url;link.download=filename;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000); }
$('download-validated-json').addEventListener('click',()=>download(JSON.stringify(state.uploadReport.normalized_json,null,2),'application/json;charset=utf-8','aed_poprawne.json'));
$('download-validated-csv').addEventListener('click',()=>download(state.uploadReport.normalized_csv,'text/csv;charset=utf-8','aed_poprawne.csv'));

function fillLabel(row) { $('label-id').value=row.id_aed;$('label-name').value=aedName(row).slice(0,80); }
function openQR(){
  openTools('tool-owner',{focus:false,pinned:true});
  if(state.selected)fillLabel(state.selected);
  document.querySelector('.label-generator').scrollIntoView({block:'start'});
  $('label-id').focus({preventScroll:true});
}
$('qr-shortcut').addEventListener('click',()=>setView('qr'));
$('label-base').value=`${location.origin}${location.pathname}`;
$('label-form').addEventListener('submit',async event=>{
  event.preventDefault();notice('label-error','');
  try {
    const id=$('label-id').value.trim();const name=$('label-name').value.trim();
    if(!name)throw new Error('Wpisz nazwę miejsca.');
    const url=labelURL($('label-base').value.trim(),id);
    const response=await fetch(`/api/aed/${encodeURIComponent(id)}/passport.svg?${new URLSearchParams({base_url:$('label-base').value.trim(),name})}`);
    if(!response.ok){const error=await response.json();throw new Error(error.detail||'Nie udało się wygenerować paszportu.');}
    state.label={svg:await response.text(),id};
    $('label-preview').innerHTML=state.label.svg; // Wyłącznie lokalny generator SVG; tekst użytkownika jest escapowany.
    $('label-output').hidden=false;
    const hostname=new URL(url).hostname;
    $('label-link').textContent=`Kod prowadzi do: ${url}${['localhost','127.0.0.1','[::1]'].includes(hostname)?' — adres lokalny. Przed drukiem ustaw publiczny adres aplikacji.':''}`;
    announce('Wygenerowano etykietę QR. Możesz pobrać SVG lub wydrukować etykietę.');
  } catch(error){notice('label-error',error.message,'error');$('label-output').hidden=true;}
});
$('download-label').addEventListener('click',()=>{if(state.label)download(state.label.svg,'image/svg+xml;charset=utf-8',`etykieta-${state.label.id}.svg`);});
$('print-label').addEventListener('click',()=>window.print());

async function loadExport() {
  state.exportController?.abort();const controller=new AbortController();state.exportController=controller;
  const timer=setTimeout(()=>controller.abort(),20000);const format=$('export-format').value;
  $('export-preview').textContent='Wczytywanie podglądu…';$('export-preview').setAttribute('aria-busy','true');
  notice('export-message','');$('export-url').textContent=`GET /export/${format}`;
  $('download-export').href=`/export/${format}`;$('download-export').textContent=`Pobierz ${format==='xml'?'XML':format==='payload'?'JSON:API':format.toUpperCase()}`;
  try {
    const response=await fetch(`/export/${format}`,{headers:{Range:'bytes=0-40000'},signal:controller.signal});if(!response.ok)throw new Error(`API zwróciło błąd ${response.status}.`);
    const text=await response.text();const limit=40000;
    const total=Number(response.headers.get('Content-Range')?.split('/').pop()||new Blob([text]).size);
    const truncated=total>new Blob([text]).size||text.length>limit;
    $('export-preview').textContent=truncated?`${text.slice(0,limit)}\n…`:text;
    $('export-size').textContent=`${(total/1024).toLocaleString('pl-PL',{maximumFractionDigits:1})} KiB`;
    $('export-preview-note').textContent=truncated?'Podgląd ograniczono do pierwszych 40 kB. Pobierz plik, aby otrzymać cały, poprawny składniowo zasób.':'Podgląd zawiera cały zasób.';
    $('export-preview').dataset.loaded='true';
  }catch(error){if(state.exportController!==controller)return;$('export-preview').textContent='Podgląd jest niedostępny.';notice('export-message','Nie udało się pobrać zasobu. Sprawdź połączenie i odśwież podgląd.','error');}
  finally{clearTimeout(timer);if(state.exportController===controller)$('export-preview').setAttribute('aria-busy','false');}
}
$('export-format').addEventListener('change',loadExport);$('refresh-export').addEventListener('click',loadExport);

function renderSourceStats(data) {
  const totals=$('sources-totals');totals.replaceChildren();
  for(const [label,value] of [['Rekordy OSM',data.osm_records],['Rekordy dane.gov.pl',data.danegov_records],['Połączone duplikaty',data.duplicates_merged],['Wynik integracji',data.integrated_records]]) {
    const group=element('div');group.append(element('dt',label),element('dd',Number(value||0).toLocaleString('pl-PL')));totals.append(group);
  }
  const body=$('sources-body');body.replaceChildren();
  for(const ds of data.datasets||[]) {
    const tr=element('tr');const title=element('td');title.append(sourceLink(ds.url,ds.title||`Zbiór ${ds.id}`),element('span',`ID: ${ds.id}`,'source-id'));tr.append(title);
    tr.append(element('td',ds.institution_title||'Nie ustalono instytucji'),element('td',String(ds.records_count||0)));
    const status=element('td');const cached=data.danegov?.from_cache||ds.from_cache;
    status.append(element('span',ds.records_count?cached?'Zintegrowano · cache':'Zintegrowano · API':'Nie zintegrowano',`source-status ${ds.records_count?'success':'error'}`));
    if(!ds.records_count)status.append(element('p',ds.resources?.some(r=>r.error?.includes('HTML'))?'Adres zasobu zwraca HTML zamiast danych.':'Brak możliwych do odczytania współrzędnych.','field-help'));
    const rejected=(ds.resources||[]).reduce((sum,r)=>sum+(r.rejected_records?.length||0),0);
    if(rejected)status.append(element('p',`Odrzucone wiersze źródłowe: ${rejected}. Szczegóły: /api/sources/stats`,'field-help'));
    tr.append(status);body.append(tr);
  }
  if(!body.children.length){const row=element('tr');const cell=element('td','Brak zintegrowanych zbiorów w tej migawce.');cell.colSpan=4;row.append(cell);body.append(row);}
  const retrieved=data.danegov?.retrieved_at;
  const date=retrieved?new Date(retrieved).toLocaleString('pl-PL',{timeZone:'Europe/Warsaw'}):'brak daty';
  $('sources-freshness').textContent=`Dane.gov.pl pobrano: ${date} · ${data.danegov?.from_cache?'lokalna migawka offline':'odczyt z API'} · Grupy łączące dane.gov.pl i OSM: ${data.cross_source_groups||0}.`;
  if(data.danegov?.fallback_reason&&data.danegov.fallback_reason!=='offline_requested')notice('sources-message','API było niedostępne. Zachowano poprzednią migawkę danych.','error');
  $('sync-danegov').disabled=!!state.syncing||!!data.sync_in_progress||data.persistence?.writes_enabled===false;
  if(data.persistence?.writes_enabled===false)notice('sources-message','Mapa i pobieranie danych są dostępne. Zapisywanie zgłoszeń i synchronizacja wymagają podłączenia trwałej bazy danych.');
}
async function loadSourceStats() {
  try {const response=await fetch('/api/sources/stats',{signal:AbortSignal.timeout(15000)});if(!response.ok)throw new Error();renderSourceStats(await response.json());}
  catch {notice('sources-message','Nie udało się pobrać statystyk źródeł. Odśwież widok lub sprawdź serwer.','error');}
}
$('sync-danegov').addEventListener('click',async()=>{
  if(state.syncing)return;state.syncing=true;$('sync-danegov').disabled=true;$('sync-danegov').setAttribute('aria-busy','true');
  notice('sources-message','Trwa synchronizacja z API dane.gov.pl. Dotychczasowe dane są nadal dostępne; operacja może potrwać kilka minut.');
  try {
    const response=await fetch('/api/danegov/refresh',{method:'POST'});const data=await response.json();
    if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:`Błąd ${response.status}`);
    renderSourceStats(data);notice('sources-message',data.danegov?.from_cache?'API niedostępne — przebudowano zbiór z ostatniej poprawnej kopii.':'Synchronizacja zakończona. Dane, statystyki i eksporty zostały przebudowane.',data.danegov?.from_cache?'':'success');
    loadExport();loadAED();
  }catch(error){notice('sources-message',`Synchronizacja nie powiodła się. ${error.message}`,'error');}
  finally{state.syncing=false;$('sync-danegov').disabled=false;$('sync-danegov').setAttribute('aria-busy','false');}
});

const initialFilters=new URLSearchParams(location.search);
if(initialFilters.get('miasto'))$('city-filter').value=initialFilters.get('miasto').slice(0,100);
if(['wszystkie','danegov','osm'].includes(initialFilters.get('zrodlo')))$('source-filter').value=initialFilters.get('zrodlo');
if(['true','false'].includes(initialFilters.get('tylko_otwarte_teraz')))$('open-now').checked=initialFilters.get('tylko_otwarte_teraz')==='true';
if(deepID){$('open-now').checked=false;$('city-filter').value='';$('source-filter').value='wszystkie';notice('map-alert','Otwierasz urządzenie z kodu. Sprawdź, czy jest dostępne.');}
initMap();setView(location.hash.slice(1));loadAED({deep:true,resolveCity:!deepID&&!!initialFilters.get('miasto')});
setInterval(()=>{if(state.view==='mapa'&&!document.hidden&&!$('aed-dialog').open)loadAED();},60000);
export {state,loadAED,setView,showDetails,fitMap};
