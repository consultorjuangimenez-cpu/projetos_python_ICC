'use strict';
document.addEventListener('DOMContentLoaded', () => {
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
