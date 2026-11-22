"""Jedno źródło SVG; eksport PDF/PNG/JPG i identyczne zasoby strony."""
from io import BytesIO
from pathlib import Path
import hashlib
import json
from PIL import Image
import pypdfium2 as pdfium
from reportlab.graphics import renderPDF
from reportlab.pdfgen import canvas
from svglib.svglib import svg2rlg
from brand_assets import ROOT,WIDTH,HEIGHT,NAVY,RED,WHITE,svg_bytes,write_logo


def main():
    source=write_logo()
    image_pdf=ROOT/'logo_otwarte_aed.pdf'
    drawing=svg2rlg(BytesIO(source.read_bytes()))
    c=canvas.Canvas(str(image_pdf),pagesize=(WIDTH,HEIGHT))
    c.setTitle('Otwarte AED — logotyp');c.setAuthor('Zespół Otwarte AED')
    c.scale(WIDTH/drawing.width,HEIGHT/drawing.height)
    renderPDF.draw(drawing,c,0,0);c.save()
    document=pdfium.PdfDocument(str(image_pdf))
    picture=document[0].render(scale=4,fill_color=(255,255,255,0)).to_pil().convert('RGBA')
    picture.save(ROOT/'logo_otwarte_aed.png')
    white=Image.new('RGB',picture.size,'white');white.paste(picture,mask=picture.getchannel('A'))
    white.save(ROOT/'logo_otwarte_aed.jpg',quality=96,subsampling=0)
    (ROOT/'sygnet_otwarte_aed.svg').write_bytes(svg_bytes(symbol_only=True))
    (ROOT/'logo_otwarte_aed_monochromatyczne.svg').write_bytes(svg_bytes(replacements={RED:NAVY}))
    (ROOT/'logo_otwarte_aed_negatyw.svg').write_bytes(svg_bytes(replacements={RED:WHITE,NAVY:WHITE,WHITE:NAVY}))
    (ROOT/'logo_otwarte_aed_kontrast.svg').write_bytes(svg_bytes(replacements={RED:'#FFED00',NAVY:'#FFED00',WHITE:'#000000'}))
    assets=ROOT.parent/'frontend/assets'
    assets.joinpath(source.name).write_bytes(source.read_bytes())
    assets.joinpath('logo_otwarte_aed_kontrast.svg').write_bytes((ROOT/'logo_otwarte_aed_kontrast.svg').read_bytes())
    assets.joinpath('mark.svg').write_bytes((ROOT/'sygnet_otwarte_aed.svg').read_bytes())
    manifest={'canonical':'branding/logo_otwarte_aed.svg','sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'website':'frontend/assets/logo_otwarte_aed.svg','formats':['svg','png','jpg','pdf'],
        'campaign':'Otwarte AED','slogan':'Dane, które ratują minuty.'}
    (ROOT/'manifest_marki.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False))


if __name__=='__main__':main()
