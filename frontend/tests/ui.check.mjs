// Test interakcji DOM z mockami API/audio/GPS; bez renderowania przeglądarkowego.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {parseHTML} from 'linkedom';

const {window}=parseHTML(fs.readFileSync(new URL('../index.html',import.meta.url),'utf8'));
const {document}=window;
const ids=[...document.querySelectorAll('[id]')].map(node=>node.id);assert.equal(ids.length,new Set(ids).size,'unique HTML identifiers');
let audioBeats=0,printed=0,speaking=0,nextTimer=1,lastAudio=null;
const deepLink=process.argv.includes('--deep-link');
const clusters=process.argv.includes('--clusters');
const desktopMode=process.argv.includes('--desktop');
let activeElement=document.body,virtualNow=0;
const timers=new Map();
const later=(callback,ms=0)=>{const id=nextTimer++;timers.set(id,{callback,at:virtualNow+ms});return id;};
const advance=ms=>{const end=virtualNow+ms;for(let i=0;i<1000;i++){const entry=[...timers.entries()].filter(([,t])=>t.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!entry)break;const [id,t]=entry;timers.delete(id);virtualNow=t.at;t.callback();}virtualNow=end;};
let clusterGroup=null;
let delayedNearest=null;
const intervals=new Map(),calls=[];
const row={id_aed:'OPEN',nazwa_obiektu:'AED Test',lat:54.19,lon:16.18,miejscowosc:'Koszalin',dostepnosc_typ:'24_7',godziny_otwarcia_osm:'24/7',wymagany_klucz_lub_kod:'NIE',status_techniczny:'niezweryfikowany',confidence_score:80,otwarte_teraz:true,opis_lokalizacji_wewnatrz:'Parter, hol przy wejściu',sources:[{name:'OpenStreetMap',url:'https://www.openstreetmap.org/node/1'}]};
const imported={rows_total:1,rows_rescued:1,output_records:1,schema_valid_records:0,changes:[],errors:[],quality:[],normalized_json:[{...row,id_aed:'IMPORT'}],standard_json:[{id_aed:'IMPORT'}],normalized_csv:'id_aed\r\nIMPORT\r\n',import_id:'batch',note:'Podgląd'};
const stats={area:'polska',osm_records:1,danegov_records:0,integrated_records:1,duplicates_merged:0,cross_source_groups:0,datasets:[],danegov:{from_cache:true,retrieved_at:'2026-11-21T12:00:00Z'}};
const res=value=>({ok:true,status:200,json:async()=>value,text:async()=>typeof value==='string'?value:JSON.stringify(value),headers:new Headers()});
async function fetchMock(url,options={}){
  calls.push([String(url),options.method||'GET']);
  if(String(url).includes('/passport.svg'))return res('<svg xmlns="http://www.w3.org/2000/svg"><title>QR</title></svg>');
  if(String(url).startsWith('/export/'))return res('[]');
  if(String(url).endsWith('/report')){row.field_access_alert='damaged';return res({saved:true,note:'Zgłoszenie zapisane.',aed:row});}
  if(url==='/api/aed/OPEN'||url==='/api/aed/LEGACY')return res({...row,merged_ids:['LEGACY']});
  if(String(url).startsWith('/api/aed?'))return res({items:[row],count:1,evaluated_at:'2026-11-21T12:00:00Z',scope:{national_records:1,danegov_points:0,matched_before_availability:1},source:{}});
  if(url==='/api/sources/stats'||url==='/api/danegov/refresh')return res(stats);
  if(url==='/api/danegov/audit')return res({methodology:'Audyt',ranking:[{institution:'Urząd',score:70,grade:'C',valid_points:21,errors:['Uzupełnij godziny.']}]});
  if(String(url).startsWith('/api/location/search?'))return res({lat:54.19,lon:16.18,label:'Koszalin, Polska',origin_note:'Czas liczymy od wskazanego miejsca.'});
  if(url==='/api/rescue/nearest'){
    const delayed=delayedNearest;delayedNearest=null;if(delayed)await delayed.promise;
    return res({origin:{lat:54.19,lon:16.18},count:1,radius_km:15,top3:[{...row,...(delayed?{nazwa_obiektu:'STALE RESULT'}:{}),rank:1,navigation_url:'https://www.google.com/maps/dir/'}],estimation_note:'Szacunek',rescue_note:'Dzwoń 112.'});
  }
  if(url==='/api/validate-upload')return res({valid:true,rows_total:1,rows_valid:1,errors:[],normalized_json:[row],normalized_csv:'csv'});
  if(url==='/api/chaos-import'||url==='/api/import/bip-url')return res(imported);
  if(url==='/api/import/preview')return res({count:1,items:imported.normalized_json});
  if(String(url).endsWith('/preview'))return res({active:true});
  throw new Error('Unexpected API '+url);
}
Object.defineProperty(window,'location',{value:new URL('http://localhost:8000/'+(deepLink?'?aed=LEGACY':'')),configurable:true});
window.isSecureContext=false;
window.localStorage={getItem:()=>null,setItem:()=>{}};
window.history={replaceState:()=>{}};
window.HTMLElement.prototype.scrollIntoView=function(){};
Object.defineProperty(document,'activeElement',{get:()=>activeElement});
window.HTMLElement.prototype.focus=function(){const old=activeElement;activeElement=this;old?.dispatchEvent(new window.Event('focusout',{bubbles:true}));this.dispatchEvent(new window.Event('focusin',{bubbles:true}));};
Object.defineProperty(window.HTMLElement.prototype,'tabIndex',{get(){return this.hasAttribute('tabindex')?Number(this.getAttribute('tabindex')):this.matches('button,input,select,textarea,summary,a[href]')?0:-1;},set(value){this.setAttribute('tabindex',value);}});
for(const details of document.querySelectorAll('details'))Object.defineProperty(details,'open',{get(){return this.hasAttribute('open');},set(value){if(value===this.hasAttribute('open'))return;this.toggleAttribute('open',value);this.dispatchEvent(new window.Event('toggle'));}});
for(const input of document.querySelectorAll('input[type=checkbox]'))Object.defineProperty(input,'checked',{get(){return this.hasAttribute('checked');},set(value){this.toggleAttribute('checked',value);}});
window.matchMedia=query=>({matches:query.includes('prefers-reduced-motion')?clusters:desktopMode,addEventListener(){}});
for(const select of document.querySelectorAll('select')){
  Object.defineProperty(select,'value',{get(){return this.querySelector('option[selected]')?.getAttribute('value')||this.querySelector('option')?.getAttribute('value')||'';},set(v){this.querySelectorAll('option').forEach(o=>o.toggleAttribute('selected',o.getAttribute('value')===v));}});
}
for(const dialog of document.querySelectorAll('dialog')){
  Object.defineProperty(dialog,'open',{get(){return this.hasAttribute('open');}});
  dialog.showModal=function(){this.setAttribute('open','');};
  dialog.close=function(){this.removeAttribute('open');this.dispatchEvent(new window.Event('close'));};
}
for(const input of document.querySelectorAll('input[type=file]'))Object.defineProperty(input,'files',{value:[],writable:true});
window.print=()=>printed++;
window.speechSynthesis={cancel:()=>{},getVoices:()=>[{lang:'pl-PL'}],speak:()=>speaking++};
window.SpeechSynthesisUtterance=class{constructor(text){this.text=text;}};
window.AudioContext=class{
  constructor(){this.currentTime=0;this.destination={};lastAudio=this;}
  async resume(){}
  async close(){}
  createOscillator(){return {frequency:{value:0},connect(){},start(){audioBeats++;},stop(){}};}
  createGain(){return {gain:{setValueAtTime(){},exponentialRampToValueAtTime(){}},connect(){}};}
};
if(clusters){
  const pane=document.createElement('div');document.getElementById('map').append(pane);
  const map={setView(){return this;},getPane:()=>pane,on(){return this;},fitBounds(){},invalidateSize(){},getZoom:()=>6};
  window.L={
    map:()=>map,tileLayer:()=>({addTo(){return this;},on(){return this;}}),
    divIcon:options=>options,latLngBounds:points=>points,
    marker:(coordinates,options)=>({coordinates,options,handlers:{},on(event,callback){this.handlers[event]=callback;return this;}}),
    markerClusterGroup(options){
      clusterGroup={options,markers:[],batches:[],hold:false,addTo(){return this;},clearLayers(){this.markers=[];},
        addLayers(markers){assert.equal(this.pending,undefined,'one batch at a time');this.batches.push(markers);this.pending=markers;if(!this.hold)this.finish();},
        finish(){this.markers=this.pending;delete this.pending;options.chunkProgress(this.markers.length,this.markers.length);}};
      return clusterGroup;
    }
  };
}
const context=vm.createContext({window,document,navigator:{},location:window.location,history:window.history,localStorage:window.localStorage,console,URL,URLSearchParams,Blob,File,FormData,Headers,AbortController,AbortSignal,Intl,Date,CustomEvent:window.CustomEvent,fetch:fetchMock,requestAnimationFrame:f=>f(),setInterval:(f,ms)=>{const id=nextTimer++;intervals.set(id,{f,ms});return id;},clearInterval:id=>intervals.delete(id),setTimeout:later,clearTimeout:id=>timers.delete(id)});
if(clusters)context.L=window.L;
const coreNames=['aedName','accessState','safeURL','confidence','filterRows','labelURL','labelSVG','sourceLabel','walkingEstimate'];
context.__core=vm.runInContext(`(()=>{${fs.readFileSync(new URL('../core.js',import.meta.url),'utf8').replaceAll('export function','function')}\nreturn {${coreNames.join(',')}};})()`,context);
const drawer=fs.readFileSync(new URL('../drawer.js',import.meta.url),'utf8').replace(/export \{[^}]+\};/,'');
context.__drawer=vm.runInContext(`(()=>{${drawer}\nreturn {openTools,closeTools,drawerState,focusable};})()`,context);
let app=fs.readFileSync(new URL('../app.js',import.meta.url),'utf8').replace(/^import .*core.js';$/m,`const {${coreNames.join(',')}}=__core;`).replace(/^import .*drawer.js';$/m,'const {openTools,closeTools}=__drawer;').replace(/export \{[^}]+\};/,'');
context.__app=vm.runInContext(`(()=>{${app}\nreturn {state,loadAED,setView,showDetails,renderMarkers};})()`,context);
let features=fs.readFileSync(new URL('../rescue-ui.js',import.meta.url),'utf8').replace(/^import \{[^}]+\} from '\.\/app.js';/m,'const {state,loadAED,setView,showDetails}=__app;').replace(/^import \{[^}]+\} from '\.\/core.js';/m,`const {${coreNames.join(',')}}=__core;`).replace(/^import .*drawer.js';$/m,'const {openTools,closeTools}=__drawer;').replace(/export \{[^}]+\};/,'');
context.__features=vm.runInContext(`(()=>{${features}\nreturn {assessment,renderRescue,openGuide};})()`,context);
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const click=selector=>{const el=document.querySelector(selector);assert.ok(el,'missing '+selector);el.focus();el.dispatchEvent(new window.Event('click',{bubbles:true}));if(el.tagName==='SUMMARY')el.parentElement.open=!el.parentElement.open;};
const submit=id=>document.getElementById(id).dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));
await tick();await tick();
if(deepLink){assert.equal(document.getElementById('aed-dialog').open,true,'QR merged alias opens canonical device');click('#close-details');}
assert.equal(document.querySelectorAll('.aed-card').length,1);
if(!clusters)assert.ok(document.getElementById('map').textContent.includes('Mapa jest niedostępna'),'Leaflet fallback');
assert.equal(document.querySelectorAll('#main input:not([type=hidden])').length,1,'one public search field');
assert.ok(!/\bAPI\b|GeoJSON|Confidence Score|harvester/i.test(document.getElementById('main').textContent),'no technical jargon in main');
const pointer=(selector,type,pointerType='mouse',relatedTarget=null)=>{const event=new window.Event(type);event.pointerType=pointerType;event.relatedTarget=relatedTarget;document.querySelector(selector).dispatchEvent(event);};
document.getElementById('location-query').focus();
pointer('#tools-toggle','pointerenter');advance(119);assert.equal(context.__drawer.drawerState.open,false);
if(desktopMode){
  advance(1);assert.equal(context.__drawer.drawerState.open,true);assert.equal(document.activeElement.id,'location-query','hover does not steal focus');assert.equal(document.getElementById('tools-backdrop').hidden,true);
  pointer('#tools-toggle','pointerleave','mouse',document.getElementById('tools-drawer'));advance(400);assert.equal(context.__drawer.drawerState.open,true,'crossing into panel stays open');
  pointer('#tools-drawer','pointerleave');advance(349);assert.equal(context.__drawer.drawerState.open,true);advance(1);assert.equal(context.__drawer.drawerState.open,false);
  pointer('#tools-toggle','pointerenter');advance(120);click('#tools-pin');document.getElementById('location-query').focus();pointer('#tools-drawer','pointerleave');advance(500);assert.equal(context.__drawer.drawerState.open,true,'pin survives pointer leave');click('#tools-close');
}else{
  advance(500);assert.equal(context.__drawer.drawerState.open,false,'touch layout ignores hover');
  click('#tools-toggle');assert.equal(context.__drawer.drawerState.open,true);assert.equal(document.getElementById('tools-backdrop').hidden,false);assert.equal(document.getElementById('main').inert,true);
  const list=context.__drawer.focusable();list.at(-1).focus();const tab=new window.Event('keydown',{bubbles:true,cancelable:true});tab.key='Tab';document.dispatchEvent(tab);assert.equal(document.activeElement,list[0],'modal focus wraps');
  click('#tools-toggle');assert.equal(context.__drawer.drawerState.open,false);assert.equal(document.getElementById('main').inert,undefined);
  click('#tools-toggle');click('#tools-backdrop');assert.equal(context.__drawer.drawerState.open,false);
}
pointer('#tools-toggle','pointerenter','touch');advance(500);assert.equal(context.__drawer.drawerState.open,false);
if(clusters){
  assert.equal(context.__app.state.layers,clusterGroup);
  for(const [option,value] of Object.entries({chunkedLoading:true,maxClusterRadius:55,disableClusteringAtZoom:15,spiderfyOnMaxZoom:true,showCoverageOnHover:false,animate:false}))assert.equal(clusterGroup.options[option],value,option);
  assert.equal(context.__app.state.map.getPane('markerPane').getAttribute('aria-hidden'),'true');
  for(const [count,size,diameter] of [[2,'small',44],[9,'small',44],[10,'medium',56],[99,'medium',56],[100,'large',68],[17381,'large',68]]){
    const cluster={options:{},getChildCount:()=>count};const icon=clusterGroup.options.iconCreateFunction(cluster);
    assert.equal(icon.className,`aed-cluster aed-cluster--${size}`);assert.equal(icon.iconSize[0],diameter);assert.equal(icon.html,`<span>${count}</span>`);assert.equal(cluster.options.keyboard,false);
  }
  clusterGroup.markers[0].handlers.click();assert.equal(document.getElementById('aed-dialog').open,true);click('#close-details');
  clusterGroup.hold=true;
  context.__app.state.filtered=Array.from({length:1200},(_,i)=>({...row,id_aed:`OLD-${i}`}));context.__app.renderMarkers();
  assert.equal(clusterGroup.pending.length,1200);
  context.__app.state.filtered=[{...row,id_aed:'INTERMEDIATE'}];context.__app.renderMarkers();
  context.__app.state.filtered=[{...row,nazwa_obiektu:'Latest filter',id_aed:'LATEST'}];context.__app.renderMarkers();
  clusterGroup.finish();await tick();assert.equal(clusterGroup.pending.length,1);assert.equal(clusterGroup.pending[0].options.title,'Latest filter');
  clusterGroup.finish();await tick();assert.equal(document.getElementById('map').getAttribute('aria-busy'),'false');
  clusterGroup.hold=false;await context.__app.loadAED();await tick();
  const search=document.getElementById('aed-search');search.value='no match';search.dispatchEvent(new window.Event('input'));await tick();assert.equal(clusterGroup.markers.length,0);
  search.value='';search.dispatchEvent(new window.Event('input'));await tick();assert.equal(clusterGroup.markers.length,1);
}
context.__drawer.openTools('tool-owner');assert.equal(document.getElementById('tool-owner').open,true);
context.__drawer.openTools('tool-data');await tick();await tick();assert.equal(document.querySelectorAll('#audit-body tr').length,1);assert.ok(document.getElementById('export-preview').textContent.includes('[]'));assert.ok(document.querySelectorAll('details[data-tool-section][open]').length<=2);
context.__drawer.closeTools();click('[data-assessment=conscious]');assert.ok(document.getElementById('assessment-result').textContent.includes('NIE JEST TERAZ POTRZEBNY'));
click('#assessment-reset');click('[data-assessment=unconscious]');assert.equal(document.getElementById('assessment-step2').hidden,false);
click('[data-assessment=breathing]');assert.ok(document.getElementById('assessment-result').textContent.includes('podejrzewasz urazu'));
click('#assessment-reset');click('[data-assessment=unconscious]');click('[data-assessment=not-breathing]');assert.equal(document.getElementById('assessment-result').getAttribute('role'),'alert');
context.__features.openGuide();assert.equal(context.__drawer.drawerState.open,true);assert.equal(document.getElementById('tool-help').open,true);
click('#metronome-toggle');await tick();assert.ok(audioBeats>0);assert.equal(document.getElementById('metronome-toggle').getAttribute('aria-pressed'),'true');
const beforeResume=audioBeats;lastAudio.currentTime=20;for(const timer of intervals.values())if(timer.ms===25)timer.f();assert.equal(audioBeats-beforeResume,1,'no burst of missed beats on resume');
click('#read-guide');assert.ok(speaking>0);
const esc=new window.Event('keydown',{bubbles:true,cancelable:true});esc.key='Escape';document.dispatchEvent(esc);assert.equal(context.__drawer.drawerState.open,false);assert.equal(document.getElementById('metronome-toggle').getAttribute('aria-pressed'),'false');
click('[data-gps]');assert.ok(document.getElementById('rescue-status').textContent.includes('Wpisz miejscowość'));
context.__features.renderRescue(await (await fetchMock('/api/rescue/nearest')).json());assert.equal(document.querySelectorAll('.rescue-card').length,1);
let routeLines=0,positionRequests=0;
context.__app.state.map={removeLayer(){},fitBounds(){},setView(){},getZoom:()=>15,getCenter:()=>({lat:54.19,lng:16.18}),invalidateSize(){}};
context.L=window.L={...(window.L||{}),circleMarker:()=>({addTo(){return this;}}),polyline:()=>({addTo(){routeLines++;return this;},getBounds:()=>[]})};
window.isSecureContext=true;context.navigator.geolocation={getCurrentPosition(success){positionRequests++;success({coords:{latitude:54.19,longitude:16.18}});}};
click('[data-gps]');await tick();await tick();assert.equal(positionRequests,1);assert.ok(routeLines>0,'GPS draws estimated line');
click('#rescue-map-pick');const enter=new window.Event('keydown',{bubbles:true,cancelable:true});enter.key='Enter';document.getElementById('map').dispatchEvent(enter);await tick();await tick();assert.ok(routeLines>1,'keyboard selects map centre');
click('.details-button');assert.equal(document.getElementById('aed-dialog').open,true);assert.ok(!document.getElementById('aed-detail').textContent.includes('Confidence'));click('[data-report=damaged]');await tick();await tick();assert.ok(document.getElementById('field-report-status').textContent.includes('zapisane'));
click('#close-details');context.__drawer.openTools('tool-help');click('#qr-shortcut');
assert.equal(document.getElementById('tool-owner').open,true);assert.equal(document.activeElement.id,'label-id');assert.equal(document.getElementById('label-id').value,'OPEN');
assert.equal(document.querySelector('.owner-grid').firstElementChild.classList.contains('label-generator'),true,'QR generator is first');
document.getElementById('label-id').value='OPEN';document.getElementById('label-name').value='Test';submit('label-form');await tick();await tick();assert.ok(document.querySelector('#label-preview svg'));click('#print-label');assert.equal(printed,1);
const file=new File(['name,lat,lon\nAED,54.19,16.18'],'aed.csv',{type:'text/csv'});document.getElementById('chaos-file').files=[file];submit('chaos-form');await tick();await tick();assert.equal(document.getElementById('chaos-results').hidden,false);click('#chaos-preview');await tick();await tick();assert.ok(document.getElementById('import-preview').textContent.includes('Lokalna baza podglądu'));
document.getElementById('upload-file').files=[file];document.getElementById('upload-file').dispatchEvent(new window.Event('change'));submit('upload-form');await tick();await tick();assert.equal(document.getElementById('validation-results').hidden,false);
context.__drawer.openTools('tool-accessibility');click('#contrast-toggle');assert.equal(document.documentElement.dataset.contrast,'high');click('#font-toggle');assert.equal(document.getElementById('font-value').textContent,'120%');click('#font-toggle');assert.equal(document.getElementById('font-value').textContent,'135%');
context.__drawer.closeTools();document.getElementById('location-query').value='Koszalin';submit('map-filters');await tick();await tick();await tick();assert.ok(calls.some(([url])=>url.startsWith('/api/location/search?')));assert.equal(document.querySelectorAll('.rescue-card').length,1);assert.ok(document.getElementById('origin-note').textContent.includes('Koszalin'));
let releaseOld;delayedNearest={promise:new Promise(resolve=>releaseOld=resolve)};click('[data-gps]');await tick();await tick();
document.getElementById('location-query').value='Nowe miejsce';submit('map-filters');await tick();await tick();assert.ok(document.getElementById('origin-note').textContent.includes('Nowe miejsce'));releaseOld();await tick();await tick();assert.ok(!document.getElementById('rescue-results').textContent.includes('STALE RESULT'),'stale nearest response cannot replace new location');
assert.ok(calls.some(([url,method])=>url==='/api/chaos-import'&&method==='POST'));
console.log(`PASS: simple screen, ${desktopMode?'desktop hover/pin/leave':'touch click/backdrop/focus trap'} drawer, 3 assistant outcomes, ESC, metronome, voice, GPS fallback, search, reports, QR/print, upload, BIP, contrast and font.`);
console.log('API calls exercised:',calls.length);
if(clusters)console.log('PASS: clustering options, 3 sizes, hidden marker pane, marker click, 1200-marker batch, latest filter wins, reduced motion and search.');
