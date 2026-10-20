import os, re
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, 'test_predictions', 'TEST_SET_REPORT.md')
OUT = os.path.join(BASE, 'test_predictions', 'AI_Department_Spandan_Watch_Analysis.pdf')
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='ReportTitle', parent=styles['Title'], alignment=TA_CENTER, fontSize=18, leading=23, spaceAfter=18, textColor=colors.HexColor('#17365D')))
styles.add(ParagraphStyle(name='H2x', parent=styles['Heading2'], fontSize=13, leading=16, spaceBefore=12, spaceAfter=7, textColor=colors.HexColor('#17365D')))
styles.add(ParagraphStyle(name='Bodyx', parent=styles['BodyText'], fontSize=9.5, leading=14, spaceAfter=7))
styles.add(ParagraphStyle(name='Smallx', parent=styles['BodyText'], fontSize=8, leading=10))
def inline(s):
    s=s.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
    s=re.sub(r'`([^`]+)`',r'<font name="Courier">\1</font>',s)
    return re.sub(r'\*\*([^*]+)\*\*',r'<b>\1</b>',s)
lines=open(SRC,encoding='utf-8').read().splitlines(); story=[]; i=0
while i<len(lines):
    line=lines[i].strip()
    if not line: i+=1; continue
    if line.startswith('# '): story.append(Paragraph(inline(line[2:]),styles['ReportTitle']))
    elif line.startswith('## 4. '): story.append(PageBreak()); story.append(Paragraph(inline(line[3:]),styles['H2x']))
    elif line.startswith('## '): story.append(Paragraph(inline(line[3:]),styles['H2x']))
    elif line.startswith('|') and i+1<len(lines) and lines[i+1].startswith('|---'):
        rows=[]
        while i<len(lines) and lines[i].startswith('|'):
            if not re.match(r'^\|[-: |]+\|$',lines[i]): rows.append([Paragraph(inline(x.strip()),styles['Smallx']) for x in lines[i].strip('|').split('|')])
            i+=1
        widths = [2.35*inch, 4.25*inch] if len(rows[0]) == 2 else [1.1*inch,.55*inch,.55*inch,.55*inch,.55*inch,1.05*inch,1.7*inch]
        t=Table(rows, repeatRows=1, colWidths=widths)
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#D9EAF7')),('GRID',(0,0),(-1,-1),.3,colors.grey),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)])); story += [t,Spacer(1,8)]; continue
    elif line.startswith('- '): story.append(Paragraph('• '+inline(line[2:]),styles['Bodyx']))
    elif re.match(r'^\d+\. ',line): story.append(Paragraph(inline(re.sub(r'^\d+\. ','',line)),styles['Bodyx']))
    else: story.append(Paragraph(inline(line),styles['Bodyx']))
    i+=1
for name,caption in [('physical_state_by_officer.png','Figure 1. Predicted physical state by officer.'),('distraction_by_officer.png','Figure 2. Predicted distraction exposure by officer.'),('overall_state_mix.png','Figure 3. Overall physical-state prediction mix.')]:
    path=os.path.join(BASE,'test_predictions',name)
    if os.path.exists(path): story += [Spacer(1,8),Image(path,width=6.6*inch,height=3.7*inch),Paragraph(caption,styles['Smallx'])]
doc=SimpleDocTemplate(OUT,pagesize=A4,rightMargin=.55*inch,leftMargin=.55*inch,topMargin=.55*inch,bottomMargin=.55*inch,title='AI Department Spandan Watch Analysis')
doc.build(story)
print(OUT)
