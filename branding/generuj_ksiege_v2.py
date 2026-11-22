"""Minimalistyczna księga znaku: wektorowy SVG, sześć stron A4, osadzone fonty."""
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from pypdf import PdfReader
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.graphics import renderPDF
from svglib.svglib import svg2rlg
from brand_assets import ROOT,NAME,SLOGAN,RED,NAVY,WHITE,LIGHT,SLATE,CONCEPT,font_path,rgb,cmyk,svg_bytes

W,H=A4;M=50;CW=W-2*M;OUT=ROOT/'ksiega_znaku.pdf'
GRAY='#DCE2EB'

def setup():
    pdfmetrics.registerFont(TTFont('Brand',str(font_path())))
    pdfmetrics.registerFont(TTFont('BrandB',str(font_path(True))))

def text(c,value,x,top,size=11,color=NAVY,bold=False):
    c.setFont('BrandB' if bold else 'Brand',size);c.setFillColor(colors.HexColor(color));c.drawString(x,H-top,value)

def para(c,value,x,top,width=CW,size=11,leading=17,color=NAVY):
    p=Paragraph(value,ParagraphStyle('brand',fontName='Brand',fontSize=size,leading=leading,textColor=colors.HexColor(color)))
    _,height=p.wrap(width,H);p.drawOn(c,x,H-top-height);return height

def box(c,x,top,w,h,color=LIGHT,stroke=None):
    c.setFillColor(colors.HexColor(color));c.setStrokeColor(colors.HexColor(stroke or color));c.setLineWidth(.7);c.rect(x,H-top-h,w,h,fill=1,stroke=bool(stroke))

def line(c,x1,top1,x2,top2,color=GRAY,width=.7):
    c.setStrokeColor(colors.HexColor(color));c.setLineWidth(width);c.line(x1,H-top1,x2,H-top2)

def logo(c,x,top,width,*,data=None,height=None):
    drawing=svg2rlg(BytesIO(data or (ROOT/'logo_otwarte_aed.svg').read_bytes()))
    h=height or width*drawing.height/drawing.width
    c.saveState();c.translate(x,H-top-h);c.scale(width/drawing.width,h/drawing.height);renderPDF.draw(drawing,c,0,0);c.restoreState()
    return h

def head(c,title,page,section):
    text(c,'OTWARTE AED',M,37,9,bold=True);text(c,section.upper(),W-210,37,8.5,color=SLATE)
    line(c,M,54,W-M,54);text(c,title,M,103,30,bold=True)
    text(c,'Księga znaku · wersja 2.0',M,H-28,8.5,color=SLATE);text(c,f'{page:02d} / 06',W-M-38,H-28,8.5,color=SLATE)

def cover(c):
    text(c,'IDENTYFIKACJA WIZUALNA',M,70,10,color=SLATE,bold=True)
    text(c,'Księga znaku',M,142,43,bold=True)
    line(c,M,185,M+45,185,RED,3)
    logo(c,M,286,CW)
    para(c,'Otwarta informacja o defibrylatorach.<br/>Spójny znak kampanii zachęcającej<br/>do dzielenia się danymi.',M,570,size=17,leading=25)
    line(c,M,738,W-M,738)
    text(c,'OTWARTE AED / MISJA-AED',M,766,9,bold=True)
    text(c,'21.11.2026  ·  WERSJA 2.0',W-217,766,8.5,color=SLATE)
    c.showPage()

def concept(c):
    head(c,'Znak i jego znaczenie',2,'Koncepcja')
    assert len(CONCEPT)==4 and all(sentence.endswith('.') for sentence in CONCEPT)
    para(c,' '.join(CONCEPT),M,143,size=11.5,leading=18)
    logo(c,M+20,324,CW-40)
    text(c,'Wersja podstawowa z hasłem',M,485,10,color=SLATE)
    logo(c,M,553,230,data=svg_bytes(replacements={RED:NAVY}))
    box(c,315,532,230,110,NAVY)
    logo(c,325,550,210,data=svg_bytes(replacements={RED:WHITE,NAVY:WHITE,WHITE:NAVY}))
    text(c,'Wersja jednobarwna',M,674,10,color=SLATE)
    text(c,'Wersja na granatowym tle',315,674,10,color=SLATE)
    para(c,'Kształt, proporcje i układ liter pozostają stałe. Wersja czarno-żółta jest zarezerwowana dla trybu wysokiego kontrastu w aplikacji.',M,714,size=10,leading=15,color=SLATE)
    c.showPage()

