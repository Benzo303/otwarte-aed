import copy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock,patch
from fastapi.testclient import TestClient
import requests
from .city_search import CitySearchError
from .location_search import LocationResolver
from .main import create_app
from .test_features import point
from .test_pipeline import MONDAY


class SimpleSearchTests(unittest.TestCase):
    def test_location_endpoint_and_radius_filter_preserve_old_routes(self):
        resolver=Mock();resolver.resolve.return_value={'lat':52.23,'lon':21.01,'label':'Warszawa'}
        near=point();far=point('FAR',54.19,16.18)
        with TestClient(create_app(records=[near,far],clock=lambda:MONDAY,location_resolver=resolver)) as client:
            self.assertEqual(client.get('/api/location/search?q=Warszawa').json()['label'],'Warszawa')
            self.assertEqual(client.get('/api/aed').json()['count'],2)
            response=client.get('/api/aed?lat=52.23&lon=21.01&radius_km=2&tylko_otwarte_teraz=true')
            self.assertEqual([r['id_aed'] for r in response.json()['items']],['OPEN'])
            self.assertEqual(client.get('/api/aed?lat=52.23').status_code,422)
            self.assertEqual(client.get('/api/aed?lat=NaN&lon=21').status_code,422)
            self.assertEqual(client.get('/api/location/search?q=%20%20').status_code,422)
            resolver.resolve.side_effect=CitySearchError('Dopisz miejscowość.',422)
            self.assertEqual(client.get('/api/location/search?q=Długa').status_code,422)

    def test_nearest_respects_selected_source(self):
        osm=point();osm['sources']=[{'name':'OpenStreetMap','license':'ODbL-1.0'}]
        gov=point('GOV',52.231);gov['sources']=[{'name':'Urząd','dataset_id':'123','license':'CC0-1.0'}]
        with TestClient(create_app(records=[osm,gov],clock=lambda:MONDAY)) as client:
            body={'lat':52.23,'lon':21.01,'zrodlo':'danegov'}
            self.assertEqual([r['id_aed'] for r in client.post('/api/rescue/nearest',json=body).json()['top3']],['GOV'])
            body['zrodlo']='osm'
            self.assertEqual([r['id_aed'] for r in client.post('/api/rescue/nearest',json=body).json()['top3']],['OPEN'])

    def test_location_lookup_cache_offline_and_ambiguity(self):
        item={'lat':'54.19','lon':'16.18','name':'Koszalin','display_name':'Koszalin, Polska','addresstype':'city','address':{'country_code':'pl'}}
        session=Mock();session.get.return_value.content=b'[]';session.get.return_value.json.return_value=[item]
        with TemporaryDirectory() as directory:
            path=Path(directory)/'locations.json';resolver=LocationResolver(path,session=session)
            with patch('backend.location_search.time.sleep'):result=resolver.resolve('Koszalin')
            self.assertEqual(result['lat'],54.19)
            offline=LocationResolver(path,allow_network=False)
            self.assertTrue(offline.resolve('KOSZALIN')['from_cache'])
            with self.assertRaises(CitySearchError):offline.resolve('Nieznane miasto')
            other=copy.deepcopy(item);other.update(lat='52.23',lon='21.01')
            session.get.return_value.json.return_value=[item,other]
            with patch('backend.location_search.time.sleep'),self.assertRaisesRegex(CitySearchError,'kilka miejsc'):resolver.resolve('Długa')
            road=copy.deepcopy(item);road['addresstype']='road';road['address'].update(city='Koszalin',road='Zwycięstwa')
            other=copy.deepcopy(road);other['lon']='16.23'
            session.get.return_value.json.return_value=[road,other]
            with patch('backend.location_search.time.sleep'):
                self.assertEqual(resolver.resolve('Koszalin, Zwycięstwa')['lat'],54.19)

    def test_geocoder_failure_is_actionable(self):
        with TemporaryDirectory() as directory:
            session=Mock();session.get.side_effect=requests.Timeout()
            resolver=LocationResolver(Path(directory)/'cache.json',session=session)
            with patch('backend.location_search.time.sleep'),self.assertRaises(CitySearchError) as error:resolver.resolve('Koszalin')
            self.assertEqual(error.exception.status_code,503)

if __name__=='__main__':unittest.main(verbosity=2)
