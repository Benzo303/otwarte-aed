"""Sześć edytowalnych slajdów i zgodny PDF; pięć miejsc na rzeczywiste zrzuty."""
from pathlib import Path
from io import BytesIO
import json
import sys
from zipfile import ZipFile
import requests
from PIL import Image
from pptx import Presentation
from pptx.util import Inches,Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE,MSO_CONNECTOR
from pptx.enum.text import PP_ALIGN
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.oxml.xmlchemy import OxmlElement
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.graphics import renderPDF
from svglib.svglib import svg2rlg
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from branding.brand_assets import RED,NAVY,WHITE,LIGHT,SLATE,font_path

OUT=ROOT/'docs/prezentacja_otwarte_aed.pptx';PDF=OUT.with_suffix('.pdf')
SCREENSHOTS=ROOT/'docs/zrzuty_ekranu';SCREENSHOTS.mkdir(exist_ok=True)
SW,SH=13.333333,7.5
FILES=['01_zrodla.png','02_wzorzec.png','03_mapa.png','04_dysponent_qr.png','05_eksport.png']

def read_evidence():
    try:
        response=requests.get('http://127.0.0.1:8000/api/sources/stats',timeout=5);response.raise_for_status();data=response.json()
        result={k:data.get(k) for k in ('osm_records','danegov_records','duplicates_merged','integrated_records','cross_source_groups','generated_at')}
        result['datasets']=[{k:d.get(k) for k in ('id','title','institution_title','records_count','status')} for d in data.get('datasets',[])]
        (ROOT/'docs/dane_prezentacji.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        return result
    except (requests.RequestException,ValueError):
        path=ROOT/'docs/dane_prezentacji.json'
        if path.exists():return json.loads(path.read_text(encoding='utf-8'))
        raise RuntimeError('Uruchom aplikację, aby pobrać rzeczywiste liczby do prezentacji.')

def rgb(value):return RGBColor.from_string(value.lstrip('#'))

class Deck:
    def __init__(self):
        self.prs=Presentation();self.prs.slide_width=Inches(SW);self.prs.slide_height=Inches(SH)
        self.prs.core_properties.title='Otwarte AED — Dane na ratunek'
        self.prs.core_properties.author='Zespół Otwarte AED'
        self.prs.core_properties.subject='Integracja rozproszonych danych o defibrylatorach dla dane.gov.pl'
        self.pdf=canvas.Canvas(str(PDF),pagesize=(SW*72,SH*72),pageCompression=1)
        self.pdf.setTitle('Otwarte AED — Dane na ratunek');self.pdf.setAuthor('Zespół Otwarte AED')
        pdfmetrics.registerFont(TTFont('Deck',str(font_path())));pdfmetrics.registerFont(TTFont('DeckB',str(font_path(True))))
        self.slide=None;self.number=0;self.actual=0

    def text(self,value,x,y,w,h,size=18,bold=False,color=NAVY,align='left',name=None):
        lines=[]
        for raw in value.split('\n'):
            current=''
            for word in raw.split():
                candidate=(current+' '+word).strip()
                if current and pdfmetrics.stringWidth(candidate,'DeckB' if bold else 'Deck',size)>w*72*.98:
                    lines.append(current);current=word
                else:current=candidate
            lines.append(current)
        assert len(lines)*size*1.18<=h*72+4,(value,len(lines),h)
        shape=self.slide.shapes.add_textbox(Inches(x),Inches(y),Inches(w),Inches(h));shape.name=name or value[:80]
        frame=shape.text_frame;frame.clear();frame.word_wrap=True
        frame.margin_left=frame.margin_right=frame.margin_top=frame.margin_bottom=0
        for i,line in enumerate(lines):
            p=frame.paragraphs[0] if i==0 else frame.add_paragraph();p.text=line;p.font.name='Arial';p.font.size=Pt(size);p.font.bold=bold;p.font.color.rgb=rgb(color);p.line_spacing=1.18;p.space_after=Pt(0)
            p.alignment=PP_ALIGN.CENTER if align=='center' else PP_ALIGN.LEFT
            self.pdf.setFont('DeckB' if bold else 'Deck',size);self.pdf.setFillColor(colors.HexColor(color))
            xx=(x+w/2)*72 if align=='center' else x*72;yy=SH*72-y*72-size-i*size*1.18
            if align=='center':self.pdf.drawCentredString(xx,yy,line)
            else:self.pdf.drawString(xx,yy,line)
        return shape

    def line(self,x1,y1,x2,y2,color='#D8DFEA',width=.8,arrow=False):
        shape=self.slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,Inches(x1),Inches(y1),Inches(x2),Inches(y2));shape.line.color.rgb=rgb(color);shape.line.width=Pt(width)
        if arrow:
            element=OxmlElement('a:tailEnd');element.set('type','triangle');shape._element.spPr.find('{http://schemas.openxmlformats.org/drawingml/2006/main}ln').append(element)
        self.pdf.setStrokeColor(colors.HexColor(color));self.pdf.setLineWidth(width);self.pdf.line(x1*72,(SH-y1)*72,x2*72,(SH-y2)*72)
        if arrow:
            self.pdf.line((x2-.06)*72,(SH-y2+.035)*72,x2*72,(SH-y2)*72);self.pdf.line((x2-.06)*72,(SH-y2-.035)*72,x2*72,(SH-y2)*72)

    def logo(self,x,y,w):
        h=w*200/700
        image=self.slide.shapes.add_picture(str(ROOT/'branding/logo_otwarte_aed.png'),Inches(x),Inches(y),width=Inches(w),height=Inches(h))
        image.name='Otwarte AED — oficjalny plik logotypu kampanii';image._element.nvPicPr.cNvPr.set('descr','Otwarte AED. Dane, które ratują minuty.')
        drawing=svg2rlg(str(ROOT/'branding/logo_otwarte_aed.svg'))
        self.pdf.saveState();self.pdf.translate(x*72,(SH-y-h)*72);self.pdf.scale(w*72/drawing.width,h*72/drawing.height);renderPDF.draw(drawing,self.pdf,0,0);self.pdf.restoreState()

    def start(self,title=None,section=None):
        if self.slide is not None:self.pdf.showPage()
        self.number+=1;self.slide=self.prs.slides.add_slide(self.prs.slide_layouts[6]);self.slide.background.fill.solid();self.slide.background.fill.fore_color.rgb=rgb(WHITE)
        if title:
            self.text(section.upper(),.72,.38,9,.22,size=10,bold=True,color=SLATE)
            self.text(title,.72,.81,11.9,.7,size=32,bold=True)
            self.line(.73,1.51,1.30,1.51,RED,2.5)
        self.text('OTWARTE AED  /  MISJA-AED',.73,7.14,7,.2,size=9,bold=True,color=SLATE)
        self.text(f'{self.number:02d} / 06',11.81,7.14,.8,.2,size=9,color=SLATE)

    def evidence(self,index,label):
        x,y,w,h=5.25,1.86,7.35,4.25
        source=SCREENSHOTS/FILES[index]
        if source.exists():
            iw,ih=Image.open(source).size
            if iw/ih<.9 and index in (0,3,4):
                self.picture_view(source,(x,y,2.55,h))
                region={0:(0,0,1,.31),3:(.02,.63,.98,.94),4:(.02,.25,.96,.81)}[index]
                self.picture_view(source,(8.0,2.02,4.6,3.85),region)
                caption={0:'Powiększenie liczników integracji',3:'Powiększenie gotowej tabliczki QR',4:'Powiększenie fragmentu XML'}[index]
                self.text(caption,8.0,6.02,4.6,.25,size=11,color=SLATE)
            else:self.picture_view(source,(x,y,w,h))
            self.actual+=1
        else:
            shape=self.slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,Inches(x),Inches(y),Inches(w),Inches(h));shape.name='ZRZUT DO UZUPEŁNIENIA: '+label
            shape.fill.solid();shape.fill.fore_color.rgb=rgb(LIGHT);shape.line.color.rgb=rgb('#C6D0E0');shape.line.width=Pt(1);shape.line.dash_style=MSO_LINE_DASH_STYLE.DASH
            self.pdf.setFillColor(colors.HexColor(LIGHT));self.pdf.setStrokeColor(colors.HexColor('#C6D0E0'));self.pdf.setLineWidth(1);self.pdf.setDash(4,4);self.pdf.rect(x*72,(SH-y-h)*72,w*72,h*72,fill=1,stroke=1);self.pdf.setDash()
            self.text('[TUTAJ WKLEJ ZRZUT EKRANU:',x+.45,y+1.55,w-.9,.36,size=17,bold=True,color=SLATE,align='center')
            self.text(label+']',x+.45,y+2.04,w-.9,.9,size=18,bold=True,color=NAVY,align='center')
            self.text('Rzeczywisty widok działającego prototypu',x+.45,y+3.12,w-.9,.35,size=13,color=SLATE,align='center')
        self.text(label,x,6.28,w,.3,size=11,color=SLATE)

    def picture_view(self,source,box,region=(0,0,1,1)):
        """Kadrowanie wyłącznie w układzie slajdu; oryginalny PNG pozostaje bez zmian."""
        iw,ih=Image.open(source).size
        left,top,right,bottom=region;cw,ch=iw*(right-left),ih*(bottom-top)
        x,y,w,h=box;scale=min(w/cw,h/ch);ww,hh=cw*scale,ch*scale;xx=x+(w-ww)/2;yy=y+(h-hh)/2
        picture=self.slide.shapes.add_picture(str(source),Inches(xx),Inches(yy),width=Inches(ww),height=Inches(hh))
        picture.crop_left=left;picture.crop_top=top;picture.crop_right=1-right;picture.crop_bottom=1-bottom
        picture._element.nvPicPr.cNvPr.set('descr',f'Rzeczywisty zrzut prototypu: {source.name}')
        self.pdf.saveState();clip=self.pdf.beginPath();clip.rect(xx*72,(SH-yy-hh)*72,ww*72,hh*72);self.pdf.clipPath(clip,stroke=0,fill=0)
        self.pdf.drawImage(ImageReader(str(source)),(xx-left*iw*scale)*72,(SH-yy-(ih-top*ih)*scale)*72,iw*scale*72,ih*scale*72,mask='auto')
        self.pdf.restoreState()

    def notes(self,value):self.slide.notes_slide.notes_text_frame.text=value

    def save(self):
        for slide in self.prs.slides:
            for shape in slide.shapes:
                style=shape._element.find('{http://schemas.openxmlformats.org/presentationml/2006/main}style')
                if style is not None:shape._element.remove(style)
                properties=shape._element.find('{http://schemas.openxmlformats.org/presentationml/2006/main}spPr')
                if properties is not None:properties.append(OxmlElement('a:effectLst'))
        self.pdf.save();self.prs.save(OUT)
        assert len(self.prs.slides)==6
        with ZipFile(OUT) as archive:assert archive.testzip() is None
        assert len(PdfReader(PDF).pages)==6
        for slide in self.prs.slides:
            for shape in slide.shapes:
                assert shape.left>=0 and shape.top>=0
                assert shape.left+shape.width<=self.prs.slide_width+10
                assert shape.top+shape.height<=self.prs.slide_height+10
        print(f'Prezentacja: 6 slajdów, {self.actual}/5 zrzutów; PPTX {OUT.stat().st_size} B; PDF {PDF.stat().st_size} B.')


