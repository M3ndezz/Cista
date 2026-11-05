# ENDEREÇOS: monta um texto de localização e evita repetir trechos iguais.
"""Build readable locations from source fields without repeated place names."""

def location(unit, *, name=False, zip_code=False, country=False):
    # Junta partes do endereço. As opções permitem acrescentar nome, CEP e país para o mapa.
    values=([unit['name']] if name else []) + [
        unit['address'],unit['district'],unit['city'],unit['state']]
    if zip_code:values.append(unit['zip'])
    if country:values.append('Brasil')
    # "result" guarda a escrita original; "seen" guarda versões padronizadas para comparar.
    result=[]
    seen=set()
    for value in values:
        value=(value or '').strip()
        # Ignora diferenças de maiúsculas e espaços ao detectar trechos repetidos.
        key=' '.join(value.casefold().split())
        if key and key not in seen:
            result.append(value)
            seen.add(key)
    # Devolve um texto único, separado por vírgulas, para cabeçalhos e pesquisas no mapa.
    return ', '.join(result)
