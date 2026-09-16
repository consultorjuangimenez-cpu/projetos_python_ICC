'use strict';
document.addEventListener('DOMContentLoaded', () => {
  const contactData = document.querySelector('#collaborator-data');
  if (contactData && window.ICCColaboradores) {
    window.ICCColaboradores.bind({
      name: document.querySelector('#name'), email: document.querySelector('#email'),
      id: document.querySelector('#collaborator-id'), feedback: document.querySelector('#colaborador-feedback')
    }, JSON.parse(contactData.textContent));
  }
  const links = document.querySelector('#links');
  const addLink = document.querySelector('#add-link');
  if (addLink) {
    const add = () => {
      if (links.children.length >= 20) { window.alert('São permitidos até 20 links.'); return; }
      links.append(document.querySelector('#link-template').content.cloneNode(true));
    };
    addLink.addEventListener('click', add);
    if (!links.children.length) add();
    links.addEventListener('click', event => {
      if (event.target.classList.contains('remove-link')) event.target.closest('.link-row').remove();
    });
  }
  const kind = document.querySelector('#kind');
  const mode = document.querySelector('#custom_mode');
  if (kind && mode) {
    const update = () => {
      document.querySelector('#custom-options').hidden = kind.value !== 'custom';
      document.querySelectorAll('[data-custom-mode]').forEach(element => {
        const enabled = kind.value === 'custom' && element.dataset.customMode === mode.value;
        element.hidden = !enabled;
        element.querySelectorAll('input').forEach(input => { input.disabled = !enabled; });
      });
    };
    kind.addEventListener('change', update); mode.addEventListener('change', update); update();
  }
  const priority = document.querySelector('#priority');
  if (priority) {
    const updateDeadline = () => { document.querySelector('#deadline').required = priority.value === 'CRITICA'; };
    priority.addEventListener('change', updateDeadline); updateDeadline();
  }
  const modelSelect = document.querySelector('#task-model');
  const modelData = document.querySelector('#task-model-data');
  if (modelSelect && modelData) {
    const models = JSON.parse(modelData.textContent);
    const applyModel = () => {
      const model = models.find(item => String(item.id) === modelSelect.value);
      if (!model) return;
      document.querySelector('#title').value = model.title;
      document.querySelector('#description').value = model.description;
      links.replaceChildren();
      model.links.forEach(link => {
        const row = document.querySelector('#link-template').content.cloneNode(true);
        row.querySelector('[name="link_label"]').value = link.label;
        row.querySelector('[name="link_value"]').value = link.value;
        links.append(row);
      });
      const rule = model.rule;
      kind.value = rule.kind;
      mode.value = rule.mode || 'days';
      document.querySelector('#interval').value = rule.interval || 1;
      document.querySelector('#monthday').value = rule.monthday || 10;
      document.querySelector('#end_date').value = rule.end_date || '';
      document.querySelector('#max_count').value = rule.max_count || '';
      document.querySelectorAll('[name="weekdays"]').forEach(input => {
        input.checked = (rule.weekdays || []).includes(Number(input.value));
      });
      kind.dispatchEvent(new Event('change'));
      document.querySelector('#model-feedback').textContent = 'Modelo aplicado. Confira as datas e salve a tarefa.';
    };
    modelSelect.addEventListener('change', applyModel);
    const selected = new URLSearchParams(window.location.search).get('model');
    // Não sobrescrever valores reapresentados após um erro de validação.
    if (selected && !document.querySelector('.notice.error')) {
      modelSelect.value = selected; applyModel();
    }
  }
  document.querySelectorAll('form[data-confirm]').forEach(form => {
    form.addEventListener('submit', event => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });
  document.querySelectorAll('.copy-path').forEach(button => {
    button.addEventListener('click', async () => {
      const feedback = document.querySelector('.copy-feedback');
      try {
        await navigator.clipboard.writeText(button.dataset.path);
        feedback.textContent = 'Caminho copiado. Cole no Explorador de Arquivos do Windows.';
      } catch (_) {
        const range = document.createRange();
        range.selectNodeContents(button.parentElement.querySelector('code'));
        const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
        feedback.textContent = 'Caminho selecionado. Pressione Ctrl+C para copiar.';
      }
    });
  });
});
