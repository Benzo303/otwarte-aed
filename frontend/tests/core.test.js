import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {accessState, filterRows, safeURL, confidence, labelURL, labelSVG, sourceLabel, walkingEstimate} from '../core.js';

test('pochodzenie rozróżnia API dane.gov.pl, OSM i połączone źródła',()=>{
  assert.equal(sourceLabel({sources:[{dataset_id:'123'}]}),'API dane.gov.pl');
  assert.equal(sourceLabel({sources:[{name:'OpenStreetMap'}]}),'OpenStreetMap');
  assert.equal(sourceLabel({sources:[{dataset_id:'123'},{name:'OpenStreetMap'}]}),'dane.gov.pl + OSM');
  assert.equal(sourceLabel({sources:[]}),'Rejestr dysponenta');
});

test('status dostępu nie uznaje samego tagu 24_7 za dostęp teraz',()=>{
  assert.equal(accessState({dostepnosc_typ:'24_7',otwarte_teraz:null}).kind,'unknown');
  assert.equal(accessState({dostepnosc_typ:'24_7',otwarte_teraz:true}).kind,'all-day');
  assert.equal(accessState({dostepnosc_typ:'godziny_pracy',otwarte_teraz:true}).kind,'open');
  assert.equal(accessState({dostepnosc_typ:'godziny_pracy',otwarte_teraz:false}).kind,'closed');
});
test('klucz i serwis mają pierwszeństwo przed flagą otwarcia',()=>{
  assert.equal(accessState({otwarte_teraz:true,wymagany_klucz_lub_kod:'TAK'}).kind,'locked');
  assert.equal(accessState({otwarte_teraz:true,status_techniczny:'serwis'}).kind,'closed');
});

test('świeże zgłoszenie terenowe wyklucza otwarcie mimo harmonogramu 24/7',()=>{
  assert.equal(accessState({dostepnosc_typ:'24_7',otwarte_teraz:true,field_access_alert:'damaged'}).kind,'closed');
  assert.equal(accessState({dostepnosc_typ:'24_7',otwarte_teraz:true,field_access_alert:'closed'}).label,'Zgłoszono brak dostępu');
});

test('szacunek marszu uwzględnia powrót i współczynnik trasy miejskiej',()=>{
  const result=walkingEstimate(52.23,21.01,52.231,21.01);
  assert.ok(result.straight_distance_m>=110&&result.straight_distance_m<=112);
  assert.ok(Math.abs(result.walking_distance_m-result.straight_distance_m*1.25)<=1);
  assert.ok(Math.abs(result.round_trip_seconds-2*result.walking_time_seconds)<=1);
  assert.equal(walkingEstimate(52.23,21.01,52.23,21.01).round_trip_seconds,0);
});
test('bezpieczne linki blokują skrypty i dane logowania',()=>{
  assert.equal(safeURL('javascript:alert(1)'),null);
  assert.equal(safeURL('https://name:password@example.org'),null);
  assert.equal(safeURL('https://example.org/aed/1'),'https://example.org/aed/1');
});
test('wyszukiwanie i sortowanie nie zmieniają danych wejściowych',()=>{
  const rows=[{id_aed:'A',nazwa_obiektu:'Urząd',miejscowosc:'Warszawa',confidence_score:50},{id_aed:'B',nazwa_obiektu:'Biblioteka',miejscowosc:'Warszawa',confidence_score:90}];
  assert.deepEqual(filterRows(rows,'WARSZAWA').map(row=>row.id_aed),['B','A']);
  assert.deepEqual(rows.map(row=>row.id_aed),['A','B']);
  assert.equal(filterRows(rows,'urząd')[0].id_aed,'A');
});
test('zakres wskaźnika kompletności',()=>{
  assert.equal(confidence(-1),0);assert.equal(confidence(125),100);assert.equal(confidence('bad'),0);
});
test('QR zawiera link do AED i nie zachowuje zbędnych parametrów',()=>{
  assert.equal(labelURL('https://aed.example.org/?stary=1#integracja','OSM-node-123'),'https://aed.example.org/?aed=OSM-node-123');
  assert.throws(()=>labelURL('javascript:alert(1)','OSM-node-123'));
  assert.throws(()=>labelURL('https://aed.example.org','<script>'));
});
test('etykieta używa prawdziwej macierzy QR i escapuje tekst',()=>{
  const sandbox={};vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(new URL('../vendor/qrcode.js',import.meta.url),'utf8'),sandbox);
  const qr=sandbox.qrcode(0,'M');qr.addData('https://aed.example.org/?aed=OSM-node-123#mapa','Byte');qr.make();
  assert.ok(qr.getModuleCount()>=21);
  const svg=labelSVG(qr,'Biblioteka <script> & hol','OSM-node-123','https://aed.example.org/?aed=OSM-node-123#mapa');
  assert.ok(svg.includes('&lt;script&gt;'));
  assert.ok(!svg.includes('<script>'));
  assert.ok(svg.includes('shape-rendering="crispEdges"'));
  assert.ok((svg.match(/h1v1h-1z/g)||[]).length>100);
});
