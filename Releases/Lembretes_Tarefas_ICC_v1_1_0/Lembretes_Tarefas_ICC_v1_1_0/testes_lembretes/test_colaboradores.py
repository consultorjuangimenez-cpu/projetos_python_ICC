"""Cadastro, seleção de destinatários e migração, sem mensagens reais."""
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from test_core import ADMIN, USER, NOW, form
from apps.lembretes_tarefas.store import Store, Conflict
from apps.lembretes_tarefas.validation import collaborator_input, task_input


class CollaboratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'lembretes.sqlite3'
        self.store = Store(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def contact(self, **changes):
        return self.store.save_collaborator({'name':'João Silva', 'email':'joao@example.com', 'active':'1', **changes}, ADMIN, now=NOW)

    def task(self, contact_id=None):
        value = form(collaborator_id=str(contact_id) if contact_id else '')
        return self.store.save(task_input(value, 'America/Cuiaba', NOW), USER, now=NOW)

    def rows(self):
        with self.store.db() as con:
            return {table:[tuple(row) for row in con.execute(f'SELECT * FROM {table} ORDER BY id')]
                    for table in ['tasks','deliveries','history','audit','worker_state']}

    def test_admin_only_and_duplicate_email_rollback(self):
        with self.assertRaises(PermissionError):
            self.store.save_collaborator({'name':'João', 'email':'joao@example.com'}, USER)
        self.contact()
        with self.assertRaisesRegex(ValueError, 'já possui cadastro'):
            self.contact(name='Outra pessoa', email='JOAO@EXAMPLE.COM')
        self.assertEqual(self.store.list_collaborators()[1], 1)
        with self.store.db() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM audit').fetchone()[0], 1)

    def test_same_name_distinct_emails_and_accent_search(self):
        first = self.contact()
        second = self.contact(email='outro@example.com')
        self.assertEqual({c['id'] for c in self.store.list_collaborators(' JOAO  silva ')[0]}, {first, second})
        self.assertEqual(self.store.list_collaborators('OUTRO@')[1], 1)

    def test_selected_id_uses_authoritative_name_and_email(self):
        contact_id = self.contact()
        task_id = self.task(contact_id)
        saved = self.store.get(task_id, USER)
        self.assertEqual((saved['name'], saved['email']), ('João Silva', 'joao@example.com'))

    def test_inactive_or_deleted_selection_is_rejected(self):
        contact_id = self.contact(active='0')
        self.assertEqual(self.store.active_collaborators(), [])
        self.assertEqual(self.store.list_collaborators(active='0')[1], 1)
        for selected in [contact_id, contact_id+100]:
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                self.task(selected)
        self.assertEqual(self.store.list_tasks(USER)[1], 0)

    def test_edit_conflict_and_reactivation(self):
        contact_id = self.contact(active='0')
        data = {'name':'João Silva', 'email':'joao@example.com', 'active':'1'}
        self.store.save_collaborator(data, ADMIN, contact_id, 1, NOW+1)
        with self.assertRaises(Conflict):
            self.store.save_collaborator({**data, 'email':'stale@example.com'}, ADMIN, contact_id, 1, NOW+2)
        self.assertEqual(self.store.get_collaborator(contact_id)['email'], 'joao@example.com')
        self.assertEqual(len(self.store.active_collaborators()), 1)

    def test_directory_changes_preserve_tasks_queue_and_history(self):
        contact_id = self.contact()
        task_id = self.task(contact_id)
        self.store.queue_manual(task_id, USER, 'completed', NOW, 1)
        self.store.success(self.store.claim(NOW), NOW+1, 'Simulação, sem SMTP real.')
        self.store.queue_manual(task_id, USER, 'waiting', NOW+2, 1)
        before = self.rows()
        self.store.save_collaborator({'name':'João atualizado', 'email':'novo@example.com', 'active':'0'}, ADMIN, contact_id, 1, NOW+3)
        after = self.rows()
        for table in ['tasks','deliveries','history']:
            self.assertEqual(before[table], after[table], table)
        self.assertEqual(self.store.claim(NOW+3)['payload']['email'], 'joao@example.com')

    def test_manual_task_stays_compatible(self):
        task = self.store.get(self.task(), USER)
        self.assertEqual(task['email'], 'pessoa@example.com')

    def test_invalid_contact_fields(self):
        for changes in [{'name':''}, {'name':'Pessoa\nOutra'}, {'name':'a'*121}, {'email':'a@example.com\r\nBcc:x@example.com'}, {'active':'2'}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                collaborator_input({'name':'Pessoa', 'email':'a@example.com', 'active':'1', **changes})

    def old_database(self):
        task_id = self.task()
        self.store.queue_manual(task_id, USER, 'old-completed', NOW, 1)
        self.store.success(self.store.claim(NOW), NOW+1, 'Registro anterior simulado.')
        self.store.queue_manual(task_id, USER, 'old-pending', NOW+2, 1)
        with self.store.db(True) as con:
            con.execute('DROP TABLE collaborators')
            con.execute('PRAGMA user_version=1')

    def test_upgrade_v1_preserves_all_old_rows_and_is_idempotent(self):
        self.old_database()
        before = self.rows()
        for _ in range(2):
            self.store = Store(self.path)
            self.assertEqual(self.rows(), before)
            self.assertEqual(self.store.active_collaborators(), [])
        with self.store.db() as con:
            self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0], 2)
        self.contact()

    def test_failed_migration_rolls_back_schema_and_version(self):
        self.old_database()
        before = self.rows()
        schema = Path(__file__).parents[1]/'apps/lembretes_tarefas/schema.sql'
        invalid = schema.read_text(encoding='utf-8')+'\nTHIS IS INVALID SQL;\n'
        with patch.object(Path, 'read_text', return_value=invalid), self.assertRaises(sqlite3.DatabaseError):
            Store(self.path)
        with self.store.db() as con:
            self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0], 1)
            self.assertIsNone(con.execute("SELECT 1 FROM sqlite_master WHERE name='collaborators'").fetchone())
        self.assertEqual(self.rows(), before)


if __name__ == '__main__':
    unittest.main()
