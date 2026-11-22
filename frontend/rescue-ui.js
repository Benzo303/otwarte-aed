import {state,loadAED,setView,showDetails} from './app.js';
import {aedName,accessState,safeURL,walkingEstimate} from './core.js';
import {openTools,closeTools} from './drawer.js';

const $=id=>document.getElementById(id);
const E=(tag,text,cls)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el;};
function notice(id,text,kind=''){const el=$(id);el.textContent=text;el.className=`notice ${kind}`;el.hidden=!text;}
function announce(text){$('feature-announcement').textContent=text;}
async function api(url,options={},timeout=45000){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeout);
  try{const response=await fetch(url,{...options,signal:controller.signal});const data=await response.json().catch(()=>{throw new Error('Nie udało się odczytać odpowiedzi. Spróbuj ponownie.');});if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Nie udało się zakończyć operacji. Spróbuj ponownie.');return data;}
  catch(error){if(error.name==='TypeError')throw new Error('Brak połączenia z aplikacją. Spróbuj ponownie.');throw error;}
  finally{clearTimeout(timer);}
}
const post=(url,body)=>api(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
function download(value,type,name){const href=URL.createObjectURL(new Blob([value],{type}));const link=E('a');link.href=href;link.download=name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(href),1000);}

// Lektor: bez sieciowego API i bez automatycznego rozpoczęcia odtwarzania.
const canSpeak=!!(window.speechSynthesis&&window.SpeechSynthesisUtterance);
let voiceEnabled=false;
function stopSpeech(){if(canSpeak)window.speechSynthesis.cancel();}
function speak(text){
  if(!canSpeak){announce('Przeglądarka nie obsługuje lektora. Instrukcje są dostępne w tekście.');return;}
  stopSpeech();const utterance=new window.SpeechSynthesisUtterance(String(text).slice(0,16000));
  utterance.lang='pl-PL';utterance.rate=.95;
  const voice=window.speechSynthesis.getVoices().find(v=>v.lang.toLowerCase().startsWith('pl'));
  if(voice)utterance.voice=voice;
  utterance.onerror=()=>announce('Nie można odtworzyć głosu. Sprawdź dostępne głosy polskie w ustawieniach urządzenia.');
  window.speechSynthesis.speak(utterance);
}
if(!canSpeak){$('speech-toggle').disabled=true;$('speech-toggle').title='Lektor nie jest obsługiwany przez tę przeglądarkę.';}
$('speech-toggle').addEventListener('click',()=>{voiceEnabled=!voiceEnabled;$('speech-toggle').setAttribute('aria-pressed',String(voiceEnabled));if(voiceEnabled)speak('Lektor włączony. Przyciski Czytaj na głos odczytują instrukcję lub kartę urządzenia.');else stopSpeech();});
$('stop-speech').addEventListener('click',stopSpeech);
document.querySelectorAll('[data-stop-speech]').forEach(button=>button.addEventListener('click',stopSpeech));

