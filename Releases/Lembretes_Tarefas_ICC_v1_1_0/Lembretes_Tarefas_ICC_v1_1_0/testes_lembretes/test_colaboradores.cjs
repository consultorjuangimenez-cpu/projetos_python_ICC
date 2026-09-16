'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {resolve, bind} = require('../apps/lembretes_tarefas/static/colaboradores.js');
const contacts = [
  {id:1, name:'João Silva', email:'joao@example.com'},
  {id:2, name:'Ana Costa', email:'ana@example.com'},
  {id:3, name:'Ana Costa', email:'outra@example.com'}
];
function input(value='') {
  const handlers = {};
  return {value, textContent:'', addEventListener(type, fn) {handlers[type]=fn;}, fire(type='input') {handlers[type]?.();}};
}
function fields(name='', email='') {
  const values = {name:input(name), email:input(email), id:input(), feedback:input()};
  bind(values, contacts);
  return values;
}
test('nome completo aceita espaços, caixa e acentos', () => {
  assert.equal(resolve('  JOAO   SILVA ', contacts).contact.id, 1);
});
test('nomes iguais exigem seleção explícita pelo e-mail', () => {
  assert.equal(resolve('Ana Costa', contacts).type, 'ambiguous');
  assert.equal(resolve('Ana Costa · outra@example.com', contacts).contact.id, 3);
});
test('digitar o nome completo preenche e-mail e identificador', () => {
  const f=fields();
  f.name.value='joao silva'; f.name.fire();
  assert.equal(f.email.value, 'joao@example.com');
  assert.equal(f.id.value, '1');
  assert.equal(f.name.value, 'João Silva');
});
test('trocar para nome desconhecido ou ambíguo limpa destinatário anterior', () => {
  const f=fields();
  f.name.value='João Silva'; f.name.fire();
  f.name.value='Ana Costa'; f.name.fire();
  assert.equal(f.email.value, ''); assert.equal(f.id.value, '');
  assert.match(f.feedback.textContent, /nomes iguais/);
  f.name.value='Outra pessoa'; f.name.fire();
  assert.equal(f.email.value, '');
});
test('alteração manual do e-mail desvincula a seleção', () => {
  const f=fields();
  f.name.value='João Silva'; f.name.fire();
  f.email.value='manual@example.com'; f.email.fire();
  f.name.fire('change');
  assert.equal(f.id.value, '');
  assert.equal(f.email.value, 'manual@example.com');
});
test('abrir e sair do nome existente conserva e-mail histórico', () => {
  const f=fields('João Silva', 'anterior@example.com');
  f.name.fire('change');
  assert.equal(f.email.value, 'anterior@example.com');
  assert.equal(f.id.value, '');
});
