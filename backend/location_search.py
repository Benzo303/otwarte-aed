"""Jawne wyszukiwanie miejscowości/adresu: cache, Polska, wspólny limit OSM."""
import json
import os
from pathlib import Path
import tempfile
import time
import requests
from .city_search import CityResolver, CitySearchError, city_key
from .normalizer import haversine
from .quality_audit import in_poland

from .runtime_paths import cache_dir
CACHE_PATH=cache_dir()/'locations.json'


class LocationResolver:
    def __init__(self,cache_path=CACHE_PATH,session=None,allow_network=True):
        self.cache_path=Path(cache_path);self.session=session or requests.Session();self.allow_network=allow_network

    def _read(self):
        try:return json.loads(self.cache_path.read_text(encoding='utf-8'))
        except (OSError,ValueError):return {}

    def resolve(self,query):
        normalized=city_key(query)
        with CityResolver._network_lock:
            cache=self._read()
            if normalized in cache:return {**cache[normalized],'from_cache':True}
            if not self.allow_network:raise CitySearchError('Nie mamy zapisanej tej lokalizacji. Użyj lokalizacji telefonu lub wskaż miejsce na mapie.',503)
            delay=1.05-(time.monotonic()-CityResolver._last_request)
            if delay>0:time.sleep(delay)
            CityResolver._last_request=time.monotonic()
            try:
                response=self.session.get(os.getenv('AED_GEOCODER_URL','https://nominatim.openstreetmap.org/search'),
                    params={'q':query,'countrycodes':'pl','format':'jsonv2','addressdetails':1,'limit':5},
                    headers={'User-Agent':'OtwarteAED/0.4 explicit location search','Accept-Language':'pl'},timeout=(5,12))
                response.raise_for_status()
                if len(response.content)>1024*1024:raise ValueError('Odpowiedź za duża.')
                document=response.json()
                if not isinstance(document,list):raise ValueError('Niepoprawna odpowiedź geokodera.')
            except (requests.RequestException,ValueError) as exc:
                raise CitySearchError('Nie udało się odnaleźć miejsca. Spróbuj ponownie, użyj GPS lub wskaż miejsce na mapie.',503) from exc
            candidates=[]
            for item in document:
                try:lat,lon=float(item['lat']),float(item['lon'])
                except (KeyError,ValueError,TypeError):continue
                if (item.get('address') or {}).get('country_code')!='pl' or not in_poland(lat,lon):continue
                candidates.append({**item,'lat':lat,'lon':lon})
            preferred=[r for r in candidates if r.get('addresstype') in ('city','town') and city_key(r.get('name'))==normalized]
            if preferred:candidates=preferred
            if not candidates:raise CitySearchError('Nie znaleziono tego miejsca w Polsce. Dopisz miejscowość, np. Koszalin, Zwycięstwa 1.',404)
            first=candidates[0]
            def road_key(item):
                address=item.get('address') or {}
                city=address.get('city') or address.get('town') or address.get('village')
                road=address.get('road') or address.get('pedestrian') or address.get('footway')
                return (city_key(city),city_key(road)) if city and road else None
            same_road=road_key(first) and all(road_key(r)==road_key(first) for r in candidates)
            # Nie wybieramy ulicy w przypadkowym mieście ani miejscowości o tej samej nazwie.
            if not same_road and any(haversine(first['lat'],first['lon'],r['lat'],r['lon'])>500 for r in candidates[1:]):
                raise CitySearchError('Znaleziono kilka miejsc. Dopisz miejscowość, numer budynku lub województwo.',422)
            result={'lat':first['lat'],'lon':first['lon'],'label':first.get('display_name') or query,
                'query':query,'source':'OpenStreetMap / Nominatim',
                'origin_note':'Czas dojścia liczymy od wskazanego miejsca. Nie jest to Twoja pozycja GPS.'}
            cache[normalized]=result
            self.cache_path.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self.cache_path.parent,suffix='.tmp',delete=False) as stream:
                path=Path(stream.name);stream.write(json.dumps(cache,ensure_ascii=False,allow_nan=False).encode('utf-8'))
            path.replace(self.cache_path)
            return {**result,'from_cache':False}
