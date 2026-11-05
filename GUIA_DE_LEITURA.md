# Aprendendo a ler a CISTA

Este guia acompanha os comentários em português do código. Você não precisa entender todos os arquivos de uma vez. Comece pelos pequenos e siga uma ação de cada vez.

## 1. As partes do sistema

A CISTA tem uma parte que roda no navegador e outra que roda no computador servidor.

| Parte | O que faz | Onde encontrar |
| --- | --- | --- |
| HTML | Descreve títulos, campos, botões e seções da página | Textos dentro de `app.py`, `unit_views.py` e `floor_views.py` |
| CSS | Define aparência, cores, tamanhos e disposição dos elementos | `static/style.css` |
| JavaScript | Reage aos cliques, cria linhas e organiza os andares antes do envio | `static/app.js` |
| Python | Atende pedidos, verifica regras, consulta e grava os dados, gera PDFs | Arquivos `.py` |
| SQLite | Guarda contas, fichas, fotos e histórico em um arquivo | `data/cista.sqlite3`, caminho antigo ou `CISTA_DB` |
| JSON | Representa listas e conjuntos de dados como texto | `seed.json`, campos complementares e envio dos andares |

O navegador não grava diretamente no SQLite. Ele envia um pedido ao Python, que confere os dados antes de gravar. Adicionar uma linha na tela ainda não salva aquela linha no banco.

## 2. Ordem sugerida para estudar

| Ordem | Arquivo | O que observar |
| --- | --- | --- |
| 1 | `locations.py` | Como uma função recebe dados e devolve um endereço |
| 2 | `contacts.py` | Como uma lista é conferida e contatos incompletos são rejeitados |
| 3 | `floor_views.py` | Como dados viram campos e botões HTML |
| 4 | `static/app.js` | O que acontece ao adicionar andar, departamento, focal ou posto |
| 5 | `floors.py` | Como o servidor confere e grava o inventário dos andares |
| 6 | `unit_views.py` | Como a ficha é montada e como seu salvamento é coordenado |
| 7 | `app.py` | Como o endereço aberto escolhe a ação que será executada |
| 8 | `database.py` e `auth.py` | Como o banco e as credenciais são preparados e consultados |
| 9 | `photos.py` e `reports.py` | Como fotos são recebidas e PDFs são montados |
| 10 | `tests/test_app.py` | Como conferimos automaticamente se os fluxos continuam funcionando |

O CSS pode ser estudado ao lado de qualquer arquivo de interface. Os comentários identificam a região da tela que cada regra atende.

## 3. Como ler os comentários

No Python, um comentário começa com `#`:

```python
# Este texto explica o comando, mas não é executado.
result = []
```

No JavaScript, usamos `//`. No CSS, usamos `/* comentário */`.

Os textos entre três aspas no início de módulos e funções são descrições chamadas *docstrings*. Alguns já existiam em inglês; os comentários em português ao redor explicam a finalidade e as etapas.

`seed.json` não aceita comentários no formato JSON padrão. Seu papel está descrito aqui e em `database.py`. As fontes da pasta `assets` são arquivos de terceiros, com sua licença preservada; não são scripts para estudar ou editar.

## 4. O que acontece quando você inicia o programa

Ao executar `python app.py serve`:

1. `app.py` importa os módulos de que precisa.
2. `main()` lê o comando e os parâmetros do terminal.
3. `init_db()` chama `database.init_db()` para preparar as tabelas e aplicar migrações pendentes.
4. A base inicial é consultada para inserir unidades que ainda não existem; fichas existentes não são substituídas pela planilha inicial.
5. O servidor começa a atender pedidos no IP e na porta escolhidos.

O trecho `if __name__ == '__main__'` significa: execute `main()` quando eu iniciar este arquivo diretamente. Quando os testes importam `app`, esse trecho não inicia o servidor por conta própria.

Outros comandos têm outra finalidade: `create-admin` cria uma conta administrativa; `migrate-data` copia o banco antigo para a pasta de dados, preservando o original.

## 5. O caminho de abrir uma ficha

Imagine que você abre `/unit/1` no navegador:

1. O navegador envia um pedido HTTP chamado **GET**.
2. `App.do_GET()` identifica o endereço e confere a sessão de login.
3. A rota encaminha o pedido para `unit_views.show()`.
4. Essa função consulta o prédio, os andares, os contatos e o histórico.
5. `floor_views.render_floor()` cria o HTML de cada andar.
6. `App.page()` acrescenta marca, menu e rodapé e envia a página ao navegador.
7. O navegador aplica o CSS e executa o JavaScript para os controles interativos.

