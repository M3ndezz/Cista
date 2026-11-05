# FICHA DA UNIDADE: monta a tela, prepara o mapa e coordena o salvamento dos dados.
"""Unit edit page, Google Maps embed, and validated save operation."""
import html
import json
import os
from html.parser import HTMLParser
from urllib.parse import urlencode, urlsplit

import floors
import photos
from locations import location
from floor_views import render_floor
from contacts import DEFAULT_COORDINATOR

# HTML usa caracteres especiais. Esta função permite mostrar o texto digitado sem tratá-lo como código.
def h(value):return html.escape(str(value if value is not None else ''),quote=True)

# Opções dos menus da ficha e contato inicial do coordenador.
FOCALS=('Vitor Aronchi','Ivan Fernandes','Jacson Vieira da Silva','Lucas Capinan de Oliveira')
COORDINATOR_PHONE=DEFAULT_COORDINATOR
RISK_LEVELS=('Baixo','Médio','Alto')

class EmbedParser(HTMLParser):
    # Lê um HTML colado do Maps para extrair só o endereço do iframe, sem executar aquele HTML.
    def __init__(self):
        # Inicia o leitor de HTML e a lista de endereços encontrados.
        super().__init__();self.sources=[]
    def handle_starttag(self,tag,attrs):
        # O leitor chama este método a cada tag: só aproveitamos src de elementos iframe.
        if tag.lower()=='iframe':self.sources.extend(v for k,v in attrs if k.lower()=='src' and v)

def validated_embed(value):
    """Only accept a Google Maps Share > Embed link; never render pasted HTML."""
    # Aceita um link ou o HTML de um único mapa. Vazio significa usar o mapa automático.
    value=value.strip()
    if not value:return ''
    if len(value)>4000:raise ValueError('O código de incorporação é muito longo.')
    if value.startswith('<'):
        parser=EmbedParser();parser.feed(value)
        if len(parser.sources)!=1:raise ValueError('Cole o HTML de incorporação de um único mapa do Google Maps.')
        value=parser.sources[0]
    # Confere protocolo, domínio e caminho; colar conteúdo de outro site não é permitido aqui.
    parts=urlsplit(value)
    if (parts.scheme!='https' or parts.netloc not in ('www.google.com','google.com')
            or parts.path!='/maps/embed' or not parts.query or parts.fragment):
        raise ValueError('Use Compartilhar → Incorporar um mapa → Copiar HTML no Google Maps.')
    return value

def map_panel(unit):
    # Ordem de preferência: mapa manual válido, imagem Static Maps com chave e mapa automático sem chave.
    embed=json.loads(unit['details'] or '{}').get('map_embed','')
    if embed:
        try:src=validated_embed(embed)
        except ValueError:src=''
        if src:return f'<iframe class="satellite-map" title="Mapa de {h(unit["name"])}" src="{h(src)}" width="640" height="360" loading="lazy" referrerpolicy="no-referrer-when-downgrade" allowfullscreen></iframe>'
    # A consulta ao mapa usa um endereço montado com os dados da unidade, sem trechos repetidos.
    address=location(unit,name=True,zip_code=True,country=True)
    if not any(unit[k] for k in ('address','city','zip')):
        return '<div class="map-empty">Adicione o endereço ou a cidade para localizar esta unidade.</div>'
    key=os.environ.get('CISTA_MAPS_STATIC_KEY','').strip()
    if not key:
        # Este link funciona como incorporação do site do Maps, mas não é uma API documentada.
        # Pode mudar no futuro. t=k seleciona satélite; z=18 define a aproximação do mapa.
        src='https://maps.google.com/maps?'+urlencode({'q':address,'t':'k','z':18,'output':'embed'})
        return f'<iframe class="satellite-map" title="Vista aérea automática de {h(unit["name"])}" src="{h(src)}" width="1100" height="500" loading="lazy" referrerpolicy="no-referrer-when-downgrade" allowfullscreen></iframe>'
    # A alternativa com chave produz uma imagem parada, em vez do mapa interativo.
    src='https://maps.googleapis.com/maps/api/staticmap?'+urlencode({
        'center':address,'zoom':18,'size':'640x360','scale':2,
        'maptype':'satellite','format':'jpg','key':key})
    return f'<img class="satellite-map" alt="Imagem de satélite da região de {h(unit["name"])}" width="640" height="360" loading="lazy" referrerpolicy="strict-origin-when-cross-origin" src="{h(src)}">'