// Ściąga i precyzyjny zegar audio: 110 BPM, uruchamiany tylko gestem użytkownika.
let audioContext=null,audioTimer=null,nextBeat=0;
function stopMetronome(){
  if(audioTimer!==null){clearInterval(audioTimer);audioTimer=null;}
  if(audioContext){audioContext.close().catch(()=>{});audioContext=null;}
  $('metronome-toggle').setAttribute('aria-pressed','false');$('metronome-toggle').textContent='Włącz rytm masażu serca (110/min)';$('metronome-status').textContent='Rytm wyłączony.';
}
async function startMetronome(){
  if(audioContext)return;
  const Audio=window.AudioContext||window.webkitAudioContext;
  if(!Audio){$('metronome-status').textContent='Dźwięk nie jest obsługiwany. Uciskaj w tempie 100–120/min.';return;}
  try{
    const started=new Audio();audioContext=started;await started.resume();if(audioContext!==started)return;nextBeat=audioContext.currentTime+.05;
    const schedule=()=>{if(!audioContext)return;
      // Nie odtwarzaj zaległych uderzeń naraz po przywróceniu karty z tła.
      if(nextBeat<audioContext.currentTime-.1)nextBeat=audioContext.currentTime+.02;
      while(nextBeat<audioContext.currentTime+.12){
      const oscillator=audioContext.createOscillator(),gain=audioContext.createGain();
      oscillator.frequency.value=1000;gain.gain.setValueAtTime(.0001,nextBeat);gain.gain.exponentialRampToValueAtTime(.12,nextBeat+.004);gain.gain.exponentialRampToValueAtTime(.0001,nextBeat+.06);
      oscillator.connect(gain);gain.connect(audioContext.destination);oscillator.start(nextBeat);oscillator.stop(nextBeat+.065);nextBeat+=60/110;
    }};
    schedule();audioTimer=setInterval(schedule,25);$('metronome-toggle').setAttribute('aria-pressed','true');$('metronome-toggle').textContent='Wyłącz rytm 110/min';$('metronome-status').textContent='Rytm włączony: 110 uciśnięć/min. Zatrzymaj podczas analizy AED.';
  }catch{stopMetronome();$('metronome-status').textContent='Nie udało się włączyć dźwięku. Uciskaj w tempie 100–120/min.';}
}
$('metronome-toggle').addEventListener('click',()=>audioTimer===null?startMetronome():stopMetronome());
function openGuide(){openTools('tool-help',{focus:true,pinned:true});$('tool-help').querySelector('summary').focus();}
document.querySelectorAll('[data-open-guide]').forEach(button=>button.addEventListener('click',openGuide));
document.addEventListener('tools:closed',()=>{stopMetronome();stopSpeech();});
$('tool-help').addEventListener('toggle',()=>{if(!$('tool-help').open)stopMetronome();});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&$('aed-dialog').open){event.preventDefault();$('aed-dialog').close();}});
$('read-guide').addEventListener('click',()=>speak($('guide-content').innerText||$('guide-content').textContent));
window.addEventListener('pagehide',()=>{stopSpeech();stopMetronome();});

// Asystent dla dorosłego. Wezwanie 112 od razu po stwierdzeniu nieprzytomności.
const answers={
  conscious:{tone:'success',title:'DEFIBRYLATOR NIE JEST TERAZ POTRZEBNY',text:'Zostań przy poszkodowanym i zapewnij mu wygodną pozycję. Przy bólu w klatce, duszności lub pogorszeniu stanu dzwoń pod 112.'},
  breathing:{tone:'warning',title:'AED NIE JEST TERAZ POTRZEBNE. ZADZWOŃ POD 112.',text:'Jeśli nie podejrzewasz urazu, ułóż osobę na boku w pozycji bezpiecznej. Stale sprawdzaj oddech i słuchaj dyspozytora.'},
  'not-breathing':{tone:'critical',title:'RÓB MASAŻ SERCA, ZADZWOŃ POD 112 I UŻYJ AED, GDY DOTRZE!',text:'Poproś inną osobę o przyniesienie urządzenia. Jeśli jesteś sam, nie przerywaj masażu serca na szukanie AED.'}
};
function assessment(choice){
  $('assessment-reset').hidden=false;
  if(choice==='unconscious'){
    $('assessment-step1').hidden=true;$('assessment-step2').hidden=false;$('assessment-result').hidden=true;$('assessment-progress').textContent='Pytanie 2 z 2';
    if(voiceEnabled)speak('Nie reaguje. Dzwoń pod 112 już teraz, włącz głośnomówiący i oceniaj oddech. Pojedyncze westchnienia lub charczenie nie są prawidłowym oddechem.');
    $('assessment-step2').querySelector('button').focus();return;
  }
  const result=answers[choice];if(!result)return;
  $('assessment-step1').hidden=true;$('assessment-step2').hidden=true;$('assessment-progress').textContent='Wskazówki do działania';
  const panel=$('assessment-result');panel.className=`assessment-result ${result.tone}`;panel.setAttribute('role',result.tone==='critical'?'alert':'status');panel.replaceChildren(E('h3',result.title),E('p',result.text));
  const actions=E('div',undefined,'form-actions');const call=E('a','Zadzwoń 112','button button-primary');call.href='tel:112';actions.append(call);
  if(choice==='not-breathing'){
    const gps=E('button','Pokaż najbliższy AED','button button-blue');gps.addEventListener('click',gpsRescue);actions.append(gps);
    const guide=E('button','Otwórz ściągę masażu serca','button button-light');guide.addEventListener('click',()=>openGuide(guide));actions.append(guide);
  }
  const read=E('button','Czytaj na głos','button button-light');read.addEventListener('click',()=>speak(result.title+'. '+result.text));actions.append(read);panel.append(actions);panel.hidden=false;panel.focus();if(voiceEnabled)speak(result.title+'. '+result.text);
}
document.querySelectorAll('[data-assessment]').forEach(button=>button.addEventListener('click',()=>assessment(button.dataset.assessment)));
$('assessment-reset').addEventListener('click',()=>{stopSpeech();$('assessment-step1').hidden=false;$('assessment-step2').hidden=true;$('assessment-result').hidden=true;$('assessment-reset').hidden=true;$('assessment-progress').textContent='Pytanie 1 z 2';$('assessment-step1').querySelector('button').focus();});
document.querySelectorAll('[data-read="assessment"]').forEach(button=>button.addEventListener('click',()=>speak($('assessment-live').innerText||$('assessment-live').textContent)));

