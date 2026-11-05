#!/usr/bin/env python3
# COMEÇO DO SISTEMA: atende o navegador, identifica o usuário e encaminha cada ação ao módulo correto.
"""CISTA: internal tactical facilities inventory. Python 3.10+."""
import argparse
# Bibliotecas do Python: argumentos do terminal, senhas, textos, tempo e comunicação HTTP.
# Os imports abaixo de "import floors" são módulos do próprio projeto.
import getpass
import hashlib
import hmac
import html
import json
import secrets
import sqlite3
import time
from datetime import datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import floors
import photos
import reports
import unit_views
import database
from auth import check_password, clean_username, password_hash, validate_password
from contacts import DEFAULT_COORDINATOR

ROOT = Path(__file__).resolve().parent
# Configurações compartilhadas: pasta do programa, banco escolhido, áreas e duração do login.
DB = database.default_path()
GROUPS = {'fundacao': 'Fundação Bradesco', 'cdd': 'Bradesco Cidade de Deus', 'externos': 'Bradesco Externos'}
ROLES = floors.ROLES
SESSION_AGE = 12 * 3600
# A duração é expressa em segundos: 12 horas multiplicadas por 3.600 segundos.

# Converte dados em texto seguro para HTML: caracteres como < e > aparecem como texto.
def h(v): return html.escape(str(v if v is not None else ''), quote=True)
# Obtém a data e a hora com o fuso configurado no computador servidor.
def now(): return datetime.now().astimezone().isoformat(timespec='seconds')
# Encaminha a abertura do banco para database.py, usando o caminho configurado acima.
def connect():
    return database.connect(DB)

# Encaminha a preparação das tabelas e migrações para database.py.
def init_db():
    database.init_db(DB)

def stats(c, group=None):
    # "c" é a conexão com o banco. Se houver "group", seleciona somente aquela área.
    rows=c.execute('SELECT * FROM units'+(' WHERE group_key=?' if group else ''), ((group,) if group else ())).fetchall()
    # A ficha conta como atualizada quando possui data de atualização; isso não mede completude dos campos.
    filled=sum(bool(x['updated_at']) for x in rows)
    staff={r:0 for r in ROLES}
    totals={f:0 for f in floors.NUMBERS}
    # Percorre prédio -> andar -> postos/equipamentos para produzir os totais do dashboard.
    for x in rows:
        for floor in floors.load(c,x['id']):
            for entry in floor['staffing']:staff[entry['role']]+=entry['quantity']
            for f in totals:totals[f]+=int(floor.get(f) or 0)
    return rows,filled,staff,totals

def make_pdf(c, group=None, unit_id=None):
    # Escolhe o relatório pelo pedido: uma unidade, uma área ou todas as unidades.
    # A aparência do arquivo é responsabilidade de reports.py.
    if unit_id is not None:
        unit=c.execute('SELECT * FROM units WHERE id=?',(unit_id,)).fetchone()
        if not unit:raise ValueError('Unidade não encontrada')
        return reports.unit_pdf(c,unit,GROUPS.get(unit['group_key'],'Unidade'))
    if group:
        rows=c.execute('SELECT * FROM units WHERE group_key=? ORDER BY name COLLATE NOCASE,id',(group,)).fetchall()
        return reports.group_pdf(rows,GROUPS[group])
    rows=c.execute('SELECT * FROM units ORDER BY group_key,name COLLATE NOCASE,id').fetchall()
    return reports.overview_pdf(rows,GROUPS)

