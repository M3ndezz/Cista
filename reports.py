# RELATÓRIOS: monta os PDFs da unidade, de uma área e da visão geral usando os dados salvos.
"""Designed PDFs for individual units and concise area summaries."""
import html
# ReportLab monta documentos em memória: textos, tabelas, imagens e páginas.
# Este módulo apenas lê os dados recebidos; não altera as fichas salvas.
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, Image, KeepTogether,
                                LongTable, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle)

import floors
from locations import location
from contacts import DEFAULT_COORDINATOR

NAVY=colors.HexColor('#173648')
# Paleta compartilhada por todos os PDFs. Cada código #RRGGBB representa uma cor.
INK=colors.HexColor('#18384A')
MUTED=colors.HexColor('#647B88')
LINE=colors.HexColor('#DCE6EA')
PALE=colors.HexColor('#F2F6F8')
TEAL=colors.HexColor('#087C82')
RED=colors.HexColor('#C71843')
WHITE=colors.white

_assets=Path(__file__).resolve().parent/'assets'
# Registra as fontes incluídas no projeto para desenhar acentos e manter a aparência entre computadores.
pdfmetrics.registerFont(TTFont('Cista',str(_assets/'DejaVuSans.ttf')))
pdfmetrics.registerFont(TTFont('Cista-Bold',str(_assets/'DejaVuSans-Bold.ttf')))
pdfmetrics.registerFontFamily('Cista',normal='Cista',bold='Cista-Bold')

def style(size=9,leading=None,color=INK,bold=False,space=0,align=TA_LEFT):
    # Define como um texto será desenhado: tamanho, espaçamento, cor, negrito e alinhamento.
    return ParagraphStyle('cista',fontName='Cista-Bold' if bold else 'Cista',
        fontSize=size,leading=leading or size*1.45,textColor=color,
        spaceAfter=space,alignment=align,allowWidows=0,allowOrphans=0)

def para(value,*,size=9,color=INK,bold=False,leading=None,align=TA_LEFT):
    # Transforma um valor em parágrafo do PDF e protege caracteres interpretados como marcação.
    return Paragraph(html.escape(str(value if value is not None else '—')),
                     style(size,leading,color,bold,align=align))

def shown(value):
    # Mostra um traço quando o valor não foi informado, preservando o número 0 quando existente.
    return '—' if value is None or value=='' else str(value)

def sum_known(rows,key):
    # Soma apenas números informados. Se todos estiverem vazios, mantém ausência em vez de inventar zero.
    values=[r[key] for r in rows if r[key] is not None]
    return sum(values) if values else None

def section(title,subtitle=None):
    # Devolve os elementos de um título de seção com seus espaços e subtítulo opcional.
    items=[Spacer(1,15),para(title,size=12,bold=True),Spacer(1,4)]
    if subtitle:items.extend([para(subtitle,size=7.5,color=MUTED),Spacer(1,8)])
    else:items.append(Spacer(1,8))
    return items

def field(label,value,width=244):
    # Monta um campo visual do relatório: rótulo pequeno acima e conteúdo logo abaixo.
    return [para(label.upper(),size=7,color=MUTED,bold=True),Spacer(1,4),
            para(shown(value),size=8.4)]

def pairs(items):
    # Distribui campos em duas colunas, completando a última posição se a lista tiver número ímpar.
    data=[]
    for i in range(0,len(items),2):
        left=items[i];right=items[i+1] if i+1<len(items) else ('','')
        data.append([field(*left),field(*right) if right[0] else ''])
    t=Table(data,colWidths=[256,256],hAlign='LEFT')
    # As coordenadas das tabelas são (coluna, linha); -1 indica a última coluna ou linha.
    # Padding é a distância entre o conteúdo e a borda da célula.
    t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,-1),PALE),
        ('LEFTPADDING',(0,0),(-1,-1),11),('RIGHTPADDING',(0,0),(-1,-1),10),
        ('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10),
        ('INNERGRID',(0,0),(-1,-1),6,WHITE)]))
    return t

def metric(value,label,accent=TEAL):
    # Desenha um indicador com número em destaque, legenda e faixa superior colorida.
    t=Table([[para(shown(value),size=11 if len(shown(value))>9 else 18,bold=True,color=accent)],
             [para(label,size=7.1,color=MUTED)]],colWidths=[123])
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),
        ('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),5),
        ('TOPPADDING',(0,0),(-1,0),10),('BOTTOMPADDING',(0,0),(-1,0),2),
        ('TOPPADDING',(0,1),(-1,1),0),('BOTTOMPADDING',(0,1),(-1,1),11),
        ('LINEABOVE',(0,0),(-1,0),3,accent)]))
    return t