def build():
    stats=read_evidence();d=Deck();d.start()
    evidence_note=('Prezentacja zawiera pięć rzeczywistych zrzutów prototypu przekazanych przez zespół.'
                   if all((SCREENSHOTS/name).exists() for name in FILES)
                   else 'Materiał roboczy: brakujące zrzuty należy uzupełnić przed zgłoszeniem.')
    d.text('MISJA AED  /  DANE NA RATUNEK',.77,.72,11,.3,size=12,bold=True,color=SLATE)
    d.logo(.82,2.05,11.55)
    d.text('Otwarty zbiór danych o defibrylatorach',.83,5.48,11.7,.5,size=26,bold=True)
    d.text('Integracja dla dane.gov.pl · prototyp zespołu',.85,6.10,11.5,.35,size=17,color=SLATE)
    d.notes('Nazwa akcji: Otwarte AED. Hasło: Dane, które ratują minuty. Logotyp pochodzi z branding/logo_otwarte_aed.svg, a jego dokładna kopia jest na stronie. Hasło kampanii nie jest wynikiem pomiaru czasu reakcji. '+evidence_note)

    d.start('Jeden zbiór z wielu źródeł','Integracja i architektura')
    n=f"{stats['integrated_records']:,}".replace(',',' ')
    d.text(n,.75,1.98,4.2,.92,size=57,bold=True,color=RED)
    d.text('lokalizacji po połączeniu',.78,3.02,4.2,.45,size=22,bold=True)
    fmt=lambda value:f'{int(value):,}'.replace(',',' ')
    d.text(f"{fmt(stats['osm_records'])} obiektów OpenStreetMap\n{fmt(stats['danegov_records'])} rekordów z dane.gov.pl\n{fmt(stats['duplicates_merged'])} scaleń przy odległości <25 m",.78,3.85,4.3,1.5,size=17)
    d.text('Krosno 3624 · Przemyśl 4581\nMarki 4955 · Warszawa 39512*',.78,5.68,4.3,.7,size=15,color=SLATE)
    d.evidence(0,'POŁĄCZONE ŹRÓDŁA I LICZNIKI')
    d.text('*Warszawa: 0 rekordów; zasób zwraca HTML.',.78,6.25,4.3,.3,size=11,color=SLATE)
    for label,x in [('Źródła',.78),('Cache + 21 pól',3.82),('Baza FastAPI',7.01),('Eksport / XSD',10.35)]:
        d.text(label,x,6.72,2.45,.36,size=17,bold=True)
    for x1,x2 in [(2.15,3.66),(5.96,6.85),(9.04,10.18)]:d.line(x1,6.88,x2,6.88,RED,1.4,arrow=True)
    d.notes('Źródło liczb: GET /api/sources/stats, zapis docs/dane_prezentacji.json. OSM 18307 + dane.gov.pl 49 - 975 scaleń = 17381. Zasoby Krosna: 21 rekordów, Przemyśla: 21, Marek: 7 (6 punktów po deduplikacji). *Warszawa jest odnaleziona, ale jej wskazany plik zwraca HTML zamiast danych: 0 zintegrowanych rekordów. Źródła pozostają w każdym rekordzie. Diagram architektury: OSM/API instytucji → normalizacja 21 pól i Haversine → migawka FastAPI → eksport/harvester. Import BIP trafia do osobnego podglądu, a nie automatycznie do zbioru ratunkowego.')

    d.start('Wspólny standard danych','Wzorzec XLSX i walidacja')
    d.text('21 pól',.77,1.98,4.1,.9,size=51,bold=True,color=RED)
    d.text('Lokalizacja i dokładne miejsce\nDostęp, godziny i wymóg klucza\nModel oraz stan urządzenia\nDysponent, źródło i data',.78,3.2,4.2,2.1,size=18)
    d.text('Jeden plik XLSX dla organizacji.\nRaport wskazuje pola do poprawy.\nDane wynikowe: CSV i JSON.',.78,5.65,4.3,1.0,size=17,color=SLATE)
    d.evidence(1,'WZORZEC XLSX / 21 PÓL')
    d.notes('Źródło: data_standard/wzorzec_danych_aed.xlsx, backend/schema.py i upload_validation.py. Arkusz ma Schemat_Danych, Szablon_Do_Wypelnienia i Instrukcja_Dla_Dysponenta. Lista dostępności i statusów technicznych jest kontrolowana. Przykłady w szablonie są fikcyjne i oznaczone DEMO. PDF/HTML są wyłącznie wejściem importera; publikowane dane pozostają maszynowe.')

    d.start('Świadek zdarzenia','Prosta ścieżka użytkownika')
    d.text('1',.78,2.03,.45,.45,size=24,bold=True,color=RED);d.text('Ocenia sytuację\nw dwóch pytaniach',1.35,2.02,3.45,.95,size=21,bold=True)
    d.text('2',.78,3.32,.45,.45,size=24,bold=True,color=RED);d.text('Wpisuje miejsce\nlub używa GPS',1.35,3.31,3.45,.95,size=21,bold=True)
    d.text('3',.78,4.61,.45,.45,size=24,bold=True,color=RED);d.text('Wybiera otwarty AED\ni sprawdza opis dojścia',1.35,4.60,3.5,.95,size=21,bold=True)
    d.text('Po urządzenie wysyła inną osobę.\nGdy jest sam, nie przerywa RKO.',.78,6.05,4.3,.7,size=16,color=SLATE)
    d.evidence(2,'MAPA I NAJBLIŻSZE OTWARTE AED')
    d.notes('Źródła: frontend/app.js, rescue-ui.js, drawer.js; backend/rescue.py i availability.py. Strefa Europe/Warsaw, opening_hours, klucz/kod, serwis i zgłoszenia terenowe. Marsz jest szacunkiem: Haversine ×1.25 i 5 km/h. Linia na mapie nie jest trasą po chodnikach. Dostępność nie potwierdza sprawności. Wskazówki dla dorosłych oparte na ERC 2025: https://www.erc.edu/media/wrhj5sye/gl2025-04-bls-e.pdf. Brak reakcji oznacza wezwanie 112 już podczas oceny oddechu. Funkcje dostępności nie są certyfikacją WCAG.')

    d.start('Dysponent urządzenia','Dodawanie i poprawianie informacji')
    d.text('1. Wgrywa plik CSV/XLSX lub BIP\n\n2. Poprawia błędy z raportu\n\n3. Pobiera dane CSV lub JSON',.78,2.03,4.25,2.9,size=18,bold=True)
    d.text('Plakietka z kodem QR prowadzi\ndo karty konkretnego urządzenia.\nŚwiadek może zgłosić jego stan.',.78,5.58,4.3,1.0,size=17,color=SLATE)
    d.evidence(3,'GENERATOR QR LUB WALIDACJA PLIKU')
    d.notes('Źródła: backend/chaos_import.py, features_api.py, feature_store.py. PDF/HTML/CSV/XLSX/JSON/GeoJSON/XML na wejściu, 21 pól na wyjściu. Limity: 5 MiB, 500 rekordów, 20 stron PDF; brak OCR skanów. Opcjonalnie 5 geokodowań adresów. QR powstaje lokalnie przez qrcode i prowadzi do /?aed=ID. Przed drukiem musi wskazywać publiczny adres HTTPS. Zgłoszenia są anonimowe, zapisane w SQLite; nie zastępują kontroli dysponenta. Logo i hasło zachęcają do otwierania danych.')

    d.start('Publikacja i ograniczenia','Gotowość prototypu')
    d.text('CSV · JSON · GeoJSON\nXML harvestera (XSD 1.13)\nAudyt instytucji: 0–100 pkt',.78,2.05,4.3,1.8,size=20,bold=True)
    d.text('Przed wdrożeniem:\n\nPubliczny hosting HTTPS\nWeryfikacja danych u dysponentów\nModeracja zgłoszeń i monitoring\nPełny audyt WCAG i testy urządzeń',.78,4.25,4.35,2.35,size=17,color=SLATE)
    d.evidence(4,'EKSPORT DANYCH I METADANYCH')
    d.text('Zbiór połączony zachowuje ODbL i oznaczenia źródeł.',5.25,6.68,7.35,.35,size=12,color=SLATE)
    d.notes('Źródła: backend/harvester_export.py, danegov_client.py, quality_audit.py. Czytanie JSON:API v1.4: https://api.dane.gov.pl/1.4. Publiczne API nie zapewnia tu zapisu zbioru; payload to paczka robocza, a publikacja wymaga harvestera/panelu dysponenta i publicznych URL. XML zgodny z lokalnym XSD 1.13: https://dane.gov.pl/static/xml/otwarte_dane_latest.xsd. Zbiór wzbogacony OSM zachowuje ODbL; źródła CC BY zachowują atrybucję, bez zmiany całości na CC0. Katalog instytucji ma niepełne pokrycie Polski. Deduplikacja przestrzenna wymaga kontroli w budynkach wielopiętrowych. Nie wykonano badania wpływu na czas ratowania ani pełnego audytu AAA. '+evidence_note)
    d.save()
    return d

if __name__=='__main__':build()