def photo_slots(con,unit_id,csrf,revision):
    # Desenha os dois espaços de foto e seus formulários independentes de envio/remover.
    existing={r['photo_type']:r for r in con.execute(
        'SELECT photo_type,updated_at FROM unit_photos WHERE unit_id=?',(unit_id,)).fetchall()}
    items=[]
    # Foto existente mostra uma prévia; espaço vazio mostra um aviso. O envio usa multipart.
    for kind,title,description in [('exterior','Foto externa','Fachada e entorno'),('interior','Foto interna','Área interna de referência')]:
        current=existing.get(kind)
        preview=(f'<img src="/unit/{unit_id}/photo/{kind}" loading="lazy" alt="{title} do prédio">' if current
                 else '<div class="photo-placeholder">Nenhuma foto enviada</div>')
        remove=(f'<form method="post" action="/unit/{unit_id}/photo/{kind}/delete" class="photo-delete"><input type="hidden" name="csrf" value="{h(csrf)}"><input type="hidden" name="revision" value="{revision}"><button type="submit" class="text-button">Remover foto</button></form>' if current else '')
        items.append(f'''<article class="photo-slot"><div class="photo-slot-heading"><strong>{title}</strong><span>{description}</span></div>{preview}
          <form method="post" action="/unit/{unit_id}/photo/{kind}" enctype="multipart/form-data" class="photo-upload">
            <input type="hidden" name="csrf" value="{h(csrf)}"><input type="hidden" name="revision" value="{revision}">
            <label>Selecionar imagem JPEG ou PNG<input type="file" name="image" accept="image/jpeg,image/png" required></label>
            <button class="secondary">{'Substituir foto' if current else 'Enviar foto'}</button></form>{remove}</article>''')
    return ''.join(items)

