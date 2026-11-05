# CISTA — inventário tático de unidades

Aplicação interna para o squad **Proteção de Polos Administrativos**. O menu superior abre a visão geral, Fundação Bradesco, Bradesco Cidade de Deus e Bradesco Externos. Todas as unidades usam a mesma ficha.

## Primeiro uso

Requer Python 3.10 ou posterior. Execute em uma máquina ou servidor interno aprovado para receber esses dados:

```bash
python -m pip install -r requirements.txt
python app.py create-admin --username seu.usuario --name "Seu nome"
python app.py serve
```

A primeira execução importa os **85 registros** de `seed.json` para `data/cista.sqlite3`: 41 da Fundação, 20 de Cidade de Deus (linhas 47 a 66 da planilha) e 24 Externos. A criação do administrador pede a senha sem mostrá-la no terminal; não existe senha padrão. Abra `http://127.0.0.1:8765/` e entre com a conta criada.

O administrador cria analistas e define ou redefine senhas na página **Usuários**. Cada analista usa uma conta individual. Alterações nas fichas são registradas com data e usuário. Para abrir na rede interna, publique atrás de um proxy HTTPS aprovado pela sua TI e inicie com `python app.py serve --host 127.0.0.1 --port 8765`; o proxy deve enviar `X-Forwarded-Proto: https`, para que o cookie de sessão seja marcado como Secure. Não exponha a porta Python diretamente à internet.

## Mapa aéreo automático sem chave

A ficha monta automaticamente uma visualização de satélite a partir do nome e dos dados de localização, sem configuração de chave. Após corrigir o endereço, salve para atualizar o mapa. Confira o ponto apresentado em cada prédio: buscas por endereço podem ser imprecisas. O endereço consultado é enviado ao Google quando o mapa é carregado.

A URL automática de incorporação é um recurso do site Google Maps, mas não é o endpoint documentado da Maps Embed API. Ela pode mudar ou deixar de funcionar. Em **Ajustar localização do mapa**, é possível colar o HTML de **Compartilhar → Incorporar um mapa → Copiar HTML** para manter a posição já conferida de uma unidade. O link salvo tem prioridade sobre a busca automática; apague esse campo e salve para voltar ao automático. A visualização personalizada pode usar a camada padrão do mapa, conforme o código copiado.

Os espaços **Foto externa** e **Foto interna** aceitam JPEG ou PNG de até 5 MB cada. Salve a ficha antes de enviar fotos; selecione uma imagem e clique em **Enviar foto**. É possível substituir e remover depois. O servidor normaliza a imagem para JPEG, limita a 1600 × 1200 pixels e armazena no mesmo banco SQLite; o histórico registra cada ação. As imagens entram no PDF individual do prédio, mas não no consolidado geral. Apenas usuários autenticados podem abrir as imagens. Inclua o banco nos backups regulares. As fotos podem conter informações internas: escolha imagens adequadas à circulação entre os analistas cadastrados.

## Imagem de satélite estática opcional

Se a equipe preferir futuramente uma imagem parada gerada automaticamente pelo endereço, pode habilitar a **Maps Static API** em um projeto Google Cloud com faturamento configurado e definir a variável de ambiente `CISTA_MAPS_STATIC_KEY` no servidor. Restrinja a chave à Maps Static API e ao domínio HTTPS da CISTA por referenciador HTTP. O endereço da unidade é enviado ao Google quando a imagem é carregada. O mapa incorporado salvo na ficha tem prioridade sobre esta opção; a imagem estática tem prioridade sobre a busca automática sem chave.

Exemplo para um teste local no PowerShell, antes de executar `python app.py serve`:

```powershell
$env:CISTA_MAPS_STATIC_KEY = "SUA_CHAVE_RESTRITA"
```