def page(canvas,doc,footer='FICHA TÁTICA DA UNIDADE  ·  Uso interno'):
    # Chamado em cada página para repetir faixa superior, identidade e rodapé com numeração.
    # canvas é a superfície de desenho; medidas do PDF usam pontos, não pixels do navegador.
    w,h=doc.pagesize
    # Guarda e restaura o estado do desenho para estas cores e fontes não afetarem outros elementos.
    canvas.saveState()
    canvas.setFillColor(NAVY);canvas.rect(0,h-62,w,62,fill=1,stroke=0)
    canvas.setFillColor(RED);canvas.rect(0,h-66,w,4,fill=1,stroke=0)
    canvas.setFont('Cista-Bold',17);canvas.setFillColor(WHITE)
    canvas.drawString(42,h-37,'CISTA')
    canvas.setFont('Cista',7);canvas.setFillColor(colors.HexColor('#B8D1D9'))
    canvas.drawRightString(w-42,h-35,'PROTEÇÃO DE POLOS ADMINISTRATIVOS')
    canvas.setStrokeColor(LINE);canvas.line(42,43,w-42,43)
    canvas.setFont('Cista',7);canvas.setFillColor(MUTED)
    canvas.drawString(42,29,footer)
    canvas.drawRightString(w-42,29,f'Página {doc.page}')
    canvas.restoreState()

def report_date(value):
    # Converte a data técnica do banco para dia/mês/ano e horário no fuso UTC-3 usado nos relatórios.
    # Se faltar data, explica a ausência; se não conseguir interpretar, preserva o texto recebido.
    if not value:return 'Sem atualização'
    try:
        instant=datetime.fromisoformat(value)
        if instant.tzinfo:
            instant=instant.astimezone(timezone(timedelta(hours=-3)))
        return instant.strftime('%d/%m/%Y às %H:%M')
    except ValueError:
        return str(value)

def summary_table(units,group_for,w,empty='Nenhuma unidade cadastrada.'):
    """Reusable, paginated building table for area and overview PDFs."""
    # Define as seis colunas usadas nos relatórios resumidos da área e da visão geral.
    # group_for é uma função recebida para descobrir o nome da área de cada prédio.
    widths=[183,135,111,64,83,w-84-183-135-111-64-83]
    headers=['Nome do prédio','Categoria','Focal do prédio','Ramal','Nível de risco','Situação / data']
    data=[[para(label,size=7,color=WHITE,bold=True) for label in headers]]
    # Cada prédio vira uma linha com seu focal, ramal, risco e situação/data.
    for u in units:
        details=json.loads(u['details'] or '{}')
        status='Atualizada' if u['updated_at'] else 'Pendente'
        status_color=TEAL if u['updated_at'] else colors.HexColor('#986021')
        data.append([
            para(u['name'],size=7.7,bold=True),
            para(group_for(u),size=7.3),
            para(shown(details.get('focal')),size=7.3),
            para(shown(details.get('extension')),size=7.3),
            para(details.get('risk_level') or 'Não avaliado',size=7.3),
            [para(status,size=7.3,bold=True,color=status_color),
             para(report_date(u['updated_at']),size=6.6,color=MUTED)]])
    if not units:
        data.append([para(empty,size=8,color=MUTED),'','','','',''])
    # LongTable continua em outras páginas; repeatRows=1 repete o cabeçalho para facilitar a leitura.
    table=LongTable(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[WHITE,PALE]),
        ('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),7),
        ('TOPPADDING',(0,0),(-1,0),9),('BOTTOMPADDING',(0,0),(-1,0),9),
        ('TOPPADDING',(0,1),(-1,-1),5),('BOTTOMPADDING',(0,1),(-1,-1),5),
        ('LINEBELOW',(0,1),(-1,-1),.35,LINE)]))
    return table