// TOP 3 otwartych AED, GPS i wskazanie miejsca zdarzenia na mapie.
let rescueOrigin=null,rescueData=null,rescueRoute=null,rescueOriginMarker=null,picking=false;
function routeTo(row){
  if(!state.map||!window.L||!rescueOrigin)return;
  if(rescueRoute)state.map.removeLayer(rescueRoute);
  if(rescueOriginMarker)state.map.removeLayer(rescueOriginMarker);
  rescueOriginMarker=L.circleMarker([rescueOrigin.lat,rescueOrigin.lon],{radius:8,color:'#003366',weight:3,fillColor:'#fff',fillOpacity:1}).addTo(state.map);
  rescueRoute=L.polyline([[rescueOrigin.lat,rescueOrigin.lon],[row.lat,row.lon]],{color:'#0052a5',weight:4,dashArray:'8 8'}).addTo(state.map);
  state.map.fitBounds(rescueRoute.getBounds(),{padding:[40,40],maxZoom:17,animate:false});
}
function rescueText(row,estimate){return `${aedName(row)}. Odległość w linii prostej ${estimate.straight_distance_m} metrów. Szacowany marsz ${Math.ceil(estimate.walking_time_seconds/60)} minut w jedną stronę, ${Math.ceil(estimate.round_trip_seconds/60)} minut w obie strony. Lokalizacja: ${row.opis_lokalizacji_wewnatrz||'Brak opisu dokładnego miejsca.'}`;}
function renderRescue(data){
  const panel=$('rescue-results');panel.replaceChildren();rescueData=data;$('rescue-panel').hidden=false;
  if(!data.top3.length){notice('rescue-status','Nie znaleźliśmy otwartego urządzenia w pobliżu. Zadzwoń pod 112 i kontynuuj masaż serca.','warning');return;}
  notice('rescue-status','');
  for(const row of data.top3.slice(0,3)){
    const estimate=walkingEstimate(data.origin.lat,data.origin.lon,row.lat,row.lon);
    const card=E('article',undefined,`rescue-card${row.rank===1?' best':''}`);
    card.append(E('span',row.rank===1?(state.origin?.kind==='gps'?'Najbliżej Ciebie':'Najbliżej wskazanego miejsca'):'Inne otwarte miejsce','rescue-rank'),E('h3',aedName(row)),E('span','✓ Otwarty teraz','badge open'));
    card.append(E('p',estimate.walking_time_seconds<60?'Mniej niż minuta pieszo':`Około ${Math.ceil(estimate.walking_time_seconds/60)} min pieszo`,'rescue-time'));
    card.append(E('p',row.opis_lokalizacji_wewnatrz||'Sprawdź dokładne miejsce na karcie urządzenia.','card-description'));
    if(row.ulica_numer)card.append(E('p',row.ulica_numer));
    const actions=E('div',undefined,'form-actions');
    const nav=E('a','Prowadź do tego AED','button button-blue');
    const href=safeURL(row.navigation_url);if(href){const url=new URL(href);if(state.origin?.kind==='search')url.searchParams.delete('origin');nav.href=url.href;}nav.target='_blank';nav.rel='noopener noreferrer';nav.setAttribute('aria-label',`Prowadź do ${aedName(row)} — otwiera nawigację w nowej karcie`);
    const details=E('button','Jak znaleźć urządzenie','button button-light');details.addEventListener('click',()=>{routeTo(row);showDetails(row,details);});
    const read=E('button','Czytaj na głos','button button-light');read.addEventListener('click',()=>speak(rescueText(row,estimate)));
    actions.append(nav,details,read);card.append(actions);panel.append(card);
  }
  $('rescue-estimate').textContent='Czas dojścia jest szacunkowy. Po urządzenie wyślij inną osobę. Jeśli jesteś sam, nie przerywaj masażu serca.';
  routeTo(data.top3[0]);if(voiceEnabled)speak(rescueText(data.top3[0],walkingEstimate(data.origin.lat,data.origin.lon,data.top3[0].lat,data.top3[0].lon)));
}
let rescueSerial=0,locationVersion=0;
async function refreshRescue(expectedSerial=null){
  if(!rescueOrigin)return;const serial=expectedSerial??++rescueSerial;
  try{const data=await post('/api/rescue/nearest',{...rescueOrigin,radius_km:15,zrodlo:$('source-filter').value});if(serial===rescueSerial)renderRescue(data);}
  catch(error){if(serial===rescueSerial)notice('rescue-status',`Nie udało się znaleźć urządzeń. ${error.message}`,'error');}
}
async function locateRescue(lat,lon,{label='Wskazane miejsce',kind='manual',origin_note='Czas liczymy od wskazanego miejsca.'}={}){
  const serial=++rescueSerial;
  closeTools();rescueOrigin={lat,lon};state.origin={lat,lon,label,kind};state.committedCity='';$('city-filter').value='';$('aed-search').value='';
  $('rescue-panel').hidden=false;$('origin-note').textContent=`${label}. ${origin_note}`;$('rescue-results').replaceChildren();
  $('rescue-panel').setAttribute('aria-busy','true');notice('rescue-status','Szukamy otwartych urządzeń w pobliżu…');
  await loadAED();if(serial!==rescueSerial)return;await refreshRescue(serial);if(serial===rescueSerial)$('rescue-panel').setAttribute('aria-busy','false');
}
function gpsRescue(){
  ++rescueSerial;rescueOrigin=null;$('rescue-results').replaceChildren();
  closeTools();const version=++locationVersion;$('rescue-panel').hidden=false;
  if(!navigator.geolocation||!window.isSecureContext){notice('rescue-status','Nie można odczytać Twojej lokalizacji. Wpisz miejscowość lub ulicę. Inne sposoby znajdziesz w panelu Pomoc.','warning');return;}
  notice('rescue-status','Zezwól na dostęp do lokalizacji telefonu lub komputera…');
  navigator.geolocation.getCurrentPosition(position=>{if(version===locationVersion)locateRescue(position.coords.latitude,position.coords.longitude,{label:'Twoja lokalizacja',kind:'gps',origin_note:'Czas dojścia liczymy od Twojej pozycji.'});},()=>{if(version===locationVersion)notice('rescue-status','Nie udało się odczytać lokalizacji. Wpisz miejscowość lub ulicę.','warning');},{enableHighAccuracy:true,timeout:12000,maximumAge:30000});
}
document.querySelectorAll('[data-gps]').forEach(button=>button.addEventListener('click',gpsRescue));
$('map-filters').addEventListener('submit',async event=>{
  event.preventDefault();const query=$('location-query').value.trim(),version=++locationVersion;$('rescue-panel').hidden=false;
  ++rescueSerial;rescueOrigin=null;$('rescue-results').replaceChildren();
  if(query.length<2){notice('rescue-status','Wpisz miejscowość lub ulicę.','warning');return;}
  $('search-location').disabled=true;notice('rescue-status','Szukamy wskazanego miejsca…');
  try{const location=await api(`/api/location/search?${new URLSearchParams({q:query})}`);if(version===locationVersion)await locateRescue(location.lat,location.lon,{...location,label:location.query||query,kind:'search'});}
  catch(error){if(version===locationVersion)notice('rescue-status',error.message,'error');}finally{$('search-location').disabled=false;}
});
$('coordinates-form').addEventListener('submit',event=>{event.preventDefault();++locationVersion;const lat=Number($('manual-lat').value),lon=Number($('manual-lon').value);if(!Number.isFinite(lat)||!Number.isFinite(lon))return;locateRescue(lat,lon);});
$('rescue-map-pick').addEventListener('click',()=>{if(!state.map){announce('Mapa nie jest dostępna. Wpisz miejscowość lub ulicę.');return;}++locationVersion;closeTools();picking=true;$('rescue-panel').hidden=false;notice('rescue-status','Kliknij miejsce na mapie albo przesuń mapę strzałkami i naciśnij Enter.');$('map').scrollIntoView({block:'center'});$('map').focus();});
if(state.map)state.map.on('click',event=>{if(picking){picking=false;locateRescue(event.latlng.lat,event.latlng.lng);}});
$('map').addEventListener('keydown',event=>{if(picking&&event.key==='Enter'&&state.map){event.preventDefault();picking=false;const center=state.map.getCenter();locateRescue(center.lat,center.lng);}});
document.addEventListener('aed:filters',()=>refreshRescue());
document.addEventListener('aed:origin-reset',()=>{++rescueSerial;rescueOrigin=null;$('rescue-panel').hidden=true;if(state.map){if(rescueRoute)state.map.removeLayer(rescueRoute);if(rescueOriginMarker)state.map.removeLayer(rescueOriginMarker);}rescueRoute=null;rescueOriginMarker=null;});
setInterval(()=>{if(rescueOrigin&&!document.hidden&&!$('aed-dialog').open)refreshRescue();},60000);

