# DADOS DOS ANDARES: lê, confere e grava o inventário interno de cada prédio.
"""Versioned floor inventory schema and validation."""
import json
from contacts import parse_contacts

# Regras compartilhadas pelo formulário, pela validação e pelos relatórios.
# Os nomes em inglês são chaves internas; os rótulos em português ficam em floor_views.py.
ROLES = ['Porteiros', 'Vigilantes', 'Bombeiros', 'Operador central']
SCHEDULES = {'12x36', '5x2', '6x1', 'Outra'}
NUMBERS = ('workstations','camera_local','camera_remote','badge_readers','face_readers','turnstiles','parking','alarms')

def migrate(con):
    # "Migrar" é atualizar a estrutura do banco sem perder os registros já existentes.
    # Cada versão concluída é anotada em schema_migrations para não repetir a etapa.
    con.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
    # Versão 2: cria a tabela dos andares e preserva inventários da versão antiga do sistema.
    if not con.execute('SELECT 1 FROM schema_migrations WHERE version=2').fetchone():
        con.execute('''CREATE TABLE IF NOT EXISTS floors(
      id INTEGER PRIMARY KEY, unit_id INTEGER NOT NULL REFERENCES units(id) ON DELETE CASCADE,
      position INTEGER NOT NULL, label TEXT NOT NULL, departments TEXT NOT NULL DEFAULT '[]',
      workstations INTEGER, staffing TEXT NOT NULL DEFAULT '[]', camera_local INTEGER,
      camera_remote INTEGER, badge_readers INTEGER, face_readers INTEGER, turnstiles INTEGER,
      parking INTEGER, notes TEXT NOT NULL DEFAULT '', is_unassigned INTEGER NOT NULL DEFAULT 0)''')
        con.execute('CREATE INDEX IF NOT EXISTS idx_floors_unit_position ON floors(unit_id,position)')
        # Os totais antigos pertenciam ao prédio inteiro. Não inventamos um andar para eles:
        # guardamos em "A distribuir por andar" até o analista conferir a distribuição.
        for unit in con.execute("SELECT id,details FROM units WHERE updated_at IS NOT NULL").fetchall():
            d=json.loads(unit['details'] or '{}')
            if not any(k in d for k in ('staffing','camera_local','camera_remote','badge_readers','face_readers','turnstiles','parking','notes')):
                continue
            con.execute('''INSERT INTO floors(unit_id,position,label,departments,workstations,staffing,camera_local,
          camera_remote,badge_readers,face_readers,turnstiles,parking,notes,is_unassigned)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (unit['id'],0,'A distribuir por andar','[]',None,json.dumps(d.get('staffing',[]),ensure_ascii=False),
               d.get('camera_local'),d.get('camera_remote'),d.get('badge_readers'),d.get('face_readers'),
               d.get('turnstiles'),d.get('parking'),d.get('notes',''),1))
        con.execute('INSERT INTO schema_migrations(version) VALUES(2)')
    # Versão 3: acrescenta a quantidade de alarmes, inicialmente não informada (NULL).
    if not con.execute('SELECT 1 FROM schema_migrations WHERE version=3').fetchone():
        if 'alarms' not in {row[1] for row in con.execute('PRAGMA table_info(floors)')}:
            con.execute('ALTER TABLE floors ADD COLUMN alarms INTEGER')
        con.execute('INSERT INTO schema_migrations(version) VALUES(3)')
    # Versão 4: acrescenta listas de focais por departamento e de responsáveis FM.
    # Essas listas são guardadas como texto JSON em duas colunas do SQLite.
    if not con.execute('SELECT 1 FROM schema_migrations WHERE version=4').fetchone():
        columns = {row[1] for row in con.execute('PRAGMA table_info(floors)')}
        for name, default in [('department_contacts', '{}'), ('fm_contacts', '[]')]:
            if name not in columns:
                con.execute(f"ALTER TABLE floors ADD COLUMN {name} TEXT NOT NULL DEFAULT '{default}'")
        con.execute('INSERT INTO schema_migrations(version) VALUES(4)')

def load(con,unit_id):
    # Lê os andares do prédio na ordem cadastrada e converte o JSON em listas/dicionários Python.
    result=[]
    for row in con.execute('SELECT * FROM floors WHERE unit_id=? ORDER BY position,id',(unit_id,)).fetchall():
        item=dict(row);item['departments']=json.loads(item['departments']);item['staffing']=json.loads(item['staffing'])
        item['department_contacts']=json.loads(item['department_contacts'])
        item['fm_contacts']=json.loads(item['fm_contacts'])
        result.append(item)
    return result

def parse(raw):
    # Recebe o texto JSON montado pelo navegador. Validar no servidor é obrigatório:
    # limites e campos HTML podem ser contornados por quem envia um pedido diretamente.
    try:items=json.loads(raw)
    except (ValueError,TypeError):raise ValueError('Confira os andares antes de salvar.')
    if not isinstance(items,list) or len(items)>50:raise ValueError('Informe até 50 andares por unidade.')
    result=[];labels=set()
    # Monta uma nova lista apenas com campos aceitos. Cada prédio pode ter até 50 andares.
    for item in items:
        if not isinstance(item,dict):raise ValueError('Dados de andar inválidos.')
        label=str(item.get('label','')).strip()[:100]
        if not label:raise ValueError('Informe o nome de cada andar, como Térreo, 1º andar ou Subsolo 1.')
        # casefold permite comparar nomes sem diferenciar maiúsculas de minúsculas.
        if label.casefold() in labels:raise ValueError('Cada andar deve ter um nome diferente.')
        labels.add(label.casefold())
        departments=item.get('departments',[])
        if not isinstance(departments,list) or len(departments)>30:raise ValueError('Confira os departamentos do andar.')
        departments=list(dict.fromkeys(str(x).strip()[:60] for x in departments if str(x).strip()))
        # Um focal só pode ser vinculado a um departamento presente neste mesmo andar.
        department_contacts=item.get('department_contacts',{})
        if not isinstance(department_contacts,dict) or any(key not in departments for key in department_contacts):
            raise ValueError('Vincule cada focal administrativo a um departamento cadastrado no andar.')
        department_contacts={key:parse_contacts(value, key) for key,value in department_contacts.items()}
        staffing=item.get('staffing',[])
        if not isinstance(staffing,list) or len(staffing)>30:raise ValueError('Confira os postos e escalas do andar.')
        # Cada posto deve ter uma função conhecida, quantidade válida e escala aceita.
        # Se a escala for "Outra", o texto de carga horária passa a ser obrigatório.
        shifts=[]
        for s in staffing:
            if not isinstance(s,dict):raise ValueError('Posto inválido.')
            role=s.get('role');schedule=s.get('schedule');custom=str(s.get('custom','')).strip()[:80]
            count=s.get('quantity')
            if role not in ROLES or schedule not in SCHEDULES or type(count)!=int or not 0<=count<=100000:
                raise ValueError('Confira posto, quantidade e escala.')
            if schedule=='Outra' and not custom:raise ValueError('Descreva a carga horária quando escolher Outra.')
            shifts.append({'role':role,'quantity':count,'schedule':schedule,'custom':custom})
        # Reúne textos, contatos e postos já conferidos no formato usado para gravar o banco.
        clean={'label':label,'departments':departments,'department_contacts':department_contacts,
               'fm_contacts':parse_contacts(item.get('fm_contacts',[]),'FM'),'staffing':shifts,
               'notes':str(item.get('notes','')).strip()[:2000],
               'is_unassigned':1 if item.get('is_unassigned') and label=='A distribuir por andar' else 0}
        # Regra essencial: vazio vira None (não informado); 0 confirma ausência do equipamento.
        # bool não é aceito como quantidade, mesmo sendo um tipo derivado de inteiro no Python.
        for key in NUMBERS:
            value=item.get(key)
            if value in (None,''):clean[key]=None
            elif type(value)!=int or not 0<=value<=100000:raise ValueError('As quantidades devem estar entre 0 e 100.000.')
            else:clean[key]=value
        result.append(clean)
    return result

def replace(con,unit_id,items):
    # Substitui os andares do prédio pela lista validada. O chamador controla commit/rollback:
    # excluir antigos e inserir novos fazem parte da mesma transação de salvamento da ficha.
    # parking continua armazenado por compatibilidade, embora o campo tenha saído da interface.
    con.execute('DELETE FROM floors WHERE unit_id=?',(unit_id,))
    for pos,item in enumerate(items):
        con.execute('''INSERT INTO floors(unit_id,position,label,departments,workstations,staffing,camera_local,
          camera_remote,badge_readers,face_readers,turnstiles,parking,alarms,notes,is_unassigned,department_contacts,fm_contacts)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
          (unit_id,pos,item['label'],json.dumps(item['departments'],ensure_ascii=False),item['workstations'],
           json.dumps(item['staffing'],ensure_ascii=False),item['camera_local'],item['camera_remote'],
           item['badge_readers'],item['face_readers'],item['turnstiles'],item['parking'],item['alarms'],item['notes'],item['is_unassigned'],
           json.dumps(item['department_contacts'],ensure_ascii=False),json.dumps(item['fm_contacts'],ensure_ascii=False)))