def group_pdf(units,group):
    """Summary table for one area; repeat the heading on continuation pages."""
    # Usa papel A4 deitado. BytesIO é um arquivo temporário em memória, enviado depois para download.
    w,h=landscape(A4)
    output=io.BytesIO()
    doc=BaseDocTemplate(output,pagesize=(w,h),leftMargin=42,rightMargin=42,
        topMargin=84,bottomMargin=57,title=f'CISTA — Relatório da área {group}',author='CISTA')
    # Frame delimita onde o conteúdo pode aparecer, deixando espaço para o cabeçalho e rodapé.
    frame=Frame(42,57,w-84,h-141,leftPadding=0,rightPadding=0,
                topPadding=0,bottomPadding=0)
    doc.addPageTemplates(PageTemplate(id='area',frames=frame,
        onPage=lambda canvas,doc:page(canvas,doc,'RELATÓRIO DA ÁREA DE ATUAÇÃO  ·  Uso interno')))
    updated=sum(bool(u['updated_at']) for u in units)
    pending=len(units)-updated
    completion=round(100*updated/len(units)) if units else 0
    stamp=datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y às %H:%M')
    story=[para('ÁREA DE ATUAÇÃO',size=7.5,color=TEAL,bold=True),Spacer(1,7),
        para(group,size=19,bold=True),Spacer(1,4),
        para(f'Resumo das unidades  ·  Emitido em {stamp}',size=8,color=MUTED),Spacer(1,15)]
    def card(value,label):
        # Pequeno componente local: monta um dos quatro indicadores do relatório desta área.
        t=Table([[para(value,size=17,color=TEAL,bold=True)],
                 [para(label,size=7,color=MUTED)]],colWidths=[180])
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),
            ('LINEABOVE',(0,0),(-1,0),3,TEAL),
            ('LEFTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,0),9),
            ('BOTTOMPADDING',(0,0),(-1,0),0),('TOPPADDING',(0,1),(-1,1),0),
            ('BOTTOMPADDING',(0,1),(-1,1),8)]))
        return t
    summary=Table([[card(len(units),'Unidades da área'),card(updated,'Atualizadas'),
                    card(pending,'Pendentes'),card(f'{completion}%','Levantamento concluído')]],
                  colWidths=[(w-84)/4]*4,hAlign='LEFT')
    summary.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),9)]))
    story.extend([summary,Spacer(1,17),para('Quadro consolidado',size=11,bold=True),Spacer(1,7)])
    # story é a sequência de elementos do documento, na mesma ordem em que devem ser impressos.
    story.append(summary_table(units,lambda _:group,w,'Nenhum prédio cadastrado nesta área.'))
    doc.build(story)
    return output.getvalue()

def overview_pdf(units,groups):
    """Overall status and concise inventory for all three areas."""
    # Cria o consolidado geral deitado com indicadores, resumo por área e tabela de todos os prédios.
    w,h=landscape(A4)
    output=io.BytesIO()
    doc=BaseDocTemplate(output,pagesize=(w,h),leftMargin=42,rightMargin=42,
        topMargin=84,bottomMargin=57,title='CISTA — Inventário tático consolidado',author='CISTA')
    doc.addPageTemplates(PageTemplate(id='overview',
        frames=Frame(42,57,w-84,h-141,leftPadding=0,rightPadding=0,
                     topPadding=0,bottomPadding=0),
        onPage=lambda canvas,doc:page(canvas,doc,'RELATÓRIO CONSOLIDADO  ·  Uso interno')))
    total=len(units)
    updated=sum(bool(u['updated_at']) for u in units)
    completion=round(100*updated/total) if total else 0
    stamp=datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y às %H:%M')
    story=[para('VISÃO GERAL · INVENTÁRIO TÁTICO',size=7.5,color=TEAL,bold=True),
        Spacer(1,7),para('Panorama das unidades',size=19,bold=True),Spacer(1,4),
        para(f'Relatório consolidado  ·  Emitido em {stamp}',size=8,color=MUTED),Spacer(1,15)]
    cards=[]
    # Monta os quatro números do início do relatório com o mesmo padrão visual.
    for value,label in [(total,'Unidades cadastradas'),(updated,'Fichas atualizadas'),
                        (total-updated,'Pendentes'),(f'{completion}%','Levantamento concluído')]:
        t=Table([[para(value,size=17,color=TEAL,bold=True)],
                 [para(label,size=7,color=MUTED)]],colWidths=[180])
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),
            ('LINEABOVE',(0,0),(-1,0),3,TEAL),('LEFTPADDING',(0,0),(-1,-1),10),
            ('TOPPADDING',(0,0),(-1,0),9),('BOTTOMPADDING',(0,0),(-1,0),0),
            ('TOPPADDING',(0,1),(-1,1),0),('BOTTOMPADDING',(0,1),(-1,1),8)]))
        cards.append(t)
    bar=Table([cards],colWidths=[(w-84)/4]*4,hAlign='LEFT')
    bar.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),9)]))
    story.extend([bar,Spacer(1,16),para('Andamento por área',size=11,bold=True),Spacer(1,7)])
    area_data=[[para(label,size=7,color=WHITE,bold=True) for label in
                ('Área de atuação','Unidades','Atualizadas','Pendentes','Concluído')]]
    # Agrupa as unidades por área e calcula atualizadas, pendentes e percentual de avanço.
    for key,title in groups.items():
        selected=[u for u in units if u['group_key']==key]
        done=sum(bool(u['updated_at']) for u in selected)
        pct=round(100*done/len(selected)) if selected else 0
        area_data.append([para(title,size=7.7,bold=True),para(len(selected),size=7.7),
            para(done,size=7.7),para(len(selected)-done,size=7.7),
            para(f'{pct}%',size=7.7,bold=True,color=TEAL)])
    area=Table(area_data,colWidths=[318,95,105,100,w-84-618],hAlign='LEFT')
    area.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[WHITE,PALE]),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),7),
        ('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),
        ('LINEBELOW',(0,1),(-1,-1),.35,LINE)]))
    story.extend([area,Spacer(1,17),
        para('Quadro consolidado de prédios',size=11,bold=True),Spacer(1,4),
        para('Situação e data da última atualização de cada ficha.',size=7.5,color=MUTED),Spacer(1,7)])
    # Ordena primeiro pela área e depois pelo nome do prédio antes de montar a tabela final.
    order={key:i for i,key in enumerate(groups)}
    sorted_units=sorted(units,key=lambda u:(order.get(u['group_key'],999),u['name'].casefold(),u['id']))
    story.append(summary_table(sorted_units,lambda u:groups.get(u['group_key'],'Unidade'),w))
    doc.build(story)
    return output.getvalue()