def palette(c):
    head(c,'Kolory i typografia',3,'Paleta')
    for x,name,value in [(M,'Czerwień ratownicza',RED),(M+257,'Granat zaufania',NAVY)]:
        box(c,x,151,238,157,value)
        text(c,name,x+17,177,12,color=WHITE,bold=True)
        text(c,value,x+17,223,27,color=WHITE,bold=True)
        text(c,'RGB  '+' / '.join(map(str,rgb(value))),x+17,259,10,color=WHITE)
        text(c,'CMYK  '+' / '.join(f'{v:g}' for v in cmyk(value)),x+17,285,10,color=WHITE)
    for y,name,value in [(349,'Biel',WHITE),(414,'Jasne tło',LIGHT),(479,'Szaroniebieski',SLATE)]:
        box(c,M,y-19,35,35,value,GRAY)
        text(c,name,M+50,y-3,11,bold=True);text(c,value,M+50,y+15,10,color=SLATE)
        text(c,'RGB  '+' / '.join(map(str,rgb(value))),M+225,y-3,9.7,color=SLATE)
        text(c,'CMYK  '+' / '.join(f'{v:g}' for v in cmyk(value)),M+225,y+15,9.7,color=SLATE)
    line(c,M,536,W-M,536)
    text(c,'Aa',M,614,53,bold=True)
    text(c,'Arial Regular / Arial Bold',M+123,571,15,bold=True)
    para(c,'Prosty krój bezszeryfowy do dokumentów i materiałów kampanii. W plikach SVG logotypu litery są zamienione na krzywe, więc nie wymagają instalacji fontu.',M+123,592,width=360,size=10.5,leading=17)
    para(c,'CMYK podano w procentach jako matematyczne przeliczenie sRGB, bez profilu ICC. W druku należy dobrać profil i wykonać próbę barwną.',M,706,size=10,leading=15,color=SLATE)
    c.showPage()

def protection(c):
    head(c,'Pole ochronne i skala',4,'Konstrukcja')
    para(c,'Moduł <b>u = H / 5</b>, gdzie H to wysokość osi konturu pinezki. W modelu SVG H = 160 jednostek, a u = 32. Wokół całego pola znaku pozostaw co najmniej jeden moduł u wolnej przestrzeni.',M,143,size=11,leading=18)
    x,top,width=111,292,373;scale=width/700;unit=32*scale;height=200*scale
    c.saveState();c.setDash(4,3);c.setStrokeColor(colors.HexColor(SLATE));c.setLineWidth(.8)
    c.rect(x-unit,H-top-height-unit,width+2*unit,height+2*unit,fill=0,stroke=1);c.restoreState()
    box(c,x-unit,top-unit,unit,unit,RED)
    logo(c,x,top,width)
    text(c,'u',x-unit-13,top-unit+12,12,color=RED,bold=True)
    text(c,'u',x+width+unit+7,top+height/2,12,color=RED,bold=True)
    line(c,78,top+10*scale,78,top+170*scale,SLATE)
    line(c,73,top+10*scale,84,top+10*scale,SLATE)
    line(c,73,top+170*scale,84,top+170*scale,SLATE)
    text(c,'H',59,top+95*scale,12,bold=True)
    text(c,'Minimalna wielkość',M,494,19,bold=True)
    logo(c,M,538,70*mm)
    text(c,'Znak z hasłem',300,558,12,bold=True);text(c,'280 px na ekranie',300,581,12);text(c,'70 mm szerokości w druku',300,604,12)
    logo(c,M+2,660,8*mm,data=svg_bytes(symbol_only=True))
    text(c,'Sam sygnet',110,669,12,bold=True);text(c,'32 px / 8 mm szerokości',300,686,12)
    para(c,'Nie zmniejszaj znaku kosztem czytelności hasła. W małych ikonach używaj zatwierdzonego sygnetu, bez dopisywania tekstu.',M,736,size=10,leading=15,color=SLATE)
    c.showPage()