**Rota** é a associação entre um endereço e a ação que atende aquele endereço.

## 6. O caminho de Salvar ficha

Este é um bom fluxo para acompanhar no código, porque passa pelas principais partes do sistema.

1. O botão dispara o envio do formulário `inventory-form`.
2. O JavaScript percorre os painéis dos andares e lê departamentos, contatos, equipamentos e postos.
3. `JSON.stringify(result)` transforma essa lista em texto e o coloca no campo oculto `floors-json`.
4. O navegador envia um **POST**, isto é, um pedido para processar os dados do formulário.
5. `App.do_POST()` confere o usuário e o identificador CSRF.
6. `unit_views.save()` confere a revisão da ficha e chama `floors.parse()` para validar os andares.
7. O servidor prepara uma transação e confere a revisão novamente antes de gravar.
8. Grava a unidade, substitui seus andares e registra uma entrada no histórico.
9. `commit()` confirma a transação; o navegador é redirecionado à ficha.

**CSRF** é um valor de conferência ligado à sessão e enviado com os formulários. Ele não é a senha e não substitui o login.

**Revisão** é o identificador da entrada mais recente do histórico do prédio. Se outro analista salvou depois de você abrir a ficha, o servidor percebe a diferença e pede recarregamento, em vez de substituir os dados sem avisar.

**Transação** agrupa operações no banco. `commit` confirma; `rollback` desfaz operações ainda não confirmadas. Assim, salvar um prédio e seus andares pode ser tratado como uma operação conjunta.

## 7. Um mesmo dado passa por vários arquivos

Observe a quantidade de câmeras com monitoramento local:

| Lugar | Como aparece | Papel |
| --- | --- | --- |
| `floor_views.py` | Rótulo “Câmeras · monitoramento local” | Desenha o campo |
| HTML do campo | `data-field="camera_local"` | Identifica a chave usada pelo JavaScript |
| `static/app.js` | `floor[input.dataset.field]` | Lê o valor e coloca no objeto do andar |
| `floors.py` | `NUMBERS`, `parse()` e `replace()` | Confere e grava o número |
| Banco | Coluna `camera_local` em `floors` | Guarda o número após o envio |
| `reports.py` | `sum_known()` e `floor_card()` | Mostra totais e detalhes no PDF |

Mudar apenas o texto do rótulo não muda a chave interna. Adicionar um novo dado exige cuidar do caminho inteiro, inclusive banco, validação e relatório quando aplicável.

## 8. Como os focais estão vinculados

Um prédio possui andares. Cada andar possui uma lista de departamentos e um conjunto de contatos separado por departamento.

Exemplo de dados de um andar:

```json
{
  "label": "Térreo",
  "departments": ["DITI", "RH"],
  "department_contacts": {
    "DITI": [
      {"name": "Pessoa de exemplo A", "contact": "1234"},
      {"name": "Pessoa de exemplo B", "contact": "5678"}
    ],
    "RH": []
  },
  "fm_contacts": [
    {"name": "Responsável de exemplo", "contact": "9012"}
  ]
}
```

Este exemplo é um recorte para estudo, não a representação de todas as colunas. Os nomes são fictícios. Repetir DITI em outro andar não copia automaticamente os focais: o vínculo é local àquele andar.

## 9. Dicionário rápido de Python

| Expressão | Como entender |
| --- | --- |
| `import floors` | Disponibiliza as funções e valores de outro módulo |
| `def nome(...):` | Define uma função, um conjunto de passos que pode ser chamado depois |
| `return valor` | Devolve um resultado e encerra aquela chamada da função |
| `if` / `else` | Escolhe caminhos conforme uma condição |
| `for item in lista` | Repete os passos para cada item de uma lista |
| `[]` | Lista; uma sequência de elementos |
| `{}` | Dicionário; valores identificados por chaves |
| `item['name']` | Lê o valor da chave name |
| `item.get('name', '')` | Lê name ou devolve texto vazio se a chave não existir |
| `None` | Ausência de um valor no Python; no JSON, usamos `null` |
| `try` / `except` | Tenta uma operação e trata os erros previstos |
| `raise ValueError(...)` | Interrompe uma operação com uma mensagem de dado inválido |
| `class App(...)` | Agrupa funções que atendem os pedidos; essas funções são métodos |
| `self` | O objeto que está executando aquele método |
| `f'Texto {valor}'` | Texto com uma parte calculada pelo Python |
| `with ... as c` | Usa um recurso em um bloco, aplicando as regras daquele recurso ao sair |

