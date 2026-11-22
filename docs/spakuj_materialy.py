"""Reproducible submission bundle with current source, cloud seed and SHA-256 manifest."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from hashlib import sha256
from datetime import datetime, timezone
import json
import os

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = ['01_zrodla.png','02_wzorzec.png','03_mapa.png','04_dysponent_qr.png','05_eksport.png']
ROOT_FILES = ['README.md','requirements.txt','requirements-lock.txt','Dockerfile','.dockerignore',
              '.gitignore','compose.yaml','uruchom_aed.py','START_AED.cmd','STOP_AED.cmd',
              'START_DOCKER.cmd','STOP_DOCKER.cmd','START_TELEFON.cmd',
              'app.py','pyproject.toml','vercel.json']
REQUIRED = ['app.py','pyproject.toml','vercel.json','backend/cloud_runtime.py','backend/cloud_store.py',
            'backend/cloud_archive.py','backend/cloud_responses.py','backend/vercel_build.py',
            'backend/data/deployment/vercel_seed.zip','frontend/index.html','frontend/app.js',
            'frontend/styles.css','frontend/rescue-ui.js','frontend/drawer.js',
            'data_standard/wzorzec_danych_aed.xlsx','docs/opis_projektu.md',
            'docs/prezentacja_otwarte_aed.pptx','docs/prezentacja_otwarte_aed.pdf',
            'docs/audyt_dostepnosci.md','docs/audyt_dostepnosci.json',
            'branding/logo_otwarte_aed.svg','branding/logo_otwarte_aed.png',
            'branding/logo_otwarte_aed.jpg','branding/logo_otwarte_aed.pdf','branding/ksiega_znaku.pdf']
EXCLUDED = {'__pycache__','node_modules','.git','.venv','.qa','logs','state','exports','exports_demo'}
SUFFIXES = {'.py','.js','.mjs','.css','.html','.svg','.png','.jpg','.jpeg','.json','.geojson',
            '.csv','.xlsx','.pdf','.pptx','.md','.txt','.yaml','.yml','.cmd','.map','.lock','.xsd','.toml'}

def selected_files():
    files = set()
    for directory in ('backend','frontend','data_standard','branding','docs'):
        for base, dirs, names in os.walk(ROOT/directory):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED and not d.startswith('.'))
            for name in sorted(names):
                path = Path(base)/name
                if name.startswith('.env') or path.is_symlink():
                    continue
                relative = path.relative_to(ROOT).as_posix()
                if path.suffix.lower() in SUFFIXES or relative in (
                    'backend/data/deployment/vercel_seed.zip','branding/logo_otwarte_aed_pakiet.zip'):
                    if relative not in ('docs/manifest_paczki.json',):
                        files.add(relative)
    files.update(name for name in ROOT_FILES if (ROOT/name).is_file())
    return sorted(files)

def main():
    from pypdf import PdfReader
    from pptx import Presentation
    from openpyxl import load_workbook
    missing = [str(p) for p in REQUIRED if not (ROOT/p).is_file()]
    missing += ['docs/zrzuty_ekranu/'+name for name in EXPECTED if not (ROOT/'docs/zrzuty_ekranu'/name).is_file()]
    if missing:
        raise RuntimeError('Brak wymaganych plików: '+', '.join(missing))
    deck = Presentation(ROOT/'docs/prezentacja_otwarte_aed.pptx')
    assert len(deck.slides) == 6
    assert not any('TUTAJ WKLEJ' in shape.text for slide in deck.slides for shape in slide.shapes if shape.has_text_frame)
    assert len(PdfReader(ROOT/'docs/prezentacja_otwarte_aed.pdf').pages) == 6
    assert len(PdfReader(ROOT/'branding/ksiega_znaku.pdf').pages) >= 1
    book = load_workbook(ROOT/'data_standard/wzorzec_danych_aed.xlsx',read_only=True)
    assert book.sheetnames == ['Schemat_Danych','Szablon_Do_Wypelnienia','Instrukcja_Dla_Dysponenta']
    assert book['Szablon_Do_Wypelnienia'].max_column == 21
    book.close()
    assert (ROOT/'branding/logo_otwarte_aed.svg').read_bytes() == (ROOT/'frontend/assets/logo_otwarte_aed.svg').read_bytes()
    audit = json.loads((ROOT/'docs/audyt_dostepnosci.json').read_text(encoding='utf-8'))
    assert audit['automated']['violations_after'] == 0
    status = {'generated_at':datetime.now(timezone.utc).isoformat(),'presentation_slides':6,
              'required_screenshots':5,'missing_screenshots':[], 'technical_package_verified':True,
              'accessibility_review_completed':True,'full_wcag_conformance_claimed':False,
              'ready_for_team_review':True,'team_approval_required':True,
              'note':'Zespół zatwierdza autorstwo, prawa i ostateczne zgłoszenie. Zakres przeglądu WCAG opisano w docs/audyt_dostepnosci.md.'}
    (ROOT/'docs/status_materialow.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    logo_zip = ROOT/'branding/logo_otwarte_aed_pakiet.zip'
    with ZipFile(logo_zip,'w',ZIP_DEFLATED,compresslevel=9) as archive:
        for path in sorted((ROOT/'branding').iterdir()):
            if path.is_file() and path.suffix.lower() in SUFFIXES:
                archive.write(path,path.name)
    files = selected_files()
    assert all(name in files for name in REQUIRED)
    manifest = {'generated_at':status['generated_at'],'algorithm':'SHA-256',
                'note':'Manifest opisuje wszystkie pliki paczki poza samym manifestem.',
                'files':[{ 'path':name,'bytes':(ROOT/name).stat().st_size,
                           'sha256':sha256((ROOT/name).read_bytes()).hexdigest()} for name in files]}
    manifest_path = ROOT/'docs/manifest_paczki.json'
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    package = ROOT/'docs/materialy_otwarte_aed.zip'
    temporary = package.with_suffix('.tmp')
    with ZipFile(temporary,'w',ZIP_DEFLATED,compresslevel=9) as archive:
        for name in files + ['docs/manifest_paczki.json']:
            archive.write(ROOT/name,name)
    with ZipFile(temporary) as archive:
        assert archive.testzip() is None
        for item in manifest['files']:
            assert sha256(archive.read(item['path'])).hexdigest() == item['sha256'], item['path']
        assert not any(part in EXCLUDED or part.startswith('.env') for name in archive.namelist() for part in Path(name).parts)
    temporary.replace(package)
    digest = sha256(package.read_bytes()).hexdigest()
    package.with_suffix('.zip.sha256').write_text(digest+'  '+package.name+'\n',encoding='ascii')
    print(f'Paczka: {len(files)+1} plików, {package.stat().st_size} B; wszystkie sumy SHA-256 zgodne.')

if __name__ == '__main__':
    main()
