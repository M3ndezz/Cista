import http.client
# Testes automatizados simulam um navegador e conferem resultados sem usar o banco real.
# Cada assert compara o que aconteceu com o resultado esperado; falhas indicam algo a investigar.
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import urlencode

import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
import database
from locations import location
from PIL import Image
from contacts import DEFAULT_COORDINATOR

class AppFlowTests(unittest.TestCase):
    # Agrupa cenários de uso. O unittest descobre e executa métodos que começam com test_.
    @classmethod
    def setUpClass(cls):
        # Cria banco e administrador apenas para testes, numa pasta temporária.
        # O servidor usa uma porta livre escolhida pelo sistema e roda em outra thread.
        cls.temp=tempfile.TemporaryDirectory()
        app.DB=Path(cls.temp.name)/'test.sqlite3'
        app.init_db()
        with app.connect() as c:
            c.execute('INSERT INTO users(username,display_name,role,password_hash,created_at) VALUES(?,?,?,?,?)',
                      ('admin','Administrador','admin',app.password_hash('secure password 123'),app.now()))
        cls.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.App)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        # Ao terminar, encerra o servidor de testes e libera os arquivos temporários.
        cls.server.shutdown();cls.server.server_close();cls.temp.cleanup()
    def request(self,method,path,data=None,cookie=None):
        # Faz um pedido HTTP de teste, opcionalmente com formulário e cookie de login.
        # Devolve código de resposta, cabeçalhos e corpo para que cada cenário possa conferir.
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
        headers={}
        if cookie:headers['Cookie']=cookie
        if data is not None:
            headers['Content-Type']='application/x-www-form-urlencoded'
            data=urlencode(data)
        conn.request(method,path,data,headers)
        res=conn.getresponse();body=res.read();result=(res.status,dict(res.getheaders()),body)
        conn.close();return result
    def login(self,username='admin',password='secure password 123'):
        # Entra com a conta fictícia de teste e devolve o cookie usado nos próximos pedidos.
        status,headers,_=self.request('POST','/login',{'username':username,'password':password})
        self.assertEqual(status,303)
        return headers['Set-Cookie'].split(';')[0]
    def photo_request(self,path,cookie,csrf,revision,raw):
        # Monta um envio multipart equivalente ao formulário de fotos do navegador.
        boundary='cista-photo-test-boundary'
        body=b''
        for name,value in [('csrf',csrf),('revision',revision)]:
            body+=(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n').encode()
        body+=(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="predio.png"\r\nContent-Type: image/png\r\n\r\n').encode()+raw+(f'\r\n--{boundary}--\r\n').encode()
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
        conn.request('POST',path,body,{'Cookie':cookie,'Content-Type':f'multipart/form-data; boundary={boundary}'})
        res=conn.getresponse();data=res.read();status=res.status;conn.close()
        return status,data
    def edit_tokens(self,cookie,unit_id=1):
        # Abre a ficha e extrai os campos ocultos CSRF e revisão exigidos para salvar.
        status,_,body=self.request('GET',f'/unit/{unit_id}',cookie=cookie)
        self.assertEqual(status,200)
        return (re.search(rb'name="csrf" value="([^"]+)"',body).group(1).decode(),
                re.search(rb'name="revision" value="([^"]+)"',body).group(1).decode())
    def test_seed_groups_and_duplicate_source_code(self):
        # Confere quantidade inicial por área, códigos repetidos válidos e a função Operador central.
        with app.connect() as c:
            self.assertEqual(dict(c.execute('SELECT group_key,COUNT(*) FROM units WHERE source_row>0 GROUP BY group_key').fetchall()),
                             {'fundacao':41,'cdd':20,'externos':24})
            self.assertEqual(c.execute("SELECT COUNT(*) FROM units WHERE code='Bussocaba'").fetchone()[0],2)
        floor=app.floors.parse(json.dumps([{'label':'Térreo','staffing':[
            {'role':'Operador central','quantity':2,'schedule':'5x2','custom':''}]}]))
        self.assertEqual(floor[0]['staffing'][0]['role'],'Operador central')
    def test_dashboard_progress_and_area_links(self):
        # Confere percentuais, indicadores e links da visão geral, incluindo remoção do bloco antigo.
        cookie=self.login()
        with app.connect() as c:
            total=c.execute('SELECT COUNT(*) FROM units').fetchone()[0]
            updated=c.execute('SELECT COUNT(*) FROM units WHERE updated_at IS NOT NULL').fetchone()[0]
        status,_,body=self.request('GET','/',cookie=cookie)
        self.assertEqual(status,200)
        self.assertIn(b'Progresso geral',body)
        self.assertIn(f'{updated} de {total}'.encode(),body)
        self.assertIn(f'aria-valuenow="{round(100*updated/total)}"'.encode(),body)
        self.assertIn(f'Dados de {updated} de {total} fichas atualizadas'.encode(),body)
        self.assertIn(b'href="#areas"',body)
        self.assertNotIn(b'Para iniciar',body)
        self.assertNotIn(b'class="pending-link"',body)
        for label in ('Leitoras de crachá','Leitores faciais','Catracas','Alarmes'):
            self.assertIn(label.encode(),body)
        self.assertEqual(body.count(b'class="panel collected-panel"'),1)
        for key in app.GROUPS:
            self.assertIn(f'href="/group/{key}"'.encode(),body)
        self.assertEqual(body.count(b'class="overview-group-card"'),3)
    def test_overview_pdf_uses_summary_for_all_areas(self):
        # Baixa o PDF geral e, quando pdftotext está disponível, confere seus textos e colunas.
        cookie=self.login()
        status,headers,pdf=self.request('GET','/report.pdf',cookie=cookie)
        self.assertEqual(status,200)
        self.assertEqual(headers['Content-Type'],'application/pdf')
        self.assertTrue(pdf.startswith(b'%PDF-'))
        if shutil.which('pdftotext'):
            report=subprocess.run(['pdftotext','-','-'],input=pdf,capture_output=True,check=True).stdout.decode()
            self.assertIn('Panorama das unidades',report)
            self.assertIn('Andamento por área',report)
            self.assertIn('Quadro consolidado de prédios',report)
            for title in app.GROUPS.values():
                self.assertIn(title,report)
            for title in ('Nome do prédio','Focal do prédio','Ramal','Nível de risco','Situação / data'):
                self.assertIn(title,report)
            self.assertNotIn('Posições de trabalho',report)
            self.assertNotIn('Acesso principal',report)
    def test_report_location_deduplicates_and_hides_source_row(self):
        # Garante que a localização não repita nomes e que a linha original da planilha não apareça.
        cookie=self.login()
        with app.connect() as c:
            unit=c.execute('SELECT * FROM units WHERE source_row=47').fetchone()
            unit_id=unit['id']
            self.assertEqual(location(unit),'Cidade de Deus, Osasco, São Paulo')
        status,_,body=self.request('GET',f'/unit/{unit_id}',cookie=cookie)
        self.assertEqual(status,200)
        self.assertIn('Cidade de Deus, Osasco, São Paulo'.encode(),body)
        self.assertNotIn(b'linha 47 da base',body)
        status,_,pdf=self.request('GET',f'/report.pdf?unit={unit_id}',cookie=cookie)
        self.assertEqual(status,200)
        if shutil.which('pdftotext'):
            content=subprocess.run(['pdftotext','-','-'],input=pdf,capture_output=True,check=True).stdout.decode()
            self.assertIn('Cidade de Deus, Osasco, São Paulo',content)
            self.assertNotIn('Cidade de Deus, Cidade de Deus',content)
            self.assertNotIn('LINHA 47 DA BASE',content)
    def test_group_gallery_filters_and_new_building(self):
        # Confere a galeria, os filtros e a criação de um prédio, incluindo autorização e histórico.
        cookie=self.login()
        status,_,page=self.request('GET','/group/cdd',cookie=cookie)
        self.assertEqual(status,200)
        self.assertIn(b'id="status-filter"',page)
        self.assertIn(b'class="unit-gallery"',page)
        self.assertIn(b'Levantamento conclu',page)
        csrf=re.search(rb'name="csrf" value="([^"]+)"',page).group(1).decode()
        form={'csrf':csrf,'name':'Prédio de Teste','code':'NOVO-01','address':'Avenida Exemplo',
              'city':'Osasco','state':'São Paulo'}
        self.assertEqual(self.request('POST','/group/cdd/create',form)[0],303)
        self.assertEqual(self.request('POST','/group/cdd/create',{**form,'csrf':'invalid'},cookie)[0],403)
        status,headers,_=self.request('POST','/group/cdd/create',form,cookie)
        self.assertEqual(status,303)
        new_id=int(headers['Location'].split('/')[-1])
        with app.connect() as c:
            unit=c.execute('SELECT * FROM units WHERE id=?',(new_id,)).fetchone()
            self.assertEqual(unit['group_key'],'cdd')
            self.assertLess(unit['source_row'],0)
            self.assertIsNone(unit['updated_at'])
            self.assertIn('Prédio cadastrado',c.execute('SELECT action FROM audit WHERE unit_id=?',(new_id,)).fetchone()[0])
        status,_,page=self.request('GET','/group/cdd',cookie=cookie)
        self.assertEqual(status,200)
        self.assertIn(b'Pr\xc3\xa9dio de Teste',page)
        self.assertIn(b'data-status="pending"',page)
        self.assertIn(b'>21</strong>',page)
        self.assertEqual(self.request('GET',f'/report.pdf?unit={new_id}',cookie=cookie)[0],200)
    def test_photo_upload_replace_and_delete(self):
        # Envia uma imagem pequena criada no teste; confere leitura, rejeição de arquivo inválido,
        # remoção de uma foto e preservação da outra, além da presença no PDF individual.
        cookie=self.login();csrf,revision=self.edit_tokens(cookie)
        self.assertEqual(self.request('GET','/unit/2/photo/exterior')[0],303)
        self.assertEqual(self.request('GET','/unit/2/photo/exterior',cookie=cookie)[0],404)
        img=Image.new('RGB',(32,20),'#3e7191');out=io.BytesIO();img.save(out,format='PNG')
        status,_=self.photo_request('/unit/2/photo/exterior',cookie,csrf,'0',out.getvalue())
        self.assertEqual(status,303)
        status,headers,body=self.request('GET','/unit/2/photo/exterior',cookie=cookie)
        self.assertEqual(status,200);self.assertEqual(headers['Content-Type'],'image/jpeg')
        self.assertTrue(body.startswith(b'\xff\xd8'))
        with app.connect() as c:
            row=c.execute("SELECT width,height FROM unit_photos WHERE unit_id=2 AND photo_type='exterior'").fetchone()
            self.assertEqual(tuple(row),(32,20))
            revision=str(c.execute('SELECT MAX(id) FROM audit WHERE unit_id=2').fetchone()[0])
        self.assertEqual(self.photo_request('/unit/2/photo/exterior',cookie,csrf,revision,b'invalid')[0],400)
        self.assertEqual(self.photo_request('/unit/2/photo/interior',cookie,csrf,revision,out.getvalue())[0],303)
        with app.connect() as c:
            revision=str(c.execute('SELECT MAX(id) FROM audit WHERE unit_id=2').fetchone()[0])
        self.assertEqual(self.request('POST','/unit/2/photo/exterior/delete',{'csrf':csrf,'revision':revision},cookie)[0],303)
        self.assertEqual(self.request('GET','/unit/2/photo/exterior',cookie=cookie)[0],404)
        self.assertEqual(self.request('GET','/unit/2/photo/interior',cookie=cookie)[0],200)
        status,_,pdf=self.request('GET','/report.pdf?unit=2',cookie=cookie)
        self.assertEqual(status,200);self.assertTrue(pdf.startswith(b'%PDF-'))
        if shutil.which('pdftotext'):
            extracted=subprocess.run(['pdftotext','-','-'],input=pdf,capture_output=True,check=True).stdout.decode()
            self.assertIn('Foto interna',extracted)
        status,_,page=self.request('GET','/unit/2',cookie=cookie)
        self.assertEqual(status,200);self.assertIn(b'/unit/2/photo/interior',page)
        self.assertIn(b'Foto externa removida',page)
    def test_auth_admin_edit_and_pdf(self):
        # Exercita login, bloqueio sem CSRF, gravação dos andares, conflito de revisão e PDFs.
        # Também verifica que um analista não recebe as funções administrativas.
        self.assertEqual(self.request('GET','/')[0],303)
        cookie=self.login();csrf,revision=self.edit_tokens(cookie)
        _,_,unit_page=self.request('GET','/unit/1',cookie=cookie)
        self.assertLess(unit_page.index('Registro fotográfico do prédio'.encode()),
                        unit_page.index(b'form="inventory-form">Salvar ficha'))
        self.assertIn(b'data-field="alarms"',unit_page)
        self.assertIn(b'<svg viewBox="0 0 48 48"',unit_page)
        self.assertEqual(self.request('POST','/unit/1',{'csrf':'wrong'},cookie)[0],403)
        floor={'label':'1º andar','departments':['TI','Segurança'], 'workstations':50,
               'staffing':[{'role':'Vigilantes','quantity':2,'schedule':'12x36','custom':''}],
               'camera_local':0,'camera_remote':4,'badge_readers':3,'face_readers':1,
               'turnstiles':2,'parking':5,'alarms':3,'notes':'Acesso principal'}
        form={'csrf':csrf,'revision':revision,'floors_json':json.dumps([floor]),
              'name':'Unidade conferida','extension':'1234'}
        self.assertEqual(self.request('POST','/unit/1',form,cookie)[0],303)
        with app.connect() as c:
            unit=c.execute('SELECT * FROM units WHERE id=1').fetchone();d=json.loads(unit['details'])
            saved=app.floors.load(c,1)[0]
            self.assertEqual(saved['camera_local'],0);self.assertEqual(saved['staffing'][0]['quantity'],2)
            self.assertEqual(saved['alarms'],3)
            self.assertEqual(saved['departments'],['TI','Segurança'])
            self.assertEqual(d['extension'],'1234')
            self.assertEqual(unit['name'],'Unidade conferida')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM audit WHERE unit_id=1').fetchone()[0],1)
        self.assertEqual(self.request('POST','/unit/1',form,cookie)[0],409)
        status,headers,body=self.request('GET','/report.pdf?group=fundacao',cookie=cookie)
        self.assertEqual(status,200);self.assertTrue(body.startswith(b'%PDF-'))
        self.assertEqual(headers['Content-Type'],'application/pdf')
        status,headers,single=self.request('GET','/report.pdf?unit=1',cookie=cookie)
        self.assertEqual(status,200);self.assertTrue(single.startswith(b'%PDF-'))
        self.assertIn('CISTA_unidade_1.pdf',headers['Content-Disposition'])
        self.assertEqual(self.request('GET','/report.pdf?unit=99999',cookie=cookie)[0],404)
        if shutil.which('pdftotext'):
            extracted=subprocess.run(['pdftotext','-','-'],input=body,capture_output=True,check=True).stdout.decode()
            for column in ('Nome do prédio','Categoria','Focal do prédio','Ramal','Nível de risco','Situação / data'):
                self.assertIn(column,extracted)
            self.assertIn('Fundação Bradesco',extracted)
            self.assertIn('Unidade conferida',extracted)
            self.assertIn('Atualizada',extracted)
            self.assertNotIn('Posições de trabalho',extracted)
            self.assertNotIn('Acesso principal',extracted)
            one=subprocess.run(['pdftotext','-','-'],input=single,capture_output=True,check=True).stdout.decode()
            self.assertIn('Unidade conferida',one)
            self.assertIn('1º andar',one)
            self.assertIn('Alarmes',one)
            with app.connect() as c:
                other=c.execute('SELECT name FROM units WHERE id=3').fetchone()[0]
            self.assertNotIn(other,one)
        self.assertEqual(self.request('POST','/admin/create',{'csrf':csrf,'username':'ana','display_name':'Ana',
          'password':'other secure password'},cookie)[0],200)
        analyst=self.login('ana','other secure password')
        self.assertEqual(self.request('GET','/admin',cookie=analyst)[0],404)
        self.assertEqual(self.request('POST','/admin/create',{'csrf':self.edit_tokens(analyst)[0],'username':'x'},analyst)[0],403)

    def test_unit_contacts_and_recent_history(self):
        # Confere contatos e risco, rejeita opções desconhecidas e limita a exibição do histórico a 20.
        cookie=self.login();csrf,revision=self.edit_tokens(cookie)
        form={'csrf':csrf,'revision':revision,'floors_json':'[]','name':'Unidade contatos',
              'floor':'Térreo e 1º ao 3º andar','focal':'Ivan Fernandes',
              'extension':'4321',
              'coordinator_phone':'(11) 94503-7889',
              'risk_level':'Alto','risk_note':'Acesso lateral com pouca visibilidade'}
        self.assertEqual(self.request('POST','/unit/1',form,cookie)[0],303)
        with app.connect() as c:
            u=c.execute('SELECT * FROM units WHERE id=1').fetchone()
            self.assertEqual(u['floor'],form['floor'])
            self.assertEqual(json.loads(u['details'])['focal'],'Ivan Fernandes')
            self.assertEqual(json.loads(u['details'])['risk_level'],'Alto')
            audit=c.execute('SELECT action FROM audit WHERE unit_id=1 ORDER BY id DESC LIMIT 1').fetchone()[0]
            self.assertIn('andares',audit)
            self.assertIn('focal do prédio',audit)
            self.assertIn('nível de risco',audit)
            for n in range(25):
                c.execute('INSERT INTO audit(unit_id,actor_id,action,at) VALUES(?,?,?,?)',
                          (1,1,f'Histórico teste {n}',app.now()))
        status,_,body=self.request('GET','/unit/1',cookie=cookie)
        self.assertEqual(status,200)
        self.assertIn(b'Hist\xc3\xb3rico teste 24',body)
        self.assertNotIn(b'Hist\xc3\xb3rico teste 0',body)
        self.assertEqual(body.count(b'Hist\xc3\xb3rico teste '),20)
        self.assertIn(b'<select name="focal">',body)
        self.assertIn(b'Nome e telefone do coordenador',body)
        self.assertIn(b'Avalia\xc3\xa7\xc3\xa3o de risco',body)
        status,_,summary=self.request('GET','/report.pdf?group=fundacao',cookie=cookie)
        self.assertEqual(status,200)
        if shutil.which('pdftotext'):
            report=subprocess.run(['pdftotext','-','-'],input=summary,capture_output=True,check=True).stdout.decode()
            self.assertIn('Ivan Fernandes',report)
            self.assertIn('4321',report)
            self.assertIn('Alto',report)
            self.assertIn('Atualizada',report)
            self.assertNotIn('Acesso lateral com pouca visibilidade',report)
        csrf,revision=self.edit_tokens(cookie)
        form.update(csrf=csrf,revision=revision,focal='Nome desconhecido')
        self.assertEqual(self.request('POST','/unit/1',form,cookie)[0],400)
        form.update(focal='Ivan Fernandes',risk_level='Extremo')
        self.assertEqual(self.request('POST','/unit/1',form,cookie)[0],400)
        status,_,pdf=self.request('GET','/report.pdf?unit=1',cookie=cookie)
        self.assertEqual(status,200)
        if shutil.which('pdftotext'):
            content=subprocess.run(['pdftotext','-','-'],input=pdf,capture_output=True,check=True).stdout.decode()
            self.assertIn('Ivan Fernandes',content)
            self.assertIn('Térreo e 1º ao 3º andar',content)
            self.assertIn('Acesso lateral com pouca visibilidade',content)

    def test_department_contacts_fm_and_expanded_unit_contacts(self):
        # Salva múltiplos focais ligados a departamentos e FM; confere banco, HTML e PDF.
        # Verifica retirada visual de vagas e rejeição de contatos incompletos ou sem departamento.
        cookie=self.login();csrf,revision=self.edit_tokens(cookie,3)
        people=[{'name':f'Focal administrativo teste {n}', 'contact':f'(11) 99999-{n:04d}'} for n in range(3)]
        floor={'label':'Térreo','departments':['DITI','RH'],
               'department_contacts':{'DITI':people,'RH':[{'name':'Focal RH','contact':'1234'}]},
               'fm_contacts':[{'name':'Responsável FM','contact':'(11) 98888-0000'}],
               'parking':22}
        coordinator=DEFAULT_COORDINATOR+' - contato adicional para emergências administrativas'
        property_contact='Focal Patrimônio teste - (11) 97777-0000'
        form={'csrf':csrf,'revision':revision,'name':'Unidade focais','floors_json':json.dumps([floor]),
              'coordinator_phone':coordinator,'property_contact':property_contact}
        self.assertEqual(self.request('POST','/unit/3',form,cookie)[0],303)
        with app.connect() as c:
            saved=app.floors.load(c,3)[0]
            self.assertEqual(saved['department_contacts']['DITI'],people)
            self.assertEqual(saved['fm_contacts'],floor['fm_contacts'])
            self.assertEqual(saved['parking'],22)
            details=json.loads(c.execute('SELECT details FROM units WHERE id=3').fetchone()[0])
            self.assertEqual(details['coordinator_phone'],coordinator)
            self.assertEqual(details['property_contact'],property_contact)
        _,_,body=self.request('GET','/unit/3',cookie=cookie)
        self.assertNotIn(b'Vagas vinculadas',body)
        self.assertNotIn(b'data-field="parking"',body)
        self.assertIn(b'data-department="DITI"',body)
        self.assertIn(b'Focal administrativo teste 2',body)
        self.assertIn(b'Identifica\xc3\xa7\xc3\xa3o de FM',body)
        status,_,pdf=self.request('GET','/report.pdf?unit=3',cookie=cookie)
        self.assertEqual(status,200)
        if shutil.which('pdftotext'):
            content=subprocess.run(['pdftotext','-','-'],input=pdf,capture_output=True,check=True).stdout.decode()
            normalized=' '.join(content.split())
            for value in (coordinator,property_contact,'Focal administrativo teste 2','Responsável FM'):
                self.assertIn(value,normalized)
            self.assertNotIn('Vagas',content)
            self.assertIn('PROTEÇÃO DE POLOS ADMINISTRATIVOS',content)
        with self.assertRaises(ValueError):
            app.floors.parse(json.dumps([{**floor,'department_contacts':{'OUTRO':people}}]))
        with self.assertRaises(ValueError):
            app.floors.parse(json.dumps([{**floor,'fm_contacts':[{'name':'Sem contato'}]}]))

    def test_coordinator_backfill_runs_once_without_marking_units_updated(self):
        # Confere o preenchimento inicial do coordenador e garante que reiniciar não apague edições futuras.
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'contacts.sqlite3'
            database.init_db(path)
            with database.connect(path) as c:
                rows=c.execute('SELECT details,updated_at FROM units').fetchall()
                self.assertTrue(all(json.loads(row['details'])['coordinator_phone']==DEFAULT_COORDINATOR for row in rows))
                self.assertTrue(all(row['updated_at'] is None for row in rows))
                c.execute("UPDATE units SET details=? WHERE id=1",(json.dumps({'coordinator_phone':'Contato personalizado'}),))
            database.init_db(path)
            with database.connect(path) as c:
                self.assertEqual(json.loads(c.execute('SELECT details FROM units WHERE id=1').fetchone()[0])['coordinator_phone'],'Contato personalizado')

    def test_keyless_embed_is_validated_and_static_map_remains_optional(self):
        # Confere mapa automático, incorporação manual validada e alternativa com chave de teste.
        # Também testa rejeição de um link de outro domínio e ausência de HTML executável colado.
        cookie=self.login()
        status,_,body=self.request('GET','/unit/1',cookie=cookie)
        self.assertEqual(status,200)
        self.assertIn(b'Vista a\xc3\xa9rea',body)
        self.assertIn(b'<iframe class="satellite-map"',body)
        self.assertIn(b'maps.google.com/maps?q=',body)
        self.assertIn(b't=k&amp;z=18&amp;output=embed',body)
        self.assertIn(b'Unidade+conferida',body)
        csrf,revision=self.edit_tokens(cookie)
        f={'csrf':csrf,'revision':revision,'floors_json':'[]','name':'Unidade mapa',
           'map_embed':'<iframe src="https://www.google.com/maps/embed?pb=123&amp;z=18" onload="alert(1)"></iframe>'}
        self.assertEqual(self.request('POST','/unit/1',f,cookie)[0],303)
        status,headers,body=self.request('GET','/unit/1',cookie=cookie)
        self.assertIn(b'<iframe class="satellite-map"',body)
        self.assertIn(b'pb=123&amp;z=18',body)
        self.assertNotIn(b'onload=',body)
        self.assertIn('frame-src https://www.google.com',headers['Content-Security-Policy'])
        csrf,revision=self.edit_tokens(cookie)
        f['csrf']=csrf;f['revision']=revision;f['map_embed']='https://evil.example/maps/embed?pb=1'
        self.assertEqual(self.request('POST','/unit/1',f,cookie)[0],400)
        old=os.environ.get('CISTA_MAPS_STATIC_KEY')
        try:
            os.environ['CISTA_MAPS_STATIC_KEY']='test-key'
            csrf,revision=self.edit_tokens(cookie)
            f['csrf']=csrf;f['revision']=revision;f['map_embed']=''
            self.assertEqual(self.request('POST','/unit/1',f,cookie)[0],303)
            status,headers,body=self.request('GET','/unit/1',cookie=cookie)
            self.assertIn(b'<img class="satellite-map"',body)
            self.assertIn(b'maps.googleapis.com/maps/api/staticmap',body)
            self.assertIn(b'maptype=satellite',body)
            self.assertIn(b'size=640x360',body)
            self.assertIn(b'scale=2',body)
            self.assertIn(b'referrerpolicy="strict-origin-when-cross-origin"',body)
            self.assertNotIn(b'<iframe',body)
            self.assertIn('img-src \'self\' https://maps.googleapis.com',headers['Content-Security-Policy'])
        finally:
            if old is None:os.environ.pop('CISTA_MAPS_STATIC_KEY',None)
            else:os.environ['CISTA_MAPS_STATIC_KEY']=old
        status,_,body=self.request('GET','/unit/1',cookie=cookie)
        self.assertIn(b'maps.google.com/maps?q=',body)

    def test_legacy_inventory_migrates_once(self):
        # Simula dados de uma versão antiga e confere que a migração preserve esses valores uma só vez.
        with app.connect() as c:
            c.execute("UPDATE units SET details=?,updated_at=? WHERE id=2",(
                json.dumps({'staffing':[{'role':'Porteiros','quantity':3,'schedule':'5x2','custom':''}],
                            'camera_local':2,'extension':'25'}),app.now()))
            c.execute('DELETE FROM schema_migrations WHERE version=2')
        app.init_db();app.init_db()
        with app.connect() as c:
            saved=app.floors.load(c,2)
            self.assertEqual(len(saved),1)
            self.assertEqual(saved[0]['label'],'A distribuir por andar')
            self.assertEqual(saved[0]['camera_local'],2)
            self.assertEqual(json.loads(c.execute('SELECT details FROM units WHERE id=2').fetchone()[0])['extension'],'25')

    def test_alarm_column_migrates_existing_floor_database(self):
        # Confere que a etapa de migração dos alarmes pode ser verificada novamente sem duplicar a versão.
        with app.connect() as c:
            c.execute('DELETE FROM schema_migrations WHERE version=3')
        app.init_db();app.init_db()
        with app.connect() as c:
            self.assertIn('alarms',{row[1] for row in c.execute('PRAGMA table_info(floors)')})
            self.assertEqual(c.execute('SELECT COUNT(*) FROM schema_migrations WHERE version=3').fetchone()[0],1)

    def test_database_directory_migration_keeps_legacy_original(self):
        # Usa caminhos temporários: copia o banco antigo, verifica uma conta preservada,
        # mantém o original e rejeita uma segunda cópia que substituiria o destino existente.
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            legacy=root/'cista.sqlite3'
            new=root/'data'/'cista.sqlite3'
            old_legacy,old_new=database.LEGACY_DB,database.DATA_DB
            old_env=os.environ.pop('CISTA_DB',None)
            try:
                database.LEGACY_DB, database.DATA_DB=legacy,new
                database.init_db(legacy)
                with database.connect(legacy) as c:
                    c.execute('INSERT INTO users(username,display_name,role,password_hash,created_at) VALUES(?,?,?,?,?)',
                              ('analista','Teste','analyst','hash','2026-10-23'))
                self.assertEqual(database.default_path(),legacy)
                self.assertEqual(database.migrate_legacy(),new)
                self.assertEqual(database.default_path(),new)
                with database.connect(new) as c:
                    self.assertEqual(c.execute("SELECT COUNT(*) FROM users WHERE username='analista'").fetchone()[0],1)
                self.assertTrue(legacy.exists())
                with self.assertRaises(ValueError):database.migrate_legacy()
            finally:
                database.LEGACY_DB,database.DATA_DB=old_legacy,old_new
                if old_env is not None:os.environ['CISTA_DB']=old_env

# Permite executar este arquivo diretamente; a opção discover do README também encontra os testes.
if __name__=='__main__':unittest.main()
