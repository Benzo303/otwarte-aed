"""Tworzy paczkę logo i roboczy pakiet konkursowy z kodem, bez środowisk i zgłoszeń."""
from pathlib import Path
import json
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
EXPECTED=['01_zrodla.png','02_wzorzec.png','03_mapa.png','04_dysponent_qr.png','05_eksport.png']

def main():
    missing=[name for name in EXPECTED if not (ROOT/'docs/zrzuty_ekranu'/name).exists()]
    status={'presentation_slides':6,'required_screenshots':5,'missing_screenshots':missing,
            'ready_for_submission':not missing,'note':'Zespół musi zatwierdzić finalną pracę. Brakujące obrazy uzupełnij zgodnie z instrukcją zrzutów.'}
    (ROOT/'docs/status_materialow.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
    logo_zip=ROOT/'branding/logo_otwarte_aed_pakiet.zip'
    with ZipFile(logo_zip,'w',ZIP_DEFLATED,compresslevel=9) as archive:
        for path in sorted((ROOT/'branding').iterdir()):
            if path.is_file() and path.suffix.lower() in ('.svg','.png','.jpg','.pdf','.json','.md','.py','.txt'):
                archive.write(path,path.name)
    package=ROOT/'docs/materialy_otwarte_aed.zip'
    excluded={'__pycache__','node_modules','.git','.venv','logs','state','exports','exports_demo'}
    allowed={'.py','.js','.mjs','.css','.html','.svg','.png','.jpg','.json','.geojson','.csv','.xlsx','.pdf','.pptx','.md','.txt','.yaml','.cmd','.map','.lock','.xsd'}
    count=0
    with ZipFile(package,'w',ZIP_DEFLATED,compresslevel=9) as archive:
        for directory in ('backend','frontend','data_standard','branding','docs'):
            for path in sorted((ROOT/directory).rglob('*')):
                relative=path.relative_to(ROOT)
                if path.is_file() and not excluded.intersection(relative.parts) and path.suffix.lower() in allowed:
                    archive.write(path,str(relative));count+=1
        for name in ('README.md','requirements.txt','requirements-lock.txt','Dockerfile','.dockerignore','.gitignore','compose.yaml','uruchom_aed.py','START_AED.cmd','STOP_AED.cmd','START_DOCKER.cmd','STOP_DOCKER.cmd','START_TELEFON.cmd','GENERUJ_PREZENTACJE.cmd'):
            path=ROOT/name
            if path.exists():archive.write(path,name);count+=1
    for path in (logo_zip,package):
        with ZipFile(path) as archive:assert archive.testzip() is None
    print(f'Logo ZIP: {logo_zip.stat().st_size} B; materiały: {count} plików, {package.stat().st_size} B; brakuje {len(missing)} zrzutów.')

if __name__=='__main__':main()