class App(BaseHTTPRequestHandler):
    # Esta classe atende os pedidos que chegam do navegador.
    # "self" representa o atendimento atual; métodos são funções que pertencem à classe.
    server_version='CISTA/1.0'
    def log_message(self,fmt,*args):
        # Mostra no terminal um registro simples de cada pedido recebido pelo servidor.
        print('%s %s'%(self.address_string(),fmt%args))
    def headers_common(self,ctype='text/html; charset=utf-8',length=None):
        # Cabeçalhos são instruções enviadas ao navegador antes do conteúdo da resposta.
        # Identificam o tipo de arquivo, desestimulam cache e restringem algumas formas de uso da página.
        self.send_header('Content-Type',ctype)
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('X-Frame-Options','DENY')
        # CSP lista origens permitidas para scripts, estilos, imagens e mapas; não substitui autenticação.
        self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' https://maps.googleapis.com; frame-src https://www.google.com https://google.com https://maps.google.com; form-action 'self'; frame-ancestors 'none'")
        if length is not None:self.send_header('Content-Length',str(length))
    def send_bytes(self,data,ctype='text/html; charset=utf-8',status=200,extra=None):
        # Finaliza uma resposta: código HTTP, cabeçalhos e conteúdo em bytes (HTML, foto ou PDF).
        # 200 significa sucesso. Outros métodos podem fornecer códigos de erro ou redirecionamento.
        self.send_response(status);self.headers_common(ctype,len(data))
        for k,v in (extra or []):self.send_header(k,v)
        self.end_headers();self.wfile.write(data)
    def page(self,body,title='CISTA',status=200,user=None,csrf=None,notice=''):
        # Envolve o conteúdo específico (body) na estrutura comum: marca, menu, usuário e rodapé.
        # Uma f-string mistura HTML e dados: o trecho entre {chaves} é calculado pelo Python.
        links='<a href="/">Visão geral</a>' + ''.join(f'<a href="/group/{k}">{h(v)}</a>' for k,v in GROUPS.items())
        if user and user['role']=='admin':links+='<a href="/admin">Usuários</a>'
        # O menu administrativo só é exibido ao admin; as rotas também verificam esse perfil.
        # O campo csrf acompanha formulários para conferir se o pedido pertence à sessão atual.
        auth=(f'<span class="user-tag">{h(user["display_name"])} · {"Admin" if user["role"]=="admin" else "Analista"}</span>'
              f'<form action="/logout" method="post"><input type="hidden" name="csrf" value="{h(csrf)}"><button class="text-button">Sair</button></form>') if user else ''
        message=f'<div class="notice">{h(notice)}</div>' if notice else ''
        document=f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{h(title)} | CISTA</title><link rel="stylesheet" href="/static/style.css"><script src="/static/app.js" defer></script></head><body><header class="top"><div class="brand"><span class="brand-mark" aria-hidden="true"><svg viewBox="0 0 48 48" fill="none" focusable="false"><path d="M24 5 39 10v13c0 10-6.2 16.8-15 20-8.8-3.2-15-10-15-20V10L24 5Z" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round"/><path d="M17 29V19l7-4 7 4v10M21 23v6m6-6v6M16 30h16" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg></span><div><strong>CISTA</strong><small>Proteção de Polos Administrativos</small></div></div>{('<nav aria-label="Navegação principal">'+links+'</nav>') if user else ''}<div class="auth">{auth}</div></header><main>{message}{body}</main><footer>CISTA · Inventário tático de unidades</footer></body></html>'''
        self.send_bytes(document.encode(),status=status)
    def redirect(self,path,cookie=None):
        # Pede ao navegador que abra outro endereço. Pode gravar ou limpar o cookie do login.
        self.send_response(303);self.headers_common();self.send_header('Location',path)
        if cookie:self.send_header('Set-Cookie',cookie)
        self.end_headers()
    def fail(self,status=404,message='Página não encontrada'):
        # Exibe uma página de erro simples. 404 significa que o recurso solicitado não foi encontrado.
        self.page(f'<section class="panel"><h1>{h(message)}</h1><a href="/">Voltar</a></section>',status=status)
    def current_user(self,c):
        # Lê o cookie (identificador de sessão enviado pelo navegador) e procura uma sessão válida.
        cookie=SimpleCookie()
        try:cookie.load(self.headers.get('Cookie',''));token=cookie['cista_session'].value
        except (KeyError,ValueError):return None,None
        # O banco guarda o hash do identificador. Sessões vencidas e contas inativas não são aceitas.
        row=c.execute('''SELECT u.*,s.csrf FROM sessions s JOIN users u ON u.id=s.user_id
            WHERE s.token_hash=? AND s.expires_at>? AND u.active=1''',(hashlib.sha256(token.encode()).hexdigest(),int(time.time()))).fetchone()
        return (row,row['csrf']) if row else (None,None)
    def form(self):
        # Lê um formulário de texto enviado por POST, limita seu tamanho e transforma campos em dicionário.
        # Fotos usam outro formato, tratado em photos.read_upload().
        length=int(self.headers.get('Content-Length','0'))
        if length>300000:raise ValueError('Formulário muito grande.')
        return {k:v[-1] for k,v in parse_qs(self.rfile.read(length).decode('utf-8'),keep_blank_values=True).items()}
    def do_GET(self):
        # GET é usado para abrir páginas ou baixar arquivos. "path" é a parte do endereço após o servidor.
        path=urlparse(self.path).path
        if path in ('/static/style.css','/static/app.js'):
            name=path.rsplit('/',1)[1];data=(ROOT/'static'/name).read_bytes()
            return self.send_bytes(data,'text/css; charset=utf-8' if name.endswith('.css') else 'text/javascript; charset=utf-8')
        # Estilos e JavaScript são públicos. As páginas e os dados abaixo exigem uma sessão válida.
        with connect() as c:
            user,csrf=self.current_user(c)
            if not user:
                if path!='/login':return self.redirect('/login')
                return self.page('''<section class="login panel"><div class="eyebrow">Acesso restrito</div><h1>Entrar na Cista</h1><p>Inventário tático dos polos e núcleos administrativos.</p><form action="/login" method="post"><label>Usuário<input name="username" autocomplete="username" required></label><label>Senha<input name="password" type="password" autocomplete="current-password" required></label><button class="primary">Entrar</button></form></section>''','Entrar')
            # Rotas: / = dashboard; /group/... = área; /unit/... = ficha; /admin = usuários.
            if path=='/login':return self.redirect('/')
            if path=='/':return self.dashboard(c,user,csrf)
            if path.startswith('/group/') and path.split('/')[-1] in GROUPS:
                return self.group(c,user,csrf,path.split('/')[-1])
            photo_parts=path.split('/')
            if len(photo_parts)==5 and photo_parts[1]=='unit' and photo_parts[2].isdigit() and photo_parts[3]=='photo' and photo_parts[4] in photos.TYPES:
                return photos.display(self,c,int(photo_parts[2]),photo_parts[4])
            if path.startswith('/unit/') and path.split('/')[-1].isdigit():
                return self.unit(c,user,csrf,int(path.split('/')[-1]))
            if path=='/admin' and user['role']=='admin':return self.admin(c,user,csrf)
            # Os parâmetros depois de ? escolhem o PDF: ?unit=1 ou ?group=cdd.
            # Confere os identificadores antes de consultar e enviar o arquivo para download.
            if path=='/report.pdf':
                params=parse_qs(urlparse(self.path).query)
                group=params.get('group',[''])[0]
                if group and group not in GROUPS:return self.fail(400,'Grupo inválido')
                unit=params.get('unit',[''])[0]
                if unit:
                    if group or not unit.isascii() or not unit.isdecimal():return self.fail(400,'Unidade inválida')
                    selected=c.execute('SELECT id FROM units WHERE id=?',(int(unit),)).fetchone()
                    if not selected:return self.fail()
                data=make_pdf(c,group or None,int(unit) if unit else None)
                filename=f'CISTA_unidade_{unit}.pdf' if unit else 'CISTA_inventario_consolidado.pdf'
                return self.send_bytes(data,'application/pdf',extra=[('Content-Disposition',f'attachment; filename="{filename}"')])
            return self.fail()
    def do_POST(self):
        # POST recebe ações: entrar, sair, salvar ficha, cadastrar usuários e enviar/remover fotos.
        path=urlparse(self.path).path
        photo_parts=path.split('/')
        # Fotos são tratadas primeiro porque chegam como multipart/form-data, contendo bytes da imagem.
        if (len(photo_parts) in (5,6) and photo_parts[1]=='unit' and photo_parts[2].isdigit()
                and photo_parts[3]=='photo' and photo_parts[4] in photos.TYPES
                and (len(photo_parts)==5 or photo_parts[5]=='delete')):
            with connect() as c:
                user,csrf=self.current_user(c)
                if not user:return self.redirect('/login')
                remove=len(photo_parts)==6
                try:
                    if remove:fields=self.form();raw=None
                    else:fields,raw=photos.read_upload(self)
                except (ValueError,UnicodeError) as exc:
                    return self.unit(c,user,csrf,int(photo_parts[2]),str(exc),400)
                return photos.save(self,c,user,csrf,int(photo_parts[2]),photo_parts[4],fields,raw,remove)
        try:f=self.form()
        except (ValueError,UnicodeDecodeError):return self.fail(400,'Formulário inválido')
        with connect() as c:
            # Login ainda não possui sessão. Todas as demais ações deste bloco exigem usuário e CSRF.
            if path=='/login':return self.login(c,f)
            user,csrf=self.current_user(c)
            if not user:return self.redirect('/login')
            if not hmac.compare_digest(f.get('csrf',''),csrf):return self.fail(403,'Sessão inválida. Atualize a página.')
            # Sair remove a sessão do banco e manda o navegador apagar seu cookie.
            if path=='/logout':
                cookie=SimpleCookie()
                try:cookie.load(self.headers.get('Cookie',''));token=cookie['cista_session'].value
                except (KeyError,ValueError):token=''
                c.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),))
                c.commit()
                return self.redirect('/login','cista_session=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict')
            if path.startswith('/group/') and path.endswith('/create'):
                parts=path.split('/')
                if len(parts)==4 and parts[2] in GROUPS:
                    return self.create_unit(c,user,csrf,parts[2],f)
            if path.startswith('/unit/') and path.split('/')[-1].isdigit():
                return self.save_unit(c,user,csrf,int(path.split('/')[-1]),f)
            if user['role']=='admin' and path in ('/admin/create','/admin/reset','/admin/toggle'):
                return self.manage_users(c,user,csrf,path,f)
            return self.fail(403,'Acesso negado')
    def login(self,c,f):
        # Padroniza o usuário e consulta suas tentativas recentes. Cinco falhas bloqueiam por 15 minutos.
        username=f.get('username','').strip().lower();pw=f.get('password','')
        attempt=c.execute('SELECT * FROM login_attempts WHERE username=?',(username,)).fetchone()
        if attempt and attempt['failures']>=5 and int(time.time())-attempt['last_at']<900:
            return self.page('<section class="panel login"><h1>Aguarde 15 minutos</h1><p>Houve muitas tentativas para este usuário.</p><a href="/login">Voltar</a></section>','Entrar',429)
        user=c.execute('SELECT * FROM users WHERE username=? AND active=1',(username,)).fetchone()
        # Senha incorreta ou conta não encontrada produzem a mesma mensagem para quem tenta entrar.
        if not user or not check_password(pw,user['password_hash']):
            failures=(attempt['failures']+1 if attempt and int(time.time())-attempt['last_at']<900 else 1)
            c.execute('INSERT INTO login_attempts(username,failures,last_at) VALUES(?,?,?) ON CONFLICT(username) DO UPDATE SET failures=?,last_at=?',
                (username,failures,int(time.time()),failures,int(time.time())))
            c.commit()
            return self.page('<section class="panel login"><h1>Não foi possível entrar</h1><p>Confira usuário e senha.</p><a href="/login">Tentar novamente</a></section>','Entrar',401)
        c.execute('DELETE FROM login_attempts WHERE username=?',(username,))
        # Após validar a senha, cria dois valores aleatórios: sessão de login e proteção dos formulários.
        token=secrets.token_urlsafe(40);csrf=secrets.token_urlsafe(32)
        c.execute('INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES(?,?,?,?)',
            (hashlib.sha256(token.encode()).hexdigest(),user['id'],csrf,int(time.time())+SESSION_AGE))
        c.commit()
        # Secure depende do cabeçalho informado pelo proxy HTTPS. O servidor Python não instala TLS sozinho.
        # HttpOnly impede leitura do cookie por JavaScript; SameSite restringe seu envio entre sites.
        secure='; Secure' if self.headers.get('X-Forwarded-Proto','').lower()=='https' else ''
        return self.redirect('/',f'cista_session={token}; Max-Age={SESSION_AGE}; Path=/; HttpOnly; SameSite=Strict{secure}')
    def dashboard(self,c,user,csrf):
        # Carrega os totais, calcula percentuais e monta os cartões da página inicial em HTML.
        rows,filled,staff,totals=stats(c)
        pending=len(rows)-filled
        completion=round(100*filled/len(rows)) if rows else 0
        cards=''.join(f'<div class="metric"><span>{h(label)}</span><strong>{h(value)}</strong></div>' for label,value in [
            ('Unidades cadastradas',len(rows)),('Fichas atualizadas',filled),
            ('Aguardando levantamento',pending),('Levantamento concluído',f'{completion}%')])
        groups=''
        # Faz um cartão de progresso para cada uma das três áreas.
        for i,(key,title) in enumerate(GROUPS.items(),1):
            group_rows=[r for r in rows if r['group_key']==key]
            done=sum(bool(r['updated_at']) for r in group_rows)
            percentage=round(100*done/len(group_rows)) if group_rows else 0
            groups+=f'''<a class="overview-group-card" href="/group/{key}"><span class="group-icon">{i:02d}</span><strong>{h(title)}</strong><span class="overview-group-count">{done} de {len(group_rows)} atualizadas <b>{percentage}%</b></span><span class="overview-progress" aria-hidden="true"><span style="width:{percentage}%"></span></span><small>{len(group_rows)-done} pendentes <span aria-hidden="true">↗</span></small></a>'''
        # Busca as quatro fichas com as datas de atualização mais recentes e seus analistas.
        recent=c.execute('''SELECT u.*,p.display_name AS editor FROM units u
            LEFT JOIN users p ON p.id=u.updated_by WHERE u.updated_at IS NOT NULL
            ORDER BY u.updated_at DESC LIMIT 4''').fetchall()
        recent_html=''.join(f'''<a class="activity-row" href="/unit/{r['id']}"><span><strong>{h(r['name'])}</strong><small>{h(GROUPS[r['group_key']])} · {h(r['editor'] or 'Analista')}</small></span><time>{h(reports.report_date(r['updated_at']))}</time></a>''' for r in recent) or '<p class="muted">Nenhuma ficha atualizada ainda.</p>'
        # Junta quantidades dos andares para o painel "Dados já levantados".
        collected=''.join(f'<div><span>{h(label)}</span><strong>{h(value)}</strong></div>' for label,value in [
            ('Profissionais nos postos',sum(staff.values())),
            ('Câmeras informadas',totals['camera_local']+totals['camera_remote']),
            ('Leitoras de crachá',totals['badge_readers']),
            ('Leitores faciais',totals['face_readers']),
            ('Catracas',totals['turnstiles']),('Alarmes',totals['alarms'])])
        hero=f'''<section class="hero overview-hero"><div><div class="eyebrow">Visão geral · inventário tático</div><h1>Inventário tático em andamento.</h1><p>Acompanhe o preenchimento das unidades e consulte as fichas por área de atuação.</p><div class="hero-actions"><a class="button" href="#areas">Ver áreas de atuação ↗</a><a class="button outline" href="/report.pdf">Baixar relatório consolidado</a></div></div><div class="hero-status"><span>Progresso geral</span><strong>{filled} <small>de {len(rows)}</small></strong><p>fichas atualizadas</p><div class="hero-track" role="progressbar" aria-label="Fichas atualizadas" aria-valuemin="0" aria-valuemax="100" aria-valuenow="{completion}"><span style="width:{completion}%"></span></div><small>{completion}% concluído · {pending} pendentes</small></div></section>'''
        body=f'''{hero}<section class="metrics overview-metrics" aria-label="Indicadores gerais">{cards}</section><section class="overview-areas" id="areas"><div class="section-title"><h2>Progresso por área</h2><p>Abra uma área para consultar as unidades e continuar o levantamento.</p></div><div class="overview-group-grid">{groups}</div></section><div class="overview-lower"><section><div class="section-title"><h2>Dados já levantados</h2><p>Quantidades registradas nas fichas até agora.</p></div><div class="panel collected-panel">{collected}<p>Dados de {filled} de {len(rows)} fichas atualizadas. Os totais crescerão conforme os analistas preencherem as unidades.</p></div></section><section><div class="section-title"><h2>Atualizações recentes</h2><p>Fichas modificadas pelos analistas.</p></div><div class="panel overview-activity">{recent_html}</div></section></div>'''
        self.page(body,'Visão geral',user=user,csrf=csrf)
    def group(self,c,user,csrf,key,notice='',status=200):
        # Monta a área de atuação: indicadores, filtros, galeria e formulário de novo prédio.
        # Os atributos data-search e data-status alimentam os filtros em static/app.js.
        rows,filled,staff,totals=stats(c,key)
        completion=round(100*filled/len(rows)) if rows else 0
        cards=''.join(f'<div class="metric"><span>{label}</span><strong>{value}</strong></div>' for label,value in [
            ('Unidades',len(rows)),('Atualizadas',filled),('Pendentes',len(rows)-filled)])
        progress=f'''<div class="metric progress-metric"><span>Levantamento concluído</span><strong>{completion}%</strong><div class="progress-track" role="progressbar" aria-label="Fichas atualizadas" aria-valuenow="{completion}" aria-valuemin="0" aria-valuemax="100"><span style="width:{completion}%"></span></div><small>{filled} de {len(rows)} fichas atualizadas</small></div>'''
        items=''.join(f'''<a class="unit-tile" data-status="{'updated' if r['updated_at'] else 'pending'}" data-search="{h((r['name']+' '+r['code']+' '+(r['city'] or '')+' '+(r['state'] or '')).casefold())}" href="/unit/{r['id']}"><div class="tile-top"><span class="unit-symbol">{h(r['name'][:1])}</span><span class="badge {'done' if r['updated_at'] else 'pending'}">{'Atualizada' if r['updated_at'] else 'Pendente'}</span></div><strong>{h(r['name'])}</strong><small>{h(' · '.join(x for x in [r['city'],r['state']] if x)) or 'Localização não informada'}</small><div class="tile-bottom"><span>Código {h(r['code'])}</span><span aria-hidden="true">↗</span></div></a>''' for r in rows)
        body=f'''<div class="page-heading"><div class="eyebrow">Área de atuação</div><h1>{h(GROUPS[key])}</h1><p>Ficha tática padronizada para cada unidade.</p><a class="button outline" href="/report.pdf?group={key}">Baixar PDF desta área</a></div><section class="metrics group-metrics">{cards}{progress}</section><section class="panel group-units"><div class="list-toolbar"><div><h2>Unidades</h2><p class="muted">Consulte ou complete as fichas desta área.</p></div><div class="unit-tools"><label>Buscar unidade<input id="unit-search" type="search" placeholder="Nome, código ou cidade"></label><label>Situação<select id="status-filter"><option value="all">Todas</option><option value="pending">Pendentes</option><option value="updated">Atualizadas</option></select></label></div></div><details class="create-unit"><summary>+ Adicionar prédio nesta área</summary><form action="/group/{key}/create" method="post"><input type="hidden" name="csrf" value="{h(csrf)}"><div class="create-grid"><label>Nome da unidade<input name="name" maxlength="150" required placeholder="Ex.: Prédio Administrativo"></label><label>Código da unidade<input name="code" maxlength="60" required placeholder="Ex.: ADM-01"></label><label>Endereço<input name="address" maxlength="250" placeholder="Rua, avenida ou local"></label><label>Cidade<input name="city" maxlength="120"></label><label>Estado<input name="state" maxlength="100"></label></div><p>A nova ficha começa pendente. Depois de criar, complete andares, equipes, controles e fotos.</p><button class="primary">Criar prédio</button></form></details><p id="results-count" class="muted results-count" aria-live="polite"></p><div class="unit-gallery">{items}</div><p id="no-results" class="muted hidden">Nenhuma unidade encontrada para esses filtros.</p></section>'''
        self.page(body,GROUPS[key],status,user,csrf,notice)
    def create_unit(self,c,user,csrf,key,f):
        # Recebe o cadastro do prédio, confere tamanhos e só então tenta gravar unidade e histórico.
        name=f.get('name','').strip();code=f.get('code','').strip()
        address=f.get('address','').strip();city=f.get('city','').strip();state=f.get('state','').strip()
        if not name or not code or len(name)>150 or len(code)>60 or len(address)>250 or len(city)>120 or len(state)>100:
            return self.group(c,user,csrf,key,'Informe nome e código. Confira o tamanho dos demais campos.',400)
        try:
            # Linhas importadas são positivas. Prédios adicionados pelo site recebem números negativos.
            # Isso evita colisões com a planilha inicial; não é o identificador exibido da unidade.
            c.execute('BEGIN IMMEDIATE')
            source_row=min(c.execute('SELECT COALESCE(MIN(source_row),0) FROM units').fetchone()[0],0)-1
            cursor=c.execute('''INSERT INTO units(source_row,code,name,group_key,area,address,city,state,details)
                VALUES(?,?,?,?,?,?,?,?,?)''',
                (source_row,code,name,key,GROUPS[key],address,city,state,
                 json.dumps({'coordinator_phone':DEFAULT_COORDINATOR},ensure_ascii=False)))
            c.execute('INSERT INTO audit(unit_id,actor_id,action,at) VALUES(?,?,?,?)',
                      (cursor.lastrowid,user['id'],'Prédio cadastrado na área '+GROUPS[key],now()))
            c.commit()
        # Se uma etapa falhar, rollback desfaz a operação para não deixar um cadastro incompleto.
        except sqlite3.Error:
            c.rollback()
            return self.group(c,user,csrf,key,'Não foi possível criar o prédio. Tente novamente.',500)
        return self.redirect('/unit/'+str(cursor.lastrowid))
    # Pequena ponte para os módulos de interface obterem o título da área.
    def group_title(self,key):return GROUPS[key]
    # Fornece aos módulos externos a mesma rotina de data/hora usada no servidor.
    def timestamp(self):return now()
    def unit(self,c,user,csrf,id,notice='',status=200):
        # Delega o desenho da ficha ao módulo unit_views, para não concentrar tudo neste arquivo.
        return unit_views.show(self,c,user,csrf,id,notice,status)
    def save_unit(self,c,user,csrf,id,f):
        # Delega a conferência e gravação da ficha para unit_views.save().
        return unit_views.save(self,c,user,csrf,id,f)
    def admin(self,c,user,csrf,notice='',status=200):
        # Desenha lista de contas e formulários de criação/redefinição. Não grava alterações aqui.
        rows=c.execute('SELECT * FROM users ORDER BY role,display_name').fetchall()
        table=''.join(f'''<tr><td><strong>{h(x['display_name'])}</strong><small>{h(x['username'])}</small></td><td>{'Administrador' if x['role']=='admin' else 'Analista'}</td><td><span class="badge {'done' if x['active'] else 'pending'}">{'Ativo' if x['active'] else 'Inativo'}</span></td><td>{('<form method="post" action="/admin/toggle"><input type="hidden" name="csrf" value="'+h(csrf)+'"><input type="hidden" name="id" value="'+str(x['id'])+'"><button class="text-button">'+('Desativar' if x['active'] else 'Ativar')+'</button></form>') if x['id']!=user['id'] else 'Sua conta'}</td></tr>''' for x in rows)
        body=f'''<div class="page-heading"><div class="eyebrow">Administração</div><h1>Acesso dos analistas</h1><p>Crie contas individuais, defina novas senhas e desative acessos quando necessário.</p></div><div class="two-col admin-cols"><section class="panel"><h2>Criar analista</h2><form action="/admin/create" method="post"><input type="hidden" name="csrf" value="{h(csrf)}"><label>Nome<input name="display_name" maxlength="100" required></label><label>Usuário<input name="username" maxlength="50" required></label><label>Senha inicial (mínimo 12 caracteres)<input name="password" type="password" minlength="12" maxlength="128" autocomplete="new-password" required></label><button class="primary">Criar acesso</button></form><hr><h2>Redefinir senha</h2><form action="/admin/reset" method="post"><input type="hidden" name="csrf" value="{h(csrf)}"><label>Usuário<input name="username" required></label><label>Nova senha<input name="password" type="password" minlength="12" maxlength="128" autocomplete="new-password" required></label><button class="secondary">Atualizar senha</button></form></section><section class="panel"><h2>Contas cadastradas</h2><div class="table-wrap"><table><thead><tr><th>Pessoa</th><th>Perfil</th><th>Status</th><th>Ação</th></tr></thead><tbody>{table}</tbody></table></div></section></div>'''
        self.page(body,'Usuários',status,user,csrf,notice)
    def manage_users(self,c,user,csrf,path,f):
        # Trata ações administrativas já autorizadas pela rota: criar, redefinir senha ou ativar/desativar.
        try:
            if path=='/admin/create':
                username=clean_username(f.get('username',''));name=f.get('display_name','').strip()[:100]
                if not name:raise ValueError('Informe o nome do analista.')
                password=f.get('password','');validate_password(password)
                c.execute('INSERT INTO users(username,display_name,role,password_hash,created_at) VALUES(?,?,?,?,?)',
                    (username,name,'analyst',password_hash(password),now()))
                msg='Acesso criado para '+username+'.'
            elif path=='/admin/reset':
                username=clean_username(f.get('username',''));password=f.get('password','');validate_password(password)
                row=c.execute('SELECT id FROM users WHERE username=?',(username,)).fetchone()
                if not row:raise ValueError('Usuário não encontrado.')
                c.execute('UPDATE users SET password_hash=? WHERE id=?',(password_hash(password),row['id']))
                # Uma nova senha também encerra as sessões antigas daquele usuário.
                c.execute('DELETE FROM sessions WHERE user_id=?',(row['id'],))
                msg='Senha atualizada. As sessões anteriores foram encerradas.'
            else:
                # Impede desativar a própria conta e impede alterar outra conta admin por esta ação.
                target=int(f.get('id','0'))
                if target==user['id']:raise ValueError('Você não pode desativar sua própria conta.')
                row=c.execute('SELECT id,active,role FROM users WHERE id=?',(target,)).fetchone()
                if not row or row['role']=='admin':raise ValueError('Conta indisponível para esta ação.')
                c.execute('UPDATE users SET active=? WHERE id=?',(0 if row['active'] else 1,target))
                c.execute('DELETE FROM sessions WHERE user_id=?',(target,))
                msg='Status de acesso atualizado.'
        except (ValueError,sqlite3.IntegrityError) as exc:
            return self.admin(c,user,csrf,str(exc),400)
        c.commit()
        return self.admin(c,user,csrf,msg)

