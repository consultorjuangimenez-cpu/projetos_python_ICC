function showFileName() {
  const input = document.getElementById('pdf_file');
  document.getElementById('fileNameDisplay').textContent = input.files[0]?.name || '';
}
const dropArea = document.querySelector('.drop-area');
if (dropArea) {
  dropArea.addEventListener('dragover', event => event.preventDefault());
  dropArea.addEventListener('drop', event => {
    event.preventDefault();
    const input = document.getElementById('pdf_file');
    if (event.dataTransfer.files.length) {
      input.files = event.dataTransfer.files;
      showFileName();
    }
  });
}
document.querySelectorAll('form[data-download]').forEach(form => {
  form.addEventListener('submit', async event => {
    event.preventDefault();
    let box = form.querySelector('[data-download-result]');
    if (!box) { box = document.createElement('p'); box.dataset.downloadResult = ''; form.append(box); }
    const button = form.querySelector('button[type="submit"],button:not([type])');
    if (button) button.disabled = true;
    box.textContent = 'Processando. Aguarde o download...';
    try {
      const response = await fetch(form.action, {method:'POST', body:new FormData(form)});
      if (!response.ok || !response.headers.get('Content-Disposition')?.includes('attachment')) {
        const text = await response.text();
        throw new Error(response.redirected || response.headers.get('X-Portal-Access') ? 'Entre novamente no portal e repita a operação.' : text.includes('<html') || text.includes('<!DOCTYPE') ? 'O processamento não foi concluído. Confira o arquivo e sua sessão.' : text);
      }
      const blob = await response.blob();
      if (form.dataset.blobUrl) URL.revokeObjectURL(form.dataset.blobUrl);
      const url = URL.createObjectURL(blob); form.dataset.blobUrl = url;
      const disposition = response.headers.get('Content-Disposition') || '';
      const name = disposition.match(/filename="?([^";]+)"?/)?.[1] || 'resultado.xlsx';
      const link = document.createElement('a'); link.href = url; link.download = name;
      link.textContent = 'Baixar ' + name; box.replaceChildren(link); link.click();
    } catch(error) { box.textContent = error.message || 'Falha na comunicação. Tente novamente.'; }
    finally { if (button) button.disabled = false; }
  });
});