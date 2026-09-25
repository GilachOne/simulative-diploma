"""Export executed notebooks as portable reports without code cells."""
import base64
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

import nbformat
from nbconvert.filters import markdown2html
from bs4 import BeautifulSoup
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
import matplotlib

ROOT=Path(__file__).resolve().parent
fonts=Path(matplotlib.get_data_path())/'fonts/ttf'
for name,file in [('DejaVu','DejaVuSans.ttf'),('DejaVu-Bold','DejaVuSans-Bold.ttf')]:
    pdfmetrics.registerFont(TTFont(name,str(fonts/file)))
pdfmetrics.registerFontFamily('DejaVu',normal='DejaVu',bold='DejaVu-Bold',italic='DejaVu',boldItalic='DejaVu-Bold')
styles=getSampleStyleSheet()
for style in styles.byName.values(): style.fontName='DejaVu'
for name in ['Heading1','Heading2','Heading3','Heading4']: styles[name].keepWithNext=True
styles['BodyText'].fontSize=9
styles['BodyText'].leading=13
styles['BodyText'].spaceAfter=7
styles.add(ParagraphStyle(name='Cell',fontName='DejaVu',fontSize=6.5,leading=8.5))
styles.add(ParagraphStyle(name='Output',fontName='DejaVu',fontSize=8,leading=11,spaceAfter=6))
W,H=landscape(A4)
WIDTH=W-72

def html_blocks(html):
    soup=BeautifulSoup(html,'html.parser')
    for anchor in soup.select('a.anchor-link'): anchor.decompose()
    result=[]
    for tag in soup.find_all(['h1','h2','h3','h4','p','table','pre','li']):
        if tag.find_parent(['table','pre','li']): continue
        if tag.name=='table':
            rows=[[c.get_text(' ',strip=True) for c in row.find_all(['th','td'])] for row in tag.find_all('tr')]
            if not rows: continue
            n=max(map(len,rows))
            data=[[Paragraph(escape(c),styles['Cell']) for c in row+['']*(n-len(row))] for row in rows]
            table=Table(data,colWidths=[WIDTH/n]*n,repeatRows=1,hAlign='LEFT')
            table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e6f2f1')),
                ('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.25,colors.HexColor('#cdd7da')),
                ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
            result.extend([table,Spacer(1,10)])
        else:
            text=escape(tag.get_text(' ',strip=True))
            if not text: continue
            style='Heading'+tag.name[1] if tag.name.startswith('h') else 'BodyText'
            result.append(Paragraph(('• ' if tag.name=='li' else '')+text,styles[style]))
    return result

def footer(canvas,doc):
    canvas.setFont('DejaVu',8)
    canvas.setFillColor(colors.HexColor('#65777c'))
    canvas.drawString(36,21,'Аналитика маркетплейса | учебные данные API | 2023')
    canvas.drawRightString(W-36,21,str(doc.page))

def main():
    for name in ['01_assortment','02_clients']:
        nb=nbformat.read(ROOT/'reports'/f'{name}.ipynb',as_version=4)
        story=[]
        for cell in nb.cells:
            if cell.cell_type=='markdown':
                story.extend(html_blocks(markdown2html(cell.source)))
            elif cell.cell_type=='code':
                for out in cell.get('outputs',[]):
                    data=out.get('data',{})
                    if 'image/png' in data:
                        image=Image(BytesIO(base64.b64decode(data['image/png'])))
                        scale=min(WIDTH/image.imageWidth,(H-115)/image.imageHeight)
                        image.drawWidth=image.imageWidth*scale
                        image.drawHeight=image.imageHeight*scale
                        story.extend([image,Spacer(1,10)])
                    elif 'text/html' in data: story.extend(html_blocks(data['text/html']))
                    elif 'text/markdown' in data: story.extend(html_blocks(markdown2html(data['text/markdown'])))
                    elif out.output_type=='stream' and out.name=='stdout':
                        story.append(Paragraph(escape(out.text).replace('\n','<br/>'),styles['Output']))
        target=ROOT/'reports'/f'{name}.pdf'
        SimpleDocTemplate(str(target),pagesize=(W,H),rightMargin=36,leftMargin=36,
            topMargin=32,bottomMargin=40,title=nb.cells[0].source.splitlines()[0].lstrip('# '),author='GilachOne').build(story,onFirstPage=footer,onLaterPages=footer)
        print(target.name,'created')

if __name__=='__main__': main()
