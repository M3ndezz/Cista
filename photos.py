# FOTOS: recebe, confere, reduz e guarda as imagens externa e interna de cada prédio.
"""Authenticated, size-limited building photo uploads stored with the inventory."""
import io
from email import policy
from email.parser import BytesParser

from PIL import Image, ImageOps, UnidentifiedImageError

TYPES={'exterior':'Foto externa','interior':'Foto interna'}
# Limites: a requisição tem espaço para a imagem e os campos auxiliares do formulário.
# A imagem em si pode ter até 5 MB; o limite de pixels evita imagens excessivamente grandes.
MAX_REQUEST=6*1024*1024
MAX_UPLOAD=5*1024*1024
Image.MAX_IMAGE_PIXELS=20_000_000

def migrate(con):
    # Cria uma tabela com uma foto de cada tipo por prédio. BLOB armazena os bytes da imagem.
    con.execute('''CREATE TABLE IF NOT EXISTS unit_photos(
      unit_id INTEGER NOT NULL REFERENCES units(id) ON DELETE CASCADE,
      photo_type TEXT NOT NULL CHECK(photo_type IN ('exterior','interior')),
      image BLOB NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
      updated_at TEXT NOT NULL, updated_by INTEGER REFERENCES users(id),
      PRIMARY KEY(unit_id,photo_type))''')

def read_upload(handler):
    # Lê o envio multipart, formato usado por formulários com arquivos.
    # Separa a imagem dos campos de segurança csrf e revision antes de processá-la.
    try:length=int(handler.headers.get('Content-Length','0'))
    except ValueError:raise ValueError('Tamanho do envio inválido.')
    content_type=handler.headers.get('Content-Type','')
    if not 0<length<=MAX_REQUEST or not content_type.lower().startswith('multipart/form-data;'):
        raise ValueError('Envie uma imagem JPEG ou PNG de até 5 MB.')
    body=handler.rfile.read(length)
    msg=BytesParser(policy=policy.default).parsebytes(
        b'MIME-Version: 1.0\r\nContent-Type: '+content_type.encode('ascii','strict')+b'\r\n\r\n'+body)
    if not msg.is_multipart():raise ValueError('Formulário de foto inválido.')
    fields={};uploads=[]
    # Percorre as partes do envio e aceita apenas uma imagem dentro do tamanho permitido.
    for part in msg.iter_parts():
        name=part.get_param('name',header='content-disposition')
        if name=='image':uploads.append(part.get_payload(decode=True) or b'')
        elif name in ('csrf','revision'):
            fields[name]=(part.get_payload(decode=True) or b'').decode('utf-8','strict')
    if len(uploads)!=1 or not 0<len(uploads[0])<=MAX_UPLOAD:
        raise ValueError('Selecione uma imagem JPEG ou PNG de até 5 MB.')
    return fields,uploads[0]

def normalize(raw):
    # Abre os bytes como imagem, confere o formato real, corrige rotação e converte para JPEG.
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in ('JPEG','PNG') or source.width*source.height>20_000_000:
                raise ValueError('Use uma imagem JPEG ou PNG de até 20 megapixels.')
            source.load()
            image=ImageOps.exif_transpose(source).convert('RGB')
        # Reduz mantendo a proporção; não estica a foto. A qualidade 82 reduz espaço no banco.
        image.thumbnail((1600,1200),Image.Resampling.LANCZOS)
        out=io.BytesIO();image.save(out,format='JPEG',quality=82,optimize=True)
        return out.getvalue(),image.width,image.height
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError,Image.DecompressionBombWarning) as exc:
        raise ValueError('A imagem não pôde ser lida. Use JPEG ou PNG válido.') from exc

def display(handler,con,unit_id,kind):
    # Busca a imagem do prédio e envia os bytes ao navegador. A rota em app.py já conferiu o login.
    row=con.execute('SELECT image FROM unit_photos WHERE unit_id=? AND photo_type=?',(unit_id,kind)).fetchone()
    if not row:return handler.fail()
    handler.send_bytes(row['image'],'image/jpeg')

def save(handler,con,user,csrf,unit_id,kind,fields,raw=None,remove=False):
    # Confere sessão e existência da unidade; prepara a imagem antes de iniciar a gravação.
    import hmac
    if not hmac.compare_digest(fields.get('csrf',''),csrf):return handler.fail(403,'Sessão inválida. Atualize a página.')
    if not con.execute('SELECT 1 FROM units WHERE id=?',(unit_id,)).fetchone():return handler.fail()
    if raw is not None:
        try:image,width,height=normalize(raw)
        except ValueError as exc:return handler.unit(con,user,csrf,unit_id,str(exc),400)
    # Reserva a escrita e confere a revisão atual. Uma foto enviada de uma ficha antiga gera conflito.
    con.execute('BEGIN IMMEDIATE')
    revision=con.execute('SELECT COALESCE(MAX(id),0) FROM audit WHERE unit_id=?',(unit_id,)).fetchone()[0]
    if fields.get('revision')!=str(revision):
        con.rollback()
        return handler.unit(con,user,csrf,unit_id,'Esta ficha mudou. Atualize a página antes de enviar a foto.',409)
    existing=con.execute('SELECT 1 FROM unit_photos WHERE unit_id=? AND photo_type=?',(unit_id,kind)).fetchone()
    # Remoção apaga a foto daquele tipo. Envio inclui ou substitui somente o espaço escolhido.
    if remove:
        if existing:con.execute('DELETE FROM unit_photos WHERE unit_id=? AND photo_type=?',(unit_id,kind))
        action=f'{TYPES[kind]} removida' if existing else f'{TYPES[kind]} já estava vazia'
    else:
        con.execute('''INSERT INTO unit_photos(unit_id,photo_type,image,width,height,updated_at,updated_by)
            VALUES(?,?,?,?,?,?,?) ON CONFLICT(unit_id,photo_type) DO UPDATE SET
            image=excluded.image,width=excluded.width,height=excluded.height,
            updated_at=excluded.updated_at,updated_by=excluded.updated_by''',
            (unit_id,kind,image,width,height,handler.timestamp(),user['id']))
        action=f'{TYPES[kind]} substituída' if existing else f'{TYPES[kind]} enviada'
    # Guarda quem fez a ação e quando; commit confirma a foto e o histórico na mesma transação.
    con.execute('INSERT INTO audit(unit_id,actor_id,action,at) VALUES(?,?,?,?)',
                (unit_id,user['id'],action,handler.timestamp()))
    con.commit()
    handler.redirect('/unit/'+str(unit_id))