A chave é usada no URL da imagem `<img>` no navegador, conforme o modelo da Maps Static API; não a coloque no código-fonte nem use uma chave sem restrições. A imagem tem proporção 16:9, tamanho base 640 × 360 e resolução de saída dupla (`scale=2`), sem marcador ou controles de navegação. Depois de corrigir um endereço na ficha, salve e recarregue a página para atualizar a localização exibida. Se aparecer uma imagem de erro do Google, confira a ativação da API, faturamento e restrições da chave.

## Dados e cópia de segurança

- Em instalações novas, o banco compartilhado fica em `data/cista.sqlite3`. Para escolher outro caminho, defina `CISTA_DB` antes de iniciar. Faça backups regulares com o comando SQLite `.backup` ou com a rotina de backup do servidor; copiar o arquivo enquanto há gravações pode gerar uma cópia incompleta. O `.gitignore` impede o versionamento do banco e dos arquivos gerados, mas não substitui o backup.
- **Se você já tem `cista.sqlite3` na pasta principal:** a CISTA continuará usando esse arquivo automaticamente, sem criar uma base vazia por cima. Para transferi-lo à nova pasta, pare o servidor e execute `python app.py migrate-data`. O comando usa uma cópia consistente do SQLite, verifica a integridade e preserva o arquivo antigo. Ao iniciar novamente, `data/cista.sqlite3` passa a ser o banco usado. Confira as fichas antes de apagar ou arquivar a cópia antiga. Se `CISTA_DB` estiver configurado, mantenha seu caminho atual e não execute essa migração.
- **Atualização da versão anterior:** faça backup do banco existente antes de trocar os arquivos da aplicação. Mantenha o mesmo `cista.sqlite3` ou caminho `CISTA_DB`. Ao iniciar a nova versão, a migração cria a tabela de andares automaticamente. Valores antigos do prédio aparecem uma única vez em **A distribuir por andar**; transfira-os para os pavimentos corretos depois da conferência. Os logins e registros anteriores são preservados.
- A base inicial usa a **linha original** como chave de importação, pois há dois acessos Bussocaba com o mesmo código. Reiniciar a aplicação não sobrescreve fichas já atualizadas.
- Os campos da planilha que ainda não foram levantados permanecem vazios. Em cada andar, `0` confirma ausência de um item, enquanto vazio significa não informado.
- O campo **Andares** na ficha da unidade pode ser editado sem alterar os cartões detalhados dos pavimentos. O antigo telefone importado da planilha permanece no banco, mas deixa de aparecer no formulário; nome e telefone do coordenador podem ser ajustados na ficha.
- O PDF consolidado pode incluir dados táticos sensíveis. Revise os destinatários e o ambiente de armazenamento antes de distribuir.

## Escopo desta versão