def forbidden(c):
    head(c,'Niedozwolone użycie',5,'Ochrona znaku')
    para(c,'Korzystaj z dostarczonych wariantów. Nie zmieniaj samodzielnie proporcji, kolorów ani położenia elementów.',M,143,size=11,leading=18)
    cells=[(M,221,'01  Deformacja'),(310,221,'02  Obrót'),(M,478,'03  Inne kolory'),(310,478,'04  Niski kontrast')]
    for x,y,label in cells:
        line(c,x,y-15,x+235,y-15);text(c,label,x,y+155,13,bold=True)
        text(c,'NIE',x,y+180,9,color=RED,bold=True)
    logo(c,M,270,235,height=30)
    c.saveState();c.translate(310,H-343);c.rotate(14)
    drawing=svg2rlg(BytesIO((ROOT/'logo_otwarte_aed.svg').read_bytes()));c.scale(222/drawing.width,222/drawing.width);renderPDF.draw(drawing,c,0,0);c.restoreState()
    logo(c,M,522,235,data=svg_bytes(replacements={RED:'#8F3FC4',NAVY:'#368466'}))
    box(c,310,500,235,108,LIGHT)
    logo(c,315,522,225,data=svg_bytes(replacements={RED:'#C7CDD6',NAVY:'#CAD0D8'}))
    para(c,'Nie umieszczaj znaku na chaotycznych zdjęciach ani na tle, które zlewa się z jego konturem. W razie potrzeby zastosuj białe pole ochronne.',M,737,size=10,leading=15,color=SLATE)
    c.showPage()

def files(c):
    head(c,'Jeden znak, wiele zastosowań',6,'Pliki')
    para(c,'Strona internetowa i dokumenty korzystają z tego samego pliku źródłowego SVG. Sygnet służy do małych ikon; pełny znak z hasłem jest wariantem podstawowym.',M,143,size=11,leading=18)
    box(c,M,235,CW,142,WHITE,GRAY)
    logo(c,M+18,254,365)
    logo(c,M+425,260,42,data=svg_bytes(symbol_only=True))
    text(c,'Wersja podstawowa',M+18,405,10,color=SLATE);text(c,'Sygnet',M+420,405,10,color=SLATE)
    rows=[('SVG','Edycja, skalowanie, strona','Wektor'),('PNG','Ekran, przezroczyste tło','2800 × 800 px'),('JPG','Białe tło','2800 × 800 px'),('PDF','Druk i skład','Wektor')]
    for i,(fmt,use,quality) in enumerate(rows):
        y=469+i*48;line(c,M,y-20,W-M,y-20);text(c,fmt,M,y,13,bold=True);text(c,use,M+75,y,11);text(c,quality,M+360,y,10,color=SLATE)
    para(c,'Nie odtwarzaj logotypu ze zrzutu ekranu. Do publikacji bierz pliki z pakietu marki i zachowaj ich proporcje.',M,695,size=11,leading=18)
    text(c,'Plik źródłowy: branding/logo_otwarte_aed.svg',M,761,9,color=SLATE)
    c.showPage()

def main():
    setup();c=canvas.Canvas(str(OUT),pagesize=A4,pageCompression=1)
    c.setTitle('Otwarte AED — księga znaku');c.setAuthor('Zespół Otwarte AED');c.setSubject(SLOGAN)
    for page in (cover,concept,palette,protection,forbidden,files):page(c)
    c.save();reader=PdfReader(OUT)
    assert len(reader.pages)==6 and OUT.stat().st_size>0
    assert all((page.extract_text() or '').strip() for page in reader.pages)
    print(f'Księga: {OUT.name}, {len(reader.pages)} stron, {OUT.stat().st_size} bajtów; koncepcja: 4 zdania.')

if __name__=='__main__':main()
