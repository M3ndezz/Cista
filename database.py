# BANCO: escolhe o arquivo SQLite, prepara suas tabelas e preserva compatibilidade com versões anteriores.
"""SQLite location, initial schema and one-time seed import."""
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

import floors
import photos
from contacts import DEFAULT_COORDINATOR

ROOT = Path(__file__).resolve().parent
# Caminhos: ROOT é a pasta do código; LEGACY_DB é o endereço antigo do banco.
# DATA_DB é o endereço usado nas instalações novas. CISTA_DB pode escolher outro caminho.
LEGACY_DB = ROOT / 'cista.sqlite3'
DATA_DB = ROOT / 'data' / 'cista.sqlite3'


def default_path():
    """Keep an old installation on its existing database until migrated."""
    # Prioridade: caminho configurado, banco na pasta data, banco antigo e, por fim, banco novo.
    # Procurar o banco antigo evita abrir uma base vazia após uma atualização.
    configured = os.environ.get('CISTA_DB')
    if configured:
        return Path(configured)
    if DATA_DB.exists():
        return DATA_DB
    if LEGACY_DB.exists():
        return LEGACY_DB
    return DATA_DB


def connect(path):
    # Abre uma conexão com o arquivo SQLite. Uma conexão permite consultar e gravar tabelas.
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=20)
    # Permite escrever row['name'] em vez de depender da posição numérica de cada coluna.
    con.row_factory = sqlite3.Row
    # Ativa os vínculos entre tabelas e espera um pouco quando outra gravação estiver em andamento.
    con.execute('PRAGMA foreign_keys=ON')
    con.execute('PRAGMA busy_timeout=20000')
    return con


def init_db(path):
    # Prepara tabelas e atualizações de estrutura. Não apaga nem recria um banco existente.
    with connect(path) as c:
        # WAL é um modo do SQLite que facilita consultas enquanto outra conexão está gravando.
        c.execute('PRAGMA journal_mode=WAL')
        # Mapa das tabelas criadas abaixo:
        # users = contas; sessions = acessos iniciados; login_attempts = falhas de login;
        # units = prédios; audit = histórico de alterações. IF NOT EXISTS preserva tabelas existentes.
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
          display_name TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','analyst')),
          password_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
          csrf TEXT NOT NULL, expires_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS login_attempts(username TEXT PRIMARY KEY, failures INTEGER NOT NULL, last_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS units(id INTEGER PRIMARY KEY, source_row INTEGER UNIQUE NOT NULL,
          code TEXT NOT NULL, name TEXT NOT NULL, group_key TEXT NOT NULL, area TEXT NOT NULL,
          floor TEXT, address TEXT, complement TEXT, zip TEXT, district TEXT, zone TEXT, city TEXT,
          state TEXT, timezone TEXT, opening TEXT, closing TEXT, phone TEXT,
          security_company TEXT, alarm_company TEXT, details TEXT NOT NULL DEFAULT '{}',
          updated_at TEXT, updated_by INTEGER REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, unit_id INTEGER REFERENCES units(id),
          actor_id INTEGER REFERENCES users(id), action TEXT NOT NULL, at TEXT NOT NULL);
        ''')
        # seed.json contém as unidades iniciais. JSON é um formato de dados, não um script.
        seed = json.loads((ROOT / 'seed.json').read_text(encoding='utf-8'))
        for u in seed:
            # A linha de origem distingue códigos repetidos. INSERT OR IGNORE não substitui fichas existentes.
            c.execute('''INSERT OR IGNORE INTO units(source_row,code,name,group_key,area,floor,address,complement,zip,
                district,zone,city,state,timezone,opening,closing,phone,security_company,alarm_company)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (u['source_row'], u['code'], u['name'], u['group'], u['area'], u['floor'], u['address'],
                 u['complement'], u['zip'], u['district'], u['zone'], u['city'], u['state'], u['timezone'],
                 u['opening'], u['closing'], u['phone'], u['security_company'], u['alarm_company']))
        # Os módulos dos andares e das fotos preparam suas próprias tabelas e colunas.
        floors.migrate(c)
        photos.migrate(c)
        if not c.execute('SELECT 1 FROM schema_migrations WHERE version=5').fetchone():
            # A versão 5 preenche o coordenador uma única vez, sem marcar as fichas como revisadas.
            # A tabela schema_migrations registra que essa etapa já foi concluída.
            for row in c.execute('SELECT id,details FROM units').fetchall():
                details=json.loads(row['details'] or '{}')
                details['coordinator_phone']=DEFAULT_COORDINATOR
                c.execute('UPDATE units SET details=? WHERE id=?',
                          (json.dumps(details,ensure_ascii=False),row['id']))
            c.execute('INSERT INTO schema_migrations(version) VALUES(5)')


def migrate_legacy():
    """Copy a legacy database using SQLite's consistent backup; retain its original."""
    # Este comando só copia o banco padrão antigo. Não altera caminhos personalizados.
    # Também se recusa a substituir um banco que já esteja no destino.
    if os.environ.get('CISTA_DB'):
        raise ValueError('Remova CISTA_DB antes de migrar o banco padrão.')
    if not LEGACY_DB.is_file():
        raise ValueError('Nenhum banco antigo cista.sqlite3 foi encontrado na pasta da aplicação.')
    if DATA_DB.exists():
        raise ValueError('O banco data/cista.sqlite3 já existe. Nenhum arquivo foi substituído.')
    DATA_DB.parent.mkdir(parents=True, exist_ok=True)
    # A cópia usa a operação backup do próprio SQLite, incluindo dados ainda presentes no WAL.
    # O arquivo original permanece no lugar; a integridade da cópia é conferida antes de concluir.
    try:
        with closing(sqlite3.connect(LEGACY_DB)) as source, closing(sqlite3.connect(DATA_DB)) as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('A cópia do banco não passou pela verificação de integridade.')
    # Se houver erro, remove apenas o destino criado por esta tentativa e repassa o erro ao chamador.
    except Exception:
        DATA_DB.unlink(missing_ok=True)
        raise
    return DATA_DB