- Dashboard com progresso geral, quatro indicadores de preenchimento, avanço por área e atualizações recentes com analista e data. O painel de dados levantados reúne postos, câmeras, leitoras de crachá, leitores faciais, catracas e alarmes, acompanhados da quantidade de fichas atualizadas para contextualizar os totais.
- Cada área apresenta quatro indicadores, incluindo o percentual de fichas atualizadas, e uma galeria responsiva de prédios. A busca por nome, código ou cidade pode ser combinada ao filtro Todas, Pendentes ou Atualizadas.
- Administradores e analistas podem usar **Adicionar prédio nesta área**. Nome e código são obrigatórios; a nova unidade começa pendente, abre sua ficha para preenchimento e entra nos relatórios da área e no consolidado. O identificador interno negativo evita conflito com a importação inicial.
- Busca por unidade, código ou cidade; menu recolhível por andar, tags de departamentos e posições de trabalho.
- Por andar: postos de porteiros, vigilantes, bombeiros ou operador central, com quantidade e escalas 12x36, 5x2, 6x1 ou outra descrição; câmeras com monitoramento local e remoto; leitoras de crachá, leitores faciais, catracas, alarmes e observações. Alarmes são registrados como quantidade por andar; vazio significa não informado e zero confirma ausência. O campo de vagas foi retirado da interface e dos relatórios; os valores históricos permanecem armazenados.
- Cada tag de departamento abre uma lista própria de **focais administrativos** (nome e telefone/ramal), com até 20 contatos. O vínculo pertence ao departamento daquele andar; repetir DITI em outro andar não copia os contatos automaticamente. Remover a tag também remove o vínculo com seus focais, após confirmação quando preenchidos. Abaixo dos postos há **Identificação de FM**, com nome e contato e opção de adicionar mais responsáveis. Esses dados aparecem no PDF individual e são registrados no histórico da ficha ao salvar.
- A ficha possui **Nome e telefone do coordenador** e **Focal Patrimônio (nome - telefone)**, ambos com até 200 caracteres e sem corte de texto no PDF. Nesta atualização o coordenador de todas as unidades existentes é preenchido uma única vez com **Fabrício Gaban Pletitsch - (11) 94503-7889**; alterações posteriores são preservadas. Novos prédios começam com o mesmo contato. O focal do prédio mantém a seleção entre Vitor Aronchi, Ivan Fernandes, Jacson Vieira da Silva e Lucas Capinan de Oliveira.
- A avaliação manual de risco da unidade oferece **Não avaliado**, **Baixo**, **Médio** e **Alto**, com uma observação de até 1.000 caracteres. Esses dados também aparecem no PDF e nas novas entradas do histórico; a aplicação não calcula o risco automaticamente.
- Mapa aéreo automático sem chave e em largura ampliada; ajuste manual por unidade e imagem estática por API opcional.
- Login de administrador e analistas, redefinição e desativação de contas, PDF consolidado geral, por área ou de um prédio específico.
- O PDF individual apresenta resumo, indicadores preenchidos, avaliação de risco, cobertura de câmeras e acessos, inventário por andar e fotos cadastradas. O PDF de cada área é uma tabela resumida com prédio, categoria, focal, ramal, risco e situação com data da última atualização. O PDF geral usa a mesma identidade visual, resume o andamento das três áreas e reúne as unidades na mesma tabela resumida. Os cabeçalhos da tabela se repetem em cada página. O traço “—” representa dado não informado; zero é um registro explícito. Duas edições concorrentes da mesma ficha geram aviso de conflito em vez de sobrescrever uma silenciosamente.
- O histórico de cada unidade exibe as 20 alterações mais recentes, com analista, data e resumo dos campos alterados. Registros anteriores permanecem no banco; edições feitas antes desta versão têm apenas a descrição genérica antiga.
- Os dados e as fotos funcionam para múltiplos usuários conectados ao **mesmo servidor e banco**. Esta versão não inclui outros anexos ou integração com autenticação corporativa.

## Verificação

```bash
python -m unittest discover -s tests -v
```

## Organização para manutenção

Para aprender a ler o código, comece pelo arquivo **GUIA_DE_LEITURA.md**. Os módulos Python, JavaScript, CSS e testes possuem comentários em português. Eles explicam o fluxo dos dados, as regras e os componentes; os nomes internos foram preservados para manter a compatibilidade.

- `app.py`: rotas HTTP, páginas de visão geral e administração, e inicialização do servidor.
- `auth.py`: regras de nomes de usuário e senhas; `contacts.py`: contato padrão e validação de responsáveis; `database.py`: conexão, tabelas, importação inicial e migração do arquivo legado.
- `unit_views.py`, `floor_views.py` e `floors.py`: ficha da unidade, controles da interface e validação do inventário dos andares. `photos.py` cuida das imagens; `reports.py`, dos PDFs; `static/`, do estilo e do JavaScript.
- `tests/` cobre login, edição, fotos, relatórios e migrações. Em novos campos, preserve a distinção entre **vazio** (não informado) e **0** (ausência confirmada), e verifique a gravação e o PDF quando o campo aparecer nele.

Comentários no código devem explicar regras e decisões pouco evidentes, especialmente compatibilidade de dados e validação. A descrição de uso fica neste README; os detalhes da implementação ficam junto do módulo responsável.
