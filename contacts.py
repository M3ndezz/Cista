# CONTATOS: valor inicial do coordenador e conferência das listas de focais e FM.
"""Shared contact defaults and validation for department and FM contacts."""
DEFAULT_COORDINATOR = 'Fabrício Gaban Pletitsch - (11) 94503-7889'
# Este valor é usado no preenchimento inicial; a ficha permite editá-lo depois.


def parse_contacts(items, label):
    # Recebe uma lista como [{"name": "Ana", "contact": "1234"}].
    # "label" informa de qual departamento ou FM veio a lista, para explicar eventuais erros.
    if not isinstance(items, list) or len(items) > 20:
        raise ValueError(f'Informe até 20 contatos para {label}.')
    result = []
    # Analisa cada pessoa e devolve somente registros completos, já sem espaços nas pontas.
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f'Confira os contatos de {label}.')
        name, contact = item.get('name', ''), item.get('contact', '')
        if not isinstance(name, str) or not isinstance(contact, str):
            raise ValueError(f'Confira nome e telefone de {label}.')
        name, contact = name.strip(), contact.strip()
        # Uma linha totalmente vazia é ignorada; uma linha preenchida pela metade é rejeitada.
        if not name and not contact:
            continue
        if not name or not contact or len(name) > 150 or len(contact) > 80:
            raise ValueError(f'Informe nome (até 150 caracteres) e contato (até 80) para {label}.')
        result.append({'name': name, 'contact': contact})
    return result