// Zgłoszenia są zapisywane na serwerze; pozytywne zgłoszenie nie usuwa ostrzeżenia.
let selectedID=null;
document.addEventListener('aed:detail',event=>{selectedID=event.detail.id_aed;notice('field-report-status','');});
document.querySelectorAll('[data-report]').forEach(button=>button.addEventListener('click',async()=>{
  if(!selectedID)return;const buttons=[...document.querySelectorAll('[data-report]')];buttons.forEach(b=>b.disabled=true);notice('field-report-status','Zapisuję zgłoszenie terenowe…');
  try{const result=await post(`/api/aed/${encodeURIComponent(selectedID)}/report`,{kind:button.dataset.report});const refreshed=await api(`/api/aed/${encodeURIComponent(selectedID)}`);showDetails(refreshed,button);notice('field-report-status','Dziękujemy. Zgłoszenie zostało zapisane.','success');if(rescueOrigin)await locateRescue(rescueOrigin.lat,rescueOrigin.lon,state.origin);else loadAED();}
  catch(error){notice('field-report-status',error.message,'error');}finally{buttons.forEach(b=>b.disabled=false);}
}));
document.querySelectorAll('[data-read="device"]').forEach(button=>button.addEventListener('click',()=>speak($('aed-detail').innerText||$('aed-detail').textContent)));
$('aed-dialog').addEventListener('close',stopSpeech);