def floor_card(f):
    # Prepara o detalhe de um andar: departamentos, posições, postos, equipamentos, focais e FM.
    title=f['label']+('  ·  dados a distribuir por andar' if f['is_unassigned'] else '')
    shifts='; '.join(f"{s['role']}: {s['quantity']} — {s['custom'] if s['schedule']=='Outra' else s['schedule']}" for s in f['staffing']) or 'Não informado'
    row=[
        ('Departamentos',', '.join(f['departments']) or 'Não informado'),
        ('Posições de trabalho',shown(f['workstations'])),
        ('Postos e escalas',shifts),
        ('Câmeras · local / remoto',f"{shown(f['camera_local'])} / {shown(f['camera_remote'])}"),
        ('Acesso · crachá / facial / catracas',f"{shown(f['badge_readers'])} / {shown(f['face_readers'])} / {shown(f['turnstiles'])}"),
        ('Alarmes',shown(f['alarms']))]
    data=[[para(title,size=10,bold=True), '']]
    data.extend([[para(k,size=7.5,color=MUTED),para(v,size=8)] for k,v in row])
    # Cada contato ganha sua própria linha; assim a lista pode continuar na página seguinte.
    for department in f['departments']:
        contacts=f.get('department_contacts',{}).get(department,[])
        for person in contacts:
            data.append([para(f'Focal administrativo · {department}',size=7.5,color=MUTED),
                         para(f"{person['name']} - {person['contact']}",size=8)])
    for person in f.get('fm_contacts',[]):
        data.append([para('Identificação de FM',size=7.5,color=MUTED),
                     para(f"{person['name']} - {person['contact']}",size=8)])
    if f['notes']:data.append([para('Observações',size=7.5,color=MUTED),para(f['notes'],size=8)])
    # Repete o nome do andar quando a tabela continua, sem obrigar todos os contatos a caber numa página.
    t=LongTable(data,colWidths=[178,334],hAlign='LEFT',repeatRows=1,splitInRow=1)
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),
        ('SPAN',(0,0),(-1,0)),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E2EFF0')),
        ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),11),
        ('RIGHTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),6),
        ('BOTTOMPADDING',(0,0),(-1,-1),6),('LINEBELOW',(0,0),(-1,-2),.4,LINE)]))
    return [t,Spacer(1,11)]

