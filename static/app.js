// Este arquivo roda no navegador. Ele organiza interações; quem grava de fato é o servidor Python.
// DOM é a representação da página que o JavaScript consegue consultar e modificar.
// Espera o HTML estar pronto antes de procurar campos ou conectar botões às ações.
document.addEventListener('DOMContentLoaded', () => {
  // querySelector procura um elemento. # indica id; . indica classe CSS.
  const search = document.querySelector('#unit-search');
  const status = document.querySelector('#status-filter');
  if (search && status) {
    // Só a página da área possui esses filtros. Reaproveitamos este arquivo em outras páginas.
    const filter = () => {
      // Para cada cartão, combina a busca por texto com a situação selecionada.
      // O filtro esconde elementos que já foram carregados; não faz nova consulta ao servidor.
      let visible = 0;
      document.querySelectorAll('.unit-tile').forEach(tile => {
        const matchesText = tile.dataset.search.includes(search.value.trim().toLocaleLowerCase('pt-BR'));
        const matchesStatus = status.value === 'all' || tile.dataset.status === status.value;
        const show = matchesText && matchesStatus;
        // A classe hidden recebe display:none no CSS. O contador considera só os cartões visíveis.
        tile.classList.toggle('hidden', !show);
        if (show) visible++;
      });
      document.querySelector('#no-results').classList.toggle('hidden', visible > 0);
      document.querySelector('#results-count').textContent = visible === 1 ? '1 unidade exibida' : `${visible} unidades exibidas`;
    };
    // input acontece enquanto se digita; change acontece ao escolher outra opção no menu.
    search.addEventListener('input', filter);
    status.addEventListener('change', filter);
    filter();
  }

  // A partir daqui estão as interações da ficha. Sem o formulário, esta parte não precisa executar.
  const form = document.querySelector('#inventory-form');
  if (!form) return;
  const container = document.querySelector('#floors-container');
  // O template é um modelo invisível de andar. Clonar evita reescrever o HTML a cada novo andar.
  const template = document.querySelector('#floor-template');
  const empty = document.querySelector('.empty-floors');
  // Mostra ou esconde o aviso de que ainda não há andares.
  const refreshEmpty = () => empty.classList.toggle('hidden', container.children.length > 0);
  // Retira do modelo uma cópia completa da linha de nome e contato.
  const newContactRow = () => template.content.querySelector('.contact-row').cloneNode(true);
  const addContact = area => {
    // Acrescenta uma linha à lista escolhida e coloca o cursor no novo nome; limite de 20 contatos.
    if (area.children.length >= 20) { alert('Limite de 20 contatos por lista.'); return; }
    const row = newContactRow();
    area.append(row); row.querySelector('.contact-name').focus();
  };
  const addDepartmentBlock = (card, name) => {
    // Cria o painel de focais do novo departamento. dataset.department guarda o vínculo com a tag.
    // textContent coloca texto na tela, sem interpretá-lo como HTML digitado pelo usuário.
    const block = document.createElement('section');
    block.className = 'department-block'; block.dataset.department = name;
    const heading = document.createElement('div'); heading.className = 'department-heading';
    const title = document.createElement('strong'); title.textContent = name;
    const description = document.createElement('span'); description.textContent = 'Focais administrativos';
    heading.append(title, description);
    const rows = document.createElement('div'); rows.className = 'department-contact-rows';
    rows.append(newContactRow());
    const button = document.createElement('button'); button.type = 'button';
    button.className = 'secondary add-department-contact'; button.textContent = '+ Adicionar focal';
    block.append(heading, rows, button); card.querySelector('.department-contacts').append(block);
  };
  const readContacts = (area, card) => {
    // Transforma campos visuais em uma lista de objetos {name, contact}, pronta para o JSON.
    const contacts = [];
    for (const row of area.querySelectorAll('.contact-row')) {
      const name = row.querySelector('.contact-name').value.trim();
      const contact = row.querySelector('.contact-phone').value.trim();
      // Linhas vazias são ignoradas; linhas pela metade abrem o andar e apontam o campo pendente.
      if (!name && !contact) continue;
      if (!name || !contact) {
        card.open = true;
        row.querySelector(name ? '.contact-phone' : '.contact-name').focus();
        throw new Error('Complete nome e telefone / ramal do contato ou remova a linha.');
      }
      contacts.push({name, contact});
    }
    return contacts;
  };

  const addTag = (card, raw) => {
    // Cria a etiqueta e o painel do departamento. trim remove espaços e slice limita o nome.
    const name = raw.trim().slice(0, 60);
    const list = card.querySelector('.tag-list');
    // Impede tags vazias ou repetidas, sem diferenciar maiúsculas de minúsculas.
    if (!name || [...list.querySelectorAll('.tag')].some(tag => tag.dataset.tag.toLocaleLowerCase('pt-BR') === name.toLocaleLowerCase('pt-BR'))) return;
    if (list.children.length >= 30) { alert('Limite de 30 departamentos por andar.'); return; }
    const chip = document.createElement('span');
    chip.className = 'tag'; chip.dataset.tag = name;
    chip.append(document.createTextNode(name));
    const remove = document.createElement('button');
    remove.type = 'button'; remove.className = 'remove-tag'; remove.setAttribute('aria-label', `Remover ${name}`); remove.textContent = '×';
    chip.append(remove); list.append(chip);
    addDepartmentBlock(card, name);
  };
  const flushTag = card => {
    // Converte o que ficou digitado em tags, separando por vírgulas e atualizando o contador do andar.
    const input = card.querySelector('.tag-entry');
    input.value.split(',').forEach(part => addTag(card, part));
    input.value = '';
    card.querySelector('.floor-meta').textContent = `${card.querySelectorAll('.tag').length} departamentos`;
  };

  document.querySelector('#add-floor').addEventListener('click', () => {
    // Adiciona uma cópia do modelo, respeita o máximo de 50 andares e posiciona o cursor no título.
    if (container.children.length >= 50) { alert('Limite de 50 andares por unidade.'); return; }
    const card = template.content.firstElementChild.cloneNode(true);
    container.append(card); refreshEmpty(); card.querySelector('.floor-label').focus();
  });
  container.addEventListener('input', event => {
    // Atualiza o título do painel enquanto o analista digita o nome do andar.
    if (event.target.matches('.floor-label')) {
      event.target.closest('.floor-card').querySelector('.floor-title').textContent = event.target.value.trim() || 'Novo andar';
    }
  });
  container.addEventListener('keydown', event => {
    // Enter ou vírgula finalizam a tag. preventDefault evita que Enter envie a ficha nesse momento.
    if (event.target.matches('.tag-entry') && (event.key === 'Enter' || event.key === ',')) {
      event.preventDefault(); flushTag(event.target.closest('.floor-card'));
    }
  });
  container.addEventListener('focusout', event => {
    // Se a pessoa sair do campo sem pressionar Enter, ainda aproveita o departamento que digitou.
    if (event.target.matches('.tag-entry')) flushTag(event.target.closest('.floor-card'));
  });
  container.addEventListener('click', event => {
    // Um único ouvinte atende botões dos andares existentes e dos adicionados depois.
    // closest encontra o painel do andar ao qual o botão clicado pertence.
    const card = event.target.closest('.floor-card');
    if (!card) return;
    if (event.target.matches('.remove-tag')) {
      // Remover um departamento também remove seus focais da tela; pede confirmação se houver conteúdo.
      const tag = event.target.closest('.tag');
      const block = [...card.querySelectorAll('.department-block')].find(item => item.dataset.department === tag.dataset.tag);
      if (block && [...block.querySelectorAll('input')].some(input => input.value.trim()) &&
          !confirm('Remover o departamento e seus focais administrativos? A mudança só será aplicada ao salvar.')) return;
      if (block) block.remove();
      tag.remove();
      card.querySelector('.floor-meta').textContent = `${card.querySelectorAll('.tag').length} departamentos`;
    }
    // Direciona inclusão/remoção de contatos para a lista correta: departamento ou FM.
    if (event.target.matches('.add-department-contact')) addContact(event.target.closest('.department-block').querySelector('.department-contact-rows'));
    if (event.target.matches('.add-fm-contact')) addContact(card.querySelector('.fm-contact-rows'));
    if (event.target.matches('.remove-contact')) event.target.closest('.contact-row').remove();
    if (event.target.matches('.add-staff')) {
      // Duplica a linha de posto do modelo, com até 30 registros por andar.
      const area = card.querySelector('.floor-staff');
      if (area.children.length >= 30) { alert('Limite de 30 postos por andar.'); return; }
      const row = template.content.querySelector('.staff-row').cloneNode(true);
      area.append(row); row.querySelector('.staff-role').focus();
    }
    // O botão de remover posto usa a classe remove-row para localizar sua linha.
    if (event.target.matches('.remove-row')) event.target.closest('.staff-row').remove();
    if (event.target.matches('.remove-floor')) {
      // A remoção aqui é só na tela. O banco só será alterado ao salvar a ficha.
      if (confirm('Remover este andar da ficha? A mudança só será aplicada ao salvar.')) {
        card.remove(); refreshEmpty();
      }
    }
  });

  form.addEventListener('submit', event => {
    // Antes do envio, percorre os andares e transforma todos os controles dinâmicos em dados.
    const result = [];
    for (const card of container.querySelectorAll('.floor-card')) {
      flushTag(card);
      const label = card.querySelector('.floor-label').value.trim();
      if (!label) { event.preventDefault(); card.open = true; card.querySelector('.floor-label').focus(); return; }
      // Cada objeto floor representa um andar. dataset guarda dados auxiliares do HTML.
      // parking conserva o valor antigo de vagas, sem disponibilizar o campo para edição.
      const floor = {label, departments:[...card.querySelectorAll('.tag')].map(tag => tag.dataset.tag),
        notes:card.querySelector('.floor-notes').value.trim(),
        parking:card.dataset.legacyParking === '' ? null : Number(card.dataset.legacyParking),
        department_contacts:{}, fm_contacts:[],
        is_unassigned:card.dataset.unassigned === 'true' && label === 'A distribuir por andar', staffing:[]};
      try {
        // Os contatos pertencem ao departamento deste andar, mesmo se a mesma tag existir em outro.
        for (const block of card.querySelectorAll('.department-block')) {
          // Define a chave de forma explícita, inclusive se o nome tiver significado especial em JavaScript.
          Object.defineProperty(floor.department_contacts, block.dataset.department, {
            value:readContacts(block, card), enumerable:true, configurable:true
          });
        }
        floor.fm_contacts = readContacts(card.querySelector('.fm-contact-rows'), card);
      } catch (error) {
        // Um contato incompleto cancela o envio e explica o que precisa ser preenchido.
        event.preventDefault(); alert(error.message); return;
      }
      for (const input of card.querySelectorAll('.floor-number')) {
        // Vazio vira null (não informado); Number converte texto numérico, inclusive "0", em número.
        floor[input.dataset.field] = input.value === '' ? null : Number(input.value);
      }
      for (const row of card.querySelectorAll('.staff-row')) {
        // Linhas de posto sem quantidade não entram na lista. Escala "Outra" exige sua descrição.
        const value = row.querySelector('.staff-quantity').value;
        if (value === '') continue;
        const schedule = row.querySelector('.staff-schedule').value;
        const custom = row.querySelector('.staff-custom').value.trim();
        if (schedule === 'Outra' && !custom) {
          event.preventDefault(); card.open = true; row.querySelector('.staff-custom').focus();
          alert('Descreva a carga horária na opção Outra.'); return;
        }
        floor.staffing.push({role:row.querySelector('.staff-role').value, quantity:Number(value), schedule, custom});
      }
      result.push(floor);
    }
    // stringify transforma a lista em texto JSON e o coloca no campo oculto da ficha.
    // O envio normal do formulário leva esse texto ao Python, que valida novamente antes de gravar.
    document.querySelector('#floors-json').value = JSON.stringify(result);
  });
});
