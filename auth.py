# CONTAS E SENHAS: regras reaproveitadas pelo terminal e pelo atendimento das páginas.
"""Account names and password hashing shared by CLI and HTTP handlers."""
import hashlib
import hmac
import secrets

# Este módulo cuida das regras de credenciais. Ele não desenha a tela de login.
# "Hash" é um resultado calculado a partir da senha: não é a senha em texto.


def password_hash(password):
    # Gera um ingrediente aleatório (salt) diferente para cada senha cadastrada.
    # PBKDF2 repete o cálculo 600 mil vezes para tornar tentativas de adivinhação mais caras.
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 600_000)
    return 'pbkdf2_sha256$600000$' + salt.hex() + '$' + digest.hex()


def check_password(password, encoded):
    # Lê o método, a quantidade de repetições, o salt e o resultado guardados no banco.
    try:
        algorithm, iterations, salt, digest = encoded.split('$')
        if algorithm != 'pbkdf2_sha256':
            return False
        # Calcula novamente com a senha digitada e compara os resultados; não "descriptografa" a senha.
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(actual, bytes.fromhex(digest))
    except (ValueError, TypeError):
        return False


def clean_username(value):
    # Remove espaços nas pontas e usa minúsculas, para Ana e ana terem o mesmo identificador.
    value = value.strip().lower()
    if not 3 <= len(value) <= 50 or not all(c.isascii() and (c.isalnum() or c in '._-') for c in value):
        raise ValueError('Usuário: 3 a 50 caracteres, letras, números, ponto, hífen ou sublinhado.')
    return value


def validate_password(password):
    # Rejeita senhas fora dos limites usados tanto no terminal quanto na página de usuários.
    if not 12 <= len(password) <= 128:
        raise ValueError('A senha deve ter entre 12 e 128 caracteres.')