// Czytelny ranking jakości źródeł.
async function loadAudit(){
  $('audit-refresh').disabled=true;notice('audit-status','Sprawdzam jakość danych instytucji…');
  try{
    const data=await api('/api/danegov/audit');$('audit-method').textContent=data.methodology||data.warning||'';
    const body=$('audit-body');body.replaceChildren();
    for(const [index,row] of (data.ranking||[]).entries()){
      const tr=E('tr');tr.append(E('td',`${index+1}. ${row.institution}`),E('td',String(row.valid_points)));
      const score=E('td');score.append(E('span',row.grade,'grade'),E('strong',`${row.score} / 100`));tr.append(score);
      const cell=E('td'),details=E('details');details.append(E('summary',row.errors.length?`${row.errors.length} uwag do poprawy`:'Brak wykrytych braków'));
      const list=E('ul');for(const error of row.errors)list.append(E('li',error));details.append(list);cell.append(details);tr.append(cell);body.append(tr);
    }
    notice('audit-status',data.warning||'Ocena dotyczy danych źródłowych. Informacje dodane z OSM nie podnoszą wyniku instytucji.',data.warning?'warning':'');
  }catch(error){notice('audit-status',`Audyt jest niedostępny. ${error.message}`,'error');}finally{$('audit-refresh').disabled=false;}
}
$('audit-refresh').addEventListener('click',loadAudit);
document.addEventListener('tools:section',event=>{if(event.detail==='tool-data')loadAudit();});
$('sync-danegov').addEventListener('click',()=>{const check=setInterval(()=>{if(!state.syncing){clearInterval(check);loadAudit();}},1000);setTimeout(()=>clearInterval(check),300000);});
if(state.view==='integracja')loadAudit();