def show(handler,con,user,csrf,unit_id,notice='',status=200):
    # Busca os dados necessários para a tela. handler é o atendimento HTTP vindo de app.py.
    u=con.execute('SELECT * FROM units WHERE id=?',(unit_id,)).fetchone()
    if not u:return handler.fail()
    editor=con.execute('SELECT display_name FROM users WHERE id=?',(u['updated_by'],)).fetchone() if u['updated_by'] else None
    # A revisão é o último identificador do histórico. Ela permite detectar edições concorrentes.
    revision=con.execute('SELECT COALESCE(MAX(id),0) FROM audit WHERE unit_id=?',(unit_id,)).fetchone()[0]
    floor_items=floors.load(con,unit_id)
    floor_html=''.join(render_floor(f,open_card=(i==0)) for i,f in enumerate(floor_items))
    address=location(u)
    updated=(f'Atualizada em {h(u["updated_at"][:16].replace("T"," "))} por {h(editor["display_name"] if editor else "analista")}' if u['updated_at'] else 'Aguardando primeiro levantamento')
    # "details" guarda campos complementares como texto JSON no banco; aqui vira um dicionário.
    details=json.loads(u['details'] or '{}')
    extension=details.get('extension','')
    embed=details.get('map_embed','')
    focal=details.get('focal','')
    # Monta os menus e marca como selected a opção que já está salva nesta unidade.
    focal_options='<option value="">Selecione um focal</option>'+''.join(
        f'<option value="{h(name)}" {"selected" if focal==name else ""}>{h(name)}</option>' for name in FOCALS)
    risk=details.get('risk_level','')
    risk_options='<option value="">Não avaliado</option>'+''.join(
        f'<option value="{h(level)}" {"selected" if risk==level else ""}>{h(level)}</option>' for level in RISK_LEVELS)
    risk_note=details.get('risk_note','')
    # Consulta apenas as 20 ações mais recentes para exibir; não apaga os registros anteriores.
    history=con.execute('''SELECT a.action,a.at,COALESCE(p.display_name,'Usuário removido') AS actor
        FROM audit a LEFT JOIN users p ON p.id=a.actor_id WHERE a.unit_id=?
        ORDER BY a.id DESC LIMIT 20''',(unit_id,)).fetchall()
    history_html=''.join(f'<li><div><strong>{h(item["actor"])}</strong> <time>{h(item["at"][:16].replace("T"," "))}</time></div><p>{h(item["action"])}</p></li>' for item in history) or '<li class="muted">Nenhuma alteração registrada ainda.</li>'
    # O HTML abaixo monta, nesta ordem: cabeçalho, dados, mapa, andares, fotos, salvar e histórico.
    # name identifica os campos enviados ao servidor; id ajuda o JavaScript a encontrá-los.
    # csrf e revision ficam ocultos. floors-json recebe o inventário montado por static/app.js.
    # O botão Salvar está fora do <form>, mas form="inventory-form" o liga à ficha correta.
    # <template> guarda um modelo de andar invisível, clonado ao clicar em Adicionar andar.
    body=f'''<div class="breadcrumbs"><a href="/group/{u['group_key']}">← {h(handler.group_title(u['group_key']))}</a></div>
      <div class="page-heading"><div class="eyebrow">Ficha tática · {h(u['code'])}</div><h1>{h(u['name'])}</h1><p>{h(address)}</p><span class="badge {'done' if u['updated_at'] else 'pending'}">{updated}</span> <a class="button outline" href="/report.pdf?unit={unit_id}">Baixar PDF deste prédio</a></div>
      <form class="inventory-form" method="post" action="/unit/{unit_id}" id="inventory-form">
      <input type="hidden" name="csrf" value="{h(csrf)}"><input type="hidden" name="revision" value="{revision}"><input type="hidden" name="floors_json" id="floors-json">
      <section class="panel"><div class="section-title"><h2>Dados da unidade</h2><p>Localização, contatos e vista aérea.</p></div>
        <div class="unit-data-grid"><div class="form-grid">
          <label>Nome da unidade<input name="name" maxlength="150" value="{h(u['name'])}" required></label>
          <label>Código de origem<input value="{h(u['code'])}" disabled></label>
          <label>Endereço<input name="address" maxlength="250" value="{h(u['address'])}"></label>
          <label>Cidade<input name="city" maxlength="120" value="{h(u['city'])}"></label>
          <label>Estado<input name="state" maxlength="100" value="{h(u['state'])}"></label>
          <label class="full-width">Andares<input name="floor" maxlength="120" value="{h(u['floor'])}" placeholder="Ex.: térreo, 1º ao 5º andar"></label>
          <label class="coordinator-field">Nome e telefone do coordenador<input name="coordinator_phone" maxlength="200" value="{h(details.get('coordinator_phone',COORDINATOR_PHONE))}" placeholder="Nome - telefone"></label>
          <label class="property-field">Focal Patrimônio (nome - telefone)<input name="property_contact" maxlength="200" value="{h(details.get('property_contact',''))}" placeholder="Nome - telefone"></label>
          <label>Ramal<input name="extension" maxlength="40" value="{h(extension)}"></label>
          <label>Focal do prédio<select name="focal">{focal_options}</select></label>
          <label class="company-field">Empresa de vigilância<input name="security_company" maxlength="150" value="{h(u['security_company'])}"></label>
          <div class="risk-panel"><div class="risk-heading"><strong>Avaliação de risco</strong><small>Classificação manual da unidade</small></div><label>Nível de risco<select name="risk_level">{risk_options}</select></label><label>Observação<textarea name="risk_note" maxlength="1000" rows="4" placeholder="Descreva os fatores observados e o motivo da classificação">{h(risk_note)}</textarea></label></div>
        </div><div class="map-panel"><div class="map-heading"><strong>Vista aérea do prédio</strong><span>{'Localização ajustada manualmente' if embed else 'Gerada automaticamente pela localização cadastrada'}</span></div>{map_panel(u)}<small>Confira a localização antes de usar o mapa como referência. Após alterar o endereço, salve a ficha para atualizar a vista automática.</small><details class="map-override" {'open' if embed else ''}><summary>Ajustar localização do mapa</summary><label>Link de incorporação do Google Maps<textarea name="map_embed" maxlength="4000" rows="3" placeholder="Opcional: cole o HTML de Incorporar um mapa ou a URL do iframe">{h(embed)}</textarea></label><small>Use somente quando o mapa automático apontar para o lugar errado. No Google Maps: Compartilhar → Incorporar um mapa → Copiar HTML. Para voltar ao automático, apague o conteúdo e salve.</small></details></div></div>
      </section>
      <section class="panel floors-panel"><div class="floor-section-heading"><div><div class="eyebrow">Inventário interno</div><h2>Andares e pavimentos</h2><p>Abra cada andar para registrar departamentos, posições de trabalho, postos e equipamentos.</p></div><button type="button" class="secondary" id="add-floor">+ Adicionar andar</button></div><div id="floors-container">{floor_html}</div><p class="muted empty-floors {'hidden' if floor_html else ''}">Nenhum andar cadastrado. Comece pelo térreo, subsolo ou pavimento que desejar.</p></section>
      </form>
      <section class="panel"><div class="section-title"><h2>Registro fotográfico do prédio</h2><p>Salve a ficha antes de enviar fotos. Cada espaço aceita uma imagem JPEG ou PNG de até 5 MB; você pode substituir ou remover depois.</p></div><div class="photo-grid">{photo_slots(con,unit_id,csrf,revision)}</div></section>
      <div class="save-bar"><span>As alterações ficam registradas com o usuário e a data.</span><button class="primary" type="submit" form="inventory-form">Salvar ficha</button></div>
      <section class="panel history-panel"><div class="section-title"><h2>Histórico de modificações</h2><p>As 20 atualizações mais recentes deste prédio.</p></div><ol class="history-list">{history_html}</ol></section>
      <template id="floor-template">{render_floor({},open_card=True)}</template>'''
    handler.page(body,u['name'],status,user,csrf,notice)

