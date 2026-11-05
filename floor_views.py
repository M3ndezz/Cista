# TELA DOS ANDARES: pequenos componentes HTML usados no painel de cada pavimento.
"""HTML components for editable floor accordions."""
import html
from floors import ROLES, NUMBERS

# Estes componentes devolvem HTML; eles não gravam dados no banco.
# A função h protege textos ao inseri-los nos campos e atributos da página.
def h(value):return html.escape(str(value if value is not None else ''),quote=True)

# Tradução das chaves internas de equipamentos para os rótulos vistos pelo analista.
LABELS={
    'workstations':'Nº de posições de trabalho',
    'camera_local':'Câmeras · monitoramento local',
    'camera_remote':'Câmeras · monitoramento remoto',
    'badge_readers':'Leitoras de crachá',
    'face_readers':'Leitores faciais',
    'turnstiles':'Catracas',
    'alarms':'Alarmes',
}

def staff_row(item=None):
    # Desenha uma linha de posto: função, quantidade, escala, carga horária e botão de remoção.
    # Sem item, cria a linha vazia usada como modelo ao adicionar um posto.
    item=item or {}
    options=''.join(f'<option value="{h(s)}" {"selected" if item.get("schedule")==s else ""}>{h(s)}</option>' for s in ['12x36','5x2','6x1','Outra'])
    roles=''.join(f'<option value="{h(role)}" {"selected" if item.get("role")==role else ""}>{h(role)}</option>' for role in ROLES)
    return f'''<div class="staff-row"><label>Posto<select class="staff-role">{roles}</select></label><label>Quantidade<input class="staff-quantity" type="number" min="0" max="100000" value="{h(item.get('quantity',''))}" placeholder="0"></label><label>Escala<select class="staff-schedule">{options}</select></label><label>Outra carga horária<input class="staff-custom" maxlength="80" value="{h(item.get('custom',''))}" placeholder="Ex.: 8 horas"></label><button class="remove-row" type="button" aria-label="Remover posto">×</button></div>'''

def contact_row(item=None):
    # Componente reaproveitado: a mesma linha de nome/telefone serve para focal administrativo e FM.
    item=item or {}
    return f'''<div class="contact-row">
      <label>Nome<input class="contact-name" maxlength="150" value="{h(item.get('name',''))}" placeholder="Nome completo"></label>
      <label>Telefone / ramal<input class="contact-phone" maxlength="80" value="{h(item.get('contact',''))}" placeholder="Telefone com DDD ou ramal"></label>
      <button type="button" class="remove-contact remove-row" aria-label="Remover contato">×</button>
    </div>'''

def department_block(name,contacts):
    # Agrupa as linhas de contatos de um único departamento; data-department guarda o vínculo.
    rows=''.join(contact_row(item) for item in contacts) or contact_row()
    return f'''<section class="department-block" data-department="{h(name)}">
      <div class="department-heading"><strong>{h(name)}</strong><span>Focais administrativos</span></div>
      <div class="department-contact-rows">{rows}</div>
      <button type="button" class="secondary add-department-contact">+ Adicionar focal</button>
    </section>'''

def render_floor(item=None,open_card=False):
    # Desenha um andar completo. <details> e <summary> formam o painel que abre e fecha.
    # item contém os dados salvos; open_card define se o painel começa aberto.
    item=item or {}
    name=item.get('label','')
    tags=''.join(f'<span class="tag" data-tag="{h(tag)}">{h(tag)}<button type="button" class="remove-tag" aria-label="Remover {h(tag)}">×</button></span>' for tag in item.get('departments',[]))
    # Reaproveita os componentes para montar tags, postos, equipamentos e contatos daquele andar.
    # join une vários pedaços de HTML em um texto; "or" fornece uma linha vazia quando necessário.
    shifts=''.join(staff_row(s) for s in item.get('staffing',[])) or staff_row()
    numbers=''.join(f'<label>{h(LABELS[key])}<input class="floor-number" data-field="{key}" type="number" min="0" max="100000" value="{h(item.get(key,""))}" placeholder="Não informado"></label>' for key in NUMBERS if key!='parking')
    departments=''.join(department_block(name,item.get('department_contacts',{}).get(name,[])) for name in item.get('departments',[]))
    fm_rows=''.join(contact_row(person) for person in item.get('fm_contacts',[])) or contact_row()
    # O aviso aparece somente no agrupamento usado para preservar dados de versões antigas.
    unassigned='true' if item.get('is_unassigned') else 'false'
    note='<p class="carry-note">Dados antigos do prédio preservados aqui. Distribua pelos andares quando conferir o local.</p>' if item.get('is_unassigned') else ''
    # Classes (class) conectam o HTML ao CSS; atributos data-* conectam o HTML ao JavaScript.
    # data-legacy-parking preserva a quantidade antiga de vagas sem mostrar um campo para edição.
    return f'''<details class="floor-card" data-unassigned="{unassigned}" data-legacy-parking="{h(item.get('parking',''))}" {'open' if open_card else ''}>
      <summary><span class="floor-number-icon">▦</span><span class="floor-title">{h(name or 'Novo andar')}</span><span class="floor-meta">{len(item.get('departments',[]))} departamentos</span><span class="chevron">⌄</span></summary>
      <div class="floor-body">{note}
        <div class="floor-head"><label>Andar / pavimento<input class="floor-label" maxlength="100" value="{h(name)}" placeholder="Ex.: Térreo, 1º andar, Subsolo 1" required></label><button type="button" class="remove-floor text-button">Remover andar</button></div>
        <div class="tag-editor"><label>Departamentos neste andar<input class="tag-entry" maxlength="60" placeholder="Digite um departamento e pressione Enter"></label><div class="tag-list" aria-label="Departamentos cadastrados">{tags}</div><p class="hint">Use Enter ou vírgula. Cada departamento terá sua própria lista de focais administrativos.</p>
          <div class="department-contacts">{departments}</div>
        </div>
        <div class="form-grid floor-counts">{numbers}</div>
        <div class="floor-subsection"><h3>Postos e escalas</h3><p>Adicione linhas para escalas ou turnos diferentes.</p><div class="floor-staff">{shifts}</div><button class="secondary add-staff" type="button">+ Adicionar posto ou escala</button></div>
        <div class="floor-subsection fm-section"><h3>Identificação de FM</h3><p>Registre nome e contato dos responsáveis por este andar.</p><div class="fm-contact-rows">{fm_rows}</div><button type="button" class="secondary add-fm-contact">+ Adicionar FM</button></div>
        <div class="floor-subsection"><h3>Observações do andar</h3><textarea class="floor-notes" maxlength="2000" rows="3" placeholder="Informações adicionais deste pavimento">{h(item.get('notes',''))}</textarea></div>
      </div>
    </details>'''