// Importer chaosu oraz odrębna lokalna baza podglądu.
let importReport=null;
function renderImport(data){
  importReport=data;$('chaos-results').hidden=false;
  $('chaos-summary').replaceChildren(E('p',`Odczytano ${data.rows_total} wierszy. Odzyskano ${data.rows_rescued}, po deduplikacji ${data.output_records}. Wszystkie wymagane pola wzorca spełnia ${data.schema_valid_records}.`,'notice success'),E('p',data.note,'field-help'));
  const issues=$('chaos-issues');issues.replaceChildren();const details=E('details');details.append(E('summary',`Zmiany i błędy (${data.changes.length+data.errors.length})`));const list=E('ul');
  for(const item of [...data.errors,...data.changes].slice(0,100))list.append(E('li',`Wiersz ${item.row}: ${item.message}`));
  for(const row of data.quality.slice(0,10))list.append(E('li',`${row.id_aed}: ${row.errors.map(e=>e.field).join(', ')} — pola do uzupełnienia.`));details.append(list);issues.append(details);
  for(const id of ['chaos-json','chaos-csv','chaos-preview'])$(id).disabled=!data.output_records;
}
$('chaos-form').addEventListener('submit',async event=>{
  event.preventDefault();const file=$('chaos-file').files[0],url=$('bip-url').value.trim(),geocode=$('chaos-geocode').checked;
  if(Boolean(file)===Boolean(url)){notice('chaos-message','Wybierz jeden plik albo podaj jeden adres strony.','error');return;}
  if(file&&file.size>5*1024*1024){notice('chaos-message','Plik przekracza 5 MiB.','error');return;}
  $('chaos-submit').disabled=true;$('chaos-form').setAttribute('aria-busy','true');$('chaos-results').hidden=true;notice('chaos-message','Odczytuję dane i sprawdzam współrzędne. Import z geokodowaniem może potrwać dłużej.');
  try{let data;if(file){const form=new FormData();form.append('file',file);form.append('geocode',String(geocode));data=await api('/api/chaos-import',{method:'POST',body:form},120000);}else data=await api('/api/import/bip-url',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url,geocode})},120000);renderImport(data);notice('chaos-message','Import zakończony. Sprawdź raport przed pobraniem.','success');}
  catch(error){notice('chaos-message',error.name==='AbortError'?'Import przekroczył czas. Spróbuj mniejszego pliku.':error.message,'error');}
  finally{$('chaos-submit').disabled=false;$('chaos-form').setAttribute('aria-busy','false');}
});
$('chaos-json').addEventListener('click',()=>{if(importReport)download(JSON.stringify(importReport.standard_json,null,2),'application/json;charset=utf-8','aed_21_pol.json');});
$('chaos-csv').addEventListener('click',()=>{if(importReport)download(importReport.normalized_csv,'text/csv;charset=utf-8','aed_21_pol.csv');});
$('chaos-preview').addEventListener('click',async()=>{
  if(!importReport)return;$('chaos-preview').disabled=true;
  try{await post(`/api/import/${importReport.import_id}/preview`,{});const data=await api('/api/import/preview');const el=$('import-preview');el.replaceChildren(E('h3',`Lokalna baza podglądu: ${data.count} punktów`),E('p','Te rekordy nie trafiają do rekomendacji ratunkowych ani publicznych eksportów.','notice warning'));const list=E('ul');for(const row of data.items.slice(0,30))list.append(E('li',`${aedName(row)} · ${row.miejscowosc||'brak miasta'} · GPS ${row.lat}, ${row.lon}`));el.append(list);notice('chaos-message','Zapisano do lokalnego podglądu.','success');}
  catch(error){notice('chaos-message',error.message,'error');}finally{$('chaos-preview').disabled=false;}
});

export {assessment,speak,stopSpeech,startMetronome,stopMetronome,openGuide,gpsRescue,renderRescue,loadAudit};