Em uma conexão SQLite, `with` confirma a transação se tudo terminar bem ou a desfaz em caso de erro; ele não significa, por si só, que a conexão foi fechada. Em `database.migrate_legacy()`, `closing(...)` também garante o fechamento das conexões usadas na cópia.

Algumas linhas usam `;` para reunir mais de um comando. Por exemplo, `a = 1; b = 2` faz duas atribuições. Leia uma instrução de cada vez, mesmo quando estiverem na mesma linha.

Uma expressão como `[f(x) for x in itens]` é uma forma curta de criar uma lista aplicando `f` a cada item. `''.join(...)` une vários textos sem separador.

## 10. Como ler o SQL

SQL é a linguagem dos comandos enviados ao banco pelo Python.

| Comando | Função |
| --- | --- |
| `SELECT` | Consulta registros |
| `WHERE` | Restringe a consulta ou alteração a determinadas condições |
| `INSERT INTO` | Adiciona registros |
| `UPDATE` | Altera registros existentes |
| `DELETE` | Remove registros |
| `CREATE TABLE` | Cria uma tabela |
| `ALTER TABLE` | Altera a estrutura de uma tabela |
| `JOIN` | Combina dados de tabelas relacionadas |
| `ORDER BY` / `LIMIT` | Ordena resultados e limita a quantidade devolvida |

Em `SELECT * FROM units WHERE id=?`, o `?` recebe o valor enviado separadamente em uma tupla. Esse padrão evita montar um comando SQL usando diretamente o texto digitado por alguém.

As principais tabelas são `users` (contas), `sessions` (sessões), `login_attempts` (falhas de login), `units` (prédios), `floors` (andares), `unit_photos` (fotos), `audit` (histórico) e `schema_migrations` (atualizações de estrutura já aplicadas).

## 11. Regras importantes para não interpretar errado

- Campo numérico vazio significa **não informado**. Zero significa **ausência confirmada**.
- “Ficha atualizada” significa que existe uma data de atualização, não que todos os campos foram preenchidos ou validados por outra pessoa.
- Os 20 registros do histórico são um limite de exibição; os anteriores continuam no banco.
- Os contatos maiores são preservados no PDF; o resumo do histórico pode abreviar textos longos.
- Senhas são armazenadas como resultados de cálculo com salt. O sistema compara resultados; não recupera a senha original para conferir o login.
- O PDF usa dados já salvos. Alterações ainda na tela não entram nele.
- As fotos são enviadas por formulários próprios; selecionar um arquivo não é o mesmo que clicar em Enviar foto.
- Vagas antigas continuam armazenadas por compatibilidade, embora não apareçam como campo nem no PDF atual.
- O mapa consulta o Google. Ele não é uma foto própria armazenada no banco da CISTA.

## 12. Aprendendo com alterações pequenas

Faça os exercícios em uma cópia de estudo, usando banco próprio e dados fictícios. Assim você consegue experimentar sem alterar as fichas usadas pela equipe.

Primeiro exercício: procure `Nº de posições de trabalho` em `floor_views.py`, mude apenas o rótulo, reinicie a cópia de estudo e veja o resultado. A chave interna `workstations` deve permanecer igual nesse exercício.

Segundo exercício: procure as variáveis de cor no início do CSS. Mude uma cor na cópia de estudo e observe quais componentes usam `var(--nome)` daquela cor.

Terceiro exercício: leia `contacts.parse_contacts()` e pense em três entradas: linha vazia, só nome e nome com telefone. Depois encontre nos testes como dados inválidos são rejeitados.

Para conferir os fluxos automatizados, execute na pasta da aplicação:

```bash
python -m unittest discover -s tests -v
```

Esses testes usam um banco temporário. Eles são uma forma de detectar regressões, não uma prova de que qualquer alteração futura está correta em todos os casos.

## 13. Arquivos que aparecem sozinhos

`__pycache__` é uma pasta que o Python gera para acelerar importações. Ela não contém o código que você deve editar. O banco e arquivos auxiliares `-wal`/`-shm` também são dados gerados pelo SQLite, não scripts.

O `.gitignore` impede incluir certos arquivos novos no versionamento com Git. Ele não cria backups, não remove arquivos já versionados e não esconde necessariamente esses arquivos no Explorer do VS Code.

O arquivo `requirements.txt` lista as bibliotecas externas instaladas com pip: ReportLab para PDF e Pillow para fotos. Ele agora também possui comentários explicando o papel de cada dependência.