def unit_pdf(con,unit,group):
    # Relatório completo de um prédio, em A4 em pé. Busca também andares e fotos no banco.
    details=json.loads(unit['details'] or '{}')
    rows=floors.load(con,unit['id'])
    # O agrupamento de dados antigos "A distribuir por andar" não conta como andar identificado.
    named=[f for f in rows if not f['is_unassigned']]
    posts=sum(s['quantity'] for f in rows for s in f['staffing']) if any(f['staffing'] for f in rows) else None
    local=sum_known(rows,'camera_local');remote=sum_known(rows,'camera_remote')
    access=[sum_known(rows,k) for k in ('badge_readers','face_readers','turnstiles')]
    assess=details.get('risk_level') or 'Não avaliado'
    risk_colors={'Baixo':TEAL,'Médio':colors.HexColor('#A97512'),
                 'Alto':RED,'Crítico':RED}
    risk_color=risk_colors.get(assess,MUTED)
    output=io.BytesIO()
    doc=BaseDocTemplate(output,pagesize=A4,leftMargin=42,rightMargin=41,
        topMargin=84,bottomMargin=57,title=f"CISTA — {unit['name']}",author='CISTA')
    frame=Frame(42,57,A4[0]-83,A4[1]-141,leftPadding=0,rightPadding=0,
                topPadding=0,bottomPadding=0)
    doc.addPageTemplates(PageTemplate(id='unit',frames=frame,onPage=page))
    address=location(unit) or 'Localização não informada'
    stamp=datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y às %H:%M')
    story=[para(group.upper(),size=7.5,color=TEAL,bold=True),Spacer(1,8),
        para(unit['name'],size=20,leading=25,bold=True),Spacer(1,5),
        para(address,size=8.5,color=MUTED),Spacer(1,8),
        para(f"CÓDIGO {unit['code']}  ·  EMITIDO EM {stamp}",size=7,color=MUTED),
        Spacer(1,18)]
    # Primeiro vêm o título e os quatro indicadores; em seguida, dados, risco e totais de equipamentos.
    kpis=[metric(len(named) if rows else None,'Andares cadastrados'),
          metric(sum_known(rows,'workstations'),'Posições de trabalho'),
          metric(posts,'Profissionais nos postos'),
          metric(assess,'Nível de risco',risk_color)]
    bar=Table([kpis],colWidths=[128]*4,hAlign='LEFT')
    bar.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),5)]))
    story.extend([bar,*section('Dados da unidade'),pairs([
        ('Andares informados',unit['floor']),('CEP',unit['zip']),
        ('Empresa de vigilância',unit['security_company']),('Focal do prédio',details.get('focal')),
        ('Nome e telefone do coordenador',details.get('coordinator_phone',DEFAULT_COORDINATOR)),
        ('Focal Patrimônio',details.get('property_contact')),
        ('Ramal',details.get('extension'))]),
        *section('Avaliação de risco')])
    risk=Table([[para(assess.upper(),size=11,bold=True,color=risk_color),
                 para(details.get('risk_note') or 'Nenhuma observação registrada.',size=8)]],
               colWidths=[122,390],hAlign='LEFT')
    risk.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),
        ('LINEBEFORE',(0,0),(0,0),4,risk_color),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('LEFTPADDING',(0,0),(-1,-1),12),('RIGHTPADDING',(0,0),(-1,-1),12),
        ('TOPPADDING',(0,0),(-1,-1),13),('BOTTOMPADDING',(0,0),(-1,-1),13)]))
    story.extend([risk,*section('Cobertura e acesso','Soma dos valores informados por andar; “—” indica dado não informado.'),
        pairs([('Câmeras · monitoramento local',local),('Câmeras · monitoramento remoto',remote),
               ('Leitoras de crachá',access[0]),('Leitores faciais',access[1]),
               ('Catracas',access[2]),
               ('Alarmes',sum_known(rows,'alarms'))])])
    # Acrescenta as tabelas detalhadas dos andares e a última atualização registrada da ficha.
    heading=section('Inventário por andar',f'{len(rows)} registro(s) de andar na ficha.')
    if not rows:story.extend(heading+[para('Ainda não há andares cadastrados.',size=8,color=MUTED)])
    else:
        story.extend(heading)
        for f in rows:story.extend(floor_card(f))
    updated=unit['updated_at'] or 'Pendente'
    story.extend([Spacer(1,5),para(f'Última atualização da ficha: {updated}',size=7,color=MUTED)])
    photos=list(con.execute('SELECT photo_type,image,width,height FROM unit_photos WHERE unit_id=? ORDER BY photo_type',(unit['id'],)))
    # Fotos entram em uma seção nova e são reduzidas proporcionalmente para caber na página.
    if photos:
        story.extend([PageBreak(),para('Registro fotográfico',size=16,bold=True),Spacer(1,5),
            para('Imagens cadastradas para esta unidade.',size=8,color=MUTED),Spacer(1,8)])
        for photo in photos:
            title='Foto externa' if photo['photo_type']=='exterior' else 'Foto interna'
            scale=min(512/photo['width'],252/photo['height'])
            story.extend([para(title,size=10,bold=True),Spacer(1,7),
                Image(io.BytesIO(photo['image']),width=photo['width']*scale,height=photo['height']*scale),
                Spacer(1,16)])
    # build transforma os elementos preparados em um PDF completo, armazenado em output.
    doc.build(story)
    return output.getvalue()