def main():
    # Ponto de partida do terminal: lê o comando escolhido e seus parâmetros (--host, --port etc.).
    parser=argparse.ArgumentParser(description='CISTA — inventário tático')
    parser.add_argument('command',choices=['serve','create-admin','migrate-data'])
    parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--username');parser.add_argument('--name')
    args=parser.parse_args()
    # A migração de pasta é separada de iniciar o site e de criar o administrador.
    if args.command=='migrate-data':
        try:destination=database.migrate_legacy()
        except ValueError as exc:parser.error(str(exc))
        print('Banco copiado e conferido em:',destination)
        print('O arquivo antigo permanece como cópia. Agora inicie a CISTA normalmente.')
        return
    init_db()
    # getpass pede a senha sem mostrá-la enquanto você digita no terminal.
    if args.command=='create-admin':
        username=clean_username(args.username or input('Usuário administrador: '))
        name=(args.name or input('Nome: ')).strip()[:100]
        if not name:parser.error('Nome é obrigatório')
        password=getpass.getpass('Senha (mínimo 12 caracteres): ')
        validate_password(password)
        if password!=getpass.getpass('Repita a senha: '):parser.error('As senhas não coincidem')
        with connect() as c:
            c.execute('INSERT INTO users(username,display_name,role,password_hash,created_at) VALUES(?,?,?,?,?)',
                (username,name,'admin',password_hash(password),now()))
        print('Administrador criado:',username)
    else:
        # Inicia o servidor no IP e porta escolhidos. Ele continua atendendo até você usar Ctrl+C.
        server=ThreadingHTTPServer((args.host,args.port),App)
        print(f'CISTA em http://{args.host}:{args.port} (Ctrl+C para sair)')
        try:server.serve_forever()
        except KeyboardInterrupt:server.server_close()

# Executa main() quando este arquivo é iniciado diretamente; importar app nos testes não inicia o servidor.
if __name__=='__main__':main()
