export function aedName(row) {
  return row.nazwa_obiektu || row.ulica_numer || 'Defibrylator';
}

export function sourceLabel(row) {
  const gov=(row.sources||[]).some(source=>source.dataset_id);
  const osm=(row.sources||[]).some(source=>source.name==='OpenStreetMap');
  return gov?(osm?'dane.gov.pl + OSM':'API dane.gov.pl'):(osm?'OpenStreetMap':'Rejestr dysponenta');
}

export function accessState(row) {
  if(row.field_access_alert==='damaged')return {kind:'closed',label:'Zgłoszono uszkodzenie',symbol:'!'};
  if(row.field_access_alert==='closed')return {kind:'closed',label:'Zgłoszono brak dostępu',symbol:'×'};
  if (row.dostepnosc_typ === 'niedostepny' || row.status_techniczny === 'serwis') return {kind:'closed', label:'Niedostępny', symbol:'×'};
  if (row.dostepnosc_typ === 'na_klucz_lub_kod' || row.wymagany_klucz_lub_kod === 'TAK') return {kind:'locked', label:'Wymaga klucza / portierni', symbol:'K'};
  if (row.otwarte_teraz === true && row.dostepnosc_typ === '24_7') return {kind:'all-day', label:'Dostępny 24/7', symbol:'24'};
  if (row.otwarte_teraz === true) return {kind:'open', label:'Otwarty teraz', symbol:'✓'};
  if (row.otwarte_teraz === false) return {kind:'closed', label:'Teraz zamknięty', symbol:'×'};
  return {kind:'unknown', label:'Dostępność niepotwierdzona', symbol:'?'};
}

export function walkingEstimate(lat1,lon1,lat2,lon2){
  const rad=value=>value*Math.PI/180;const dlat=rad(lat2-lat1),dlon=rad(lon2-lon1);
  const a=Math.sin(dlat/2)**2+Math.cos(rad(lat1))*Math.cos(rad(lat2))*Math.sin(dlon/2)**2;
  const straight=6371008.8*2*Math.asin(Math.sqrt(Math.min(1,Math.max(0,a))));
  return {straight_distance_m:Math.round(straight),walking_distance_m:Math.round(straight*1.25),walking_time_seconds:Math.round(straight*1.25/(5000/3600)),round_trip_seconds:Math.round(2*straight*1.25/(5000/3600))};
}

export function safeURL(value) {
  try { const url = new URL(value); return ['http:','https:'].includes(url.protocol) && !url.username && !url.password ? url.href : null; }
  catch { return null; }
}

export function confidence(value) { return Number.isFinite(Number(value)) ? Math.max(0,Math.min(100,Number(value))) : 0; }
export function escapeXML(value) { return String(value).replace(/[<>&"']/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;',"'":'&apos;'}[c])); }
export function filterRows(rows, query) {
  const needle = query.trim().toLocaleLowerCase('pl');
  return rows.filter(row => !needle || [aedName(row), row.ulica_numer, row.miejscowosc, row.miejscowosc_wyszukiwania, row.id_aed, row.opis_lokalizacji_wewnatrz].some(value => String(value || '').toLocaleLowerCase('pl').includes(needle)))
    .sort((a,b)=> confidence(b.confidence_score)-confidence(a.confidence_score) || aedName(a).localeCompare(aedName(b),'pl') || a.id_aed.localeCompare(b.id_aed));
}

export function labelURL(base, id) {
  const safe = safeURL(base);
  if (!safe) throw new Error('Wpisz poprawny adres aplikacji HTTP lub HTTPS bez danych logowania.');
  if (!/^[A-Za-z0-9_.:\-]{3,100}$/.test(id)) throw new Error('Identyfikator musi mieć 3–100 znaków: litery, cyfry, kropka, podkreślenie, dwukropek lub myślnik.');
  const url = new URL(safe);
  url.search = '';
  url.searchParams.set('aed', id);
  url.hash = '';
  return url.href;
}

export function labelSVG(qr, name, id, url) {
  const n = qr.getModuleCount();
  let path = '';
  for (let y=0;y<n;y++) for (let x=0;x<n;x++) if (qr.isDark(y,x)) path += `M${x+4} ${y+4}h1v1h-1z`;
  const words = name.split(/\s+/).flatMap(word=>word.match(/.{1,20}/gu)||[]);
  const lines = [''];
  words.forEach(word => { if ((lines.at(-1)+' '+word).trim().length>20 && lines.at(-1)) lines.push(word); else lines[lines.length-1] = (lines.at(-1)+' '+word).trim(); });
  if(lines.length>4)lines[3]=lines[3].slice(0,19)+'…';
  const heading = lines.slice(0,4).map((line,i)=>`<text x="55" y="${225+i*38}" font-size="28" font-weight="700">${escapeXML(line)}</text>`).join('');
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="620" viewBox="0 0 1080 620" role="img" aria-label="Etykieta AED: ${escapeXML(name)}"><title>Etykieta AED: ${escapeXML(name)}</title><desc>Kod QR prowadzi do ${escapeXML(url)}</desc><rect width="1080" height="620" fill="white"/><rect x="12" y="12" width="1056" height="596" rx="25" fill="white" stroke="#123b34" stroke-width="6"/><g font-family="Arial,sans-serif" fill="#123b34"><text x="55" y="100" font-size="43">otwarte<tspan font-weight="800">AED</tspan></text><text x="55" y="155" font-size="22">SPRAWDŹ INFORMACJE O URZĄDZENIU</text>${heading}<text x="55" y="380" font-size="21">${escapeXML(id)}</text><text x="55" y="465" font-size="25" font-weight="700">Zeskanuj. Sprawdź dostęp.</text><text x="55" y="506" font-size="20">Lokalizacja, godziny i źródło danych.</text><text x="55" y="560" font-size="18">W sytuacji zagrożenia życia zadzwoń pod 112.</text></g><svg x="660" y="150" width="350" height="350" viewBox="0 0 ${n+8} ${n+8}" shape-rendering="crispEdges"><rect width="${n+8}" height="${n+8}" fill="white"/><path d="${path}" fill="black"/></svg><text x="835" y="545" text-anchor="middle" fill="#123b34" font-size="20" font-family="Arial,sans-serif">AKTUALNE DANE O AED</text></svg>`;
}