def save(handler,con,user,csrf,unit_id,form):
    # Carrega a ficha e compara revisões antes de aceitar alterações enviadas pelo navegador.
    row=con.execute('SELECT * FROM units WHERE id=?',(unit_id,)).fetchone()
    if not row:return handler.fail()
    latest=con.execute('SELECT COALESCE(MAX(id),0) FROM audit WHERE unit_id=?',(unit_id,)).fetchone()[0]
    if form.get('revision')!=str(latest):
        return show(handler,con,user,csrf,unit_id,'A ficha foi alterada por outra pessoa. Recarregue antes de salvar novamente.',409)
    # Confere andares, nomes, mapas, contatos e menus antes de modificar o banco.
    try:
        if 'floors_json' not in form:raise ValueError('Atualize a página para editar os andares.')
        floor_items=floors.parse(form['floors_json'])
        # Campos principais são limitados ao tamanho definido; os contatos maiores são validados abaixo.
        updates={k:form.get(k,'').strip()[:limit] for k,limit in [('name',150),('address',250),('city',120),('state',100),('floor',120),('security_company',150)]}
        if not updates['name']:raise ValueError('Informe o nome da unidade.')
        details=json.loads(row['details'] or '{}')
        old_details=details.copy()
        details['extension']=form.get('extension','').strip()[:40]
        details['map_embed']=validated_embed(form.get('map_embed',''))
        details['coordinator_phone']=form.get('coordinator_phone',details.get('coordinator_phone',COORDINATOR_PHONE)).strip()
        details['property_contact']=form.get('property_contact',details.get('property_contact','')).strip()
        if any(len(details[key])>200 for key in ('coordinator_phone','property_contact')):
            raise ValueError('Os contatos do coordenador e de Patrimônio aceitam até 200 caracteres.')
        focal=form.get('focal','').strip()
        if focal and focal not in FOCALS:raise ValueError('Selecione um focal da lista.')
        details['focal']=focal
        risk_level=form.get('risk_level','').strip()
        if risk_level and risk_level not in RISK_LEVELS:raise ValueError('Selecione um nível de risco da lista.')
        details['risk_level']=risk_level
        details['risk_note']=form.get('risk_note','').strip()[:1000]
    except (ValueError,TypeError,KeyError) as exc:
        return show(handler,con,user,csrf,unit_id,str(exc),400)
    # Reserva a escrita e confere a revisão novamente: outro analista pode ter salvado durante a validação.
    # Em conflito, rollback desfaz a transação e pede recarregamento em vez de sobrescrever a ficha.
    con.execute('BEGIN IMMEDIATE')
    current=con.execute('SELECT COALESCE(MAX(id),0) FROM audit WHERE unit_id=?',(unit_id,)).fetchone()[0]
    if current!=latest:
        con.rollback()
        return show(handler,con,user,csrf,unit_id,'A ficha foi alterada por outra pessoa. Recarregue antes de salvar novamente.',409)
    def change_text(label,before,after):
        # Forma o resumo "campo: antes -> depois". O corte é só no histórico, não no dado nem no PDF.
        compact=lambda value: (str(value or '—')[:77]+'…') if len(str(value or '—'))>77 else str(value or '—')
        return f'{label}: {compact(before)} → {compact(after)}'
    # Compara campos anteriores e novos para descrever as alterações no histórico.
    # Para os andares, o histórico registra um resumo geral de inventário atualizado.
    changes=[change_text(label,row[key],updates[key])
             for key,label in [('name','nome'),('address','endereço'),('city','cidade'),('state','estado'),('floor','andares'),('security_company','empresa de vigilância')]
             if (row[key] or '')!=updates[key]]
    changes.extend(change_text(label,old_details.get(key,COORDINATOR_PHONE if key=='coordinator_phone' else ''),details[key])
                   for key,label in [('extension','ramal'),('coordinator_phone','nome e telefone do coordenador'),('property_contact','focal Patrimônio'),('focal','focal do prédio'),('risk_level','nível de risco'),('risk_note','observação de risco')]
                   if (old_details.get(key,COORDINATOR_PHONE if key=='coordinator_phone' else '') or '')!=details[key])
    if old_details.get('map_embed','')!=details['map_embed']:changes.append('mapa: link incorporado atualizado' if details['map_embed'] else 'mapa: voltou à busca automática')
    if floors.load(con,unit_id)!=floor_items:changes.append('inventário dos andares: atualizado')
    action=('Campos alterados: '+', '.join(changes)) if changes else 'Ficha revisada sem alteração de dados'
    # Grava dados da unidade, todos os andares e uma nova entrada de histórico.
    # Os ? do SQL recebem valores separados, evitando misturar dados digitados com comandos SQL.
    con.execute('''UPDATE units SET name=?,address=?,city=?,state=?,floor=?,security_company=?,
        details=?,updated_at=?,updated_by=? WHERE id=?''',(*updates.values(),json.dumps(details,ensure_ascii=False),handler.timestamp(),user['id'],unit_id))
    floors.replace(con,unit_id,floor_items)
    con.execute('INSERT INTO audit(unit_id,actor_id,action,at) VALUES(?,?,?,?)',(unit_id,user['id'],action,handler.timestamp()))
    # Só neste ponto as alterações são confirmadas. Depois o navegador recarrega a ficha salva.
    con.commit()
    return handler.redirect('/unit/'+str(unit_id))
