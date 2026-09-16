'use strict';
(function (root) {
  function normalize(text) {
    return String(text || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().replace(/\s+/g, ' ').toLowerCase();
  }
  function resolve(text, contacts) {
    const query = normalize(text);
    const choice = contacts.find(contact => normalize(contact.name + ' · ' + contact.email) === query);
    if (choice) return {type: 'match', contact: choice};
    const matches = contacts.filter(contact => normalize(contact.name) === query);
    if (matches.length === 1) return {type: 'match', contact: matches[0]};
    return {type: matches.length > 1 ? 'ambiguous' : 'none'};
  }
  function bind(fields, contacts) {
    const {name, email, id, feedback} = fields;
    let lastName = name.value;
    function changed() {
      // Focar ou sair do campo de uma tarefa antiga não troca seu destinatário.
      if (name.value === lastName) return;
      id.value = '';
      email.value = '';
      const result = resolve(name.value, contacts);
      if (result.type === 'match') {
        name.value = result.contact.name;
        email.value = result.contact.email;
        id.value = String(result.contact.id);
        feedback.textContent = 'E-mail preenchido pelo cadastro: ' + result.contact.email;
      } else if (result.type === 'ambiguous') {
        feedback.textContent = 'Há nomes iguais. Selecione a opção com o e-mail correto na lista.';
      } else {
        feedback.textContent = name.value.trim() ? 'Selecione um nome cadastrado ou informe o e-mail manualmente.' : 'Digite o nome e selecione o colaborador.';
      }
      lastName = name.value;
    }
    name.addEventListener('input', changed);
    name.addEventListener('change', changed);
    email.addEventListener('input', () => {
      id.value = '';
      feedback.textContent = 'E-mail informado manualmente para esta tarefa. O cadastro não será alterado.';
    });
  }
  const api = {normalize, resolve, bind};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.ICCColaboradores = api;
})(typeof window !== 'undefined' ? window : null);
