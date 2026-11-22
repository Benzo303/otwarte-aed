"""Przygotowanie krajowej migawki podczas budowania, zamiast podczas żądania."""
from pathlib import Path
from .cloud_archive import pack_snapshot
from .harvester_export import build_snapshot
from .cloud_runtime import public_base_url

OUTPUT=Path(__file__).parent/'data/deployment/vercel_seed.zip'

def main():
    records,report,bundle=build_snapshot(area='polska',offline=True,base_url=public_base_url())
    gov=Path(__file__).parent/'data/cache/danegov_cache.json'
    payload=pack_snapshot({'records':records,'report':report,'bundle':bundle},gov.read_bytes())
    if len(payload)>25*1024*1024:raise RuntimeError('Migawka przekracza limit przesyłania przez stronę GitHub.')
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    temporary=OUTPUT.with_suffix('.tmp')
    temporary.write_bytes(payload)
    temporary.replace(OUTPUT)
    print(f'Gotowa migawka: {len(records)} AED, {len(payload)} bajtów. Źródła: OSM + dane.gov.pl z jawnego cache.')

if __name__=='__main__':main()
