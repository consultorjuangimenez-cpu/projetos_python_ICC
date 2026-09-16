"""Teste opcional de interface: Chromium local, servidor local isolado e banco temporário."""
import os
from pathlib import Path
import unittest
import threading
from werkzeug.serving import make_server, WSGIRequestHandler
from datetime import datetime, timedelta

import test_integracao as integration
from test_core import ADMIN, form
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


@unittest.skipUnless(sync_playwright and os.environ.get('LEMBRETES_TEST_BROWSER') == '1',
                     'Defina LEMBRETES_TEST_BROWSER=1 para validar a interface com Chromium local.')
class BrowserTests(unittest.TestCase):
    setUp=integration.PortalIntegrationTests.setUp
    tearDown=integration.PortalIntegrationTests.tearDown
    login=integration.PortalIntegrationTests.login

    def test_model_autofill_save_filter_complete_and_responsive_layout(self):
        self.login()
        model_id=self.store.save_model(form(model_name='Rotina fiscal',title='Conferência mensal',
            description='Validar os documentos do cliente.',kind='custom',custom_mode='weekdays',weekdays=['0','4'],
            link_label=['Portal','Documentos'],link_value=['https://example.com',r'\\servidor\documentos']),ADMIN)
        with sync_playwright() as driver:
            if not Path(driver.chromium.executable_path).is_file():
                self.skipTest('Chromium não instalado; execute o instalador de navegador do portal.')
            class QuietHandler(WSGIRequestHandler):
                def log_request(self, *args, **kwargs): pass
            server=make_server('127.0.0.1',0,self.client.application,threaded=True,request_handler=QuietHandler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base_url=f'http://127.0.0.1:{server.server_port}'
            browser=driver.chromium.launch(headless=True)
            try:
                page=browser.new_page(viewport={'width':1440,'height':1000})
                errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(base_url+'/login')
                page.locator('[name="username"]').fill('admin')
                page.locator('[name="password"]').fill('teste123')
                page.locator('button[type="submit"]').click()
                page.goto(base_url+'/lembretes/nova?model='+str(model_id))
                self.assertEqual(page.locator('#title').input_value(),'Conferência mensal')
                self.assertEqual(page.locator('#description').input_value(),'Validar os documentos do cliente.')
                self.assertEqual(page.locator('#kind').input_value(),'custom')
                self.assertEqual(page.locator('#custom_mode').input_value(),'weekdays')
                self.assertEqual(page.locator('[name="weekdays"]:checked').count(),2)
                self.assertEqual(page.locator('#links .link-row').count(),2)
                page.locator('#name').fill('Dono da tarefa')
                page.locator('#email').fill('dono@example.com')
                page.locator('#department').fill('Fiscal')
                page.locator('#client').fill('Cliente de teste')
                page.locator('#priority').select_option('CRITICA')
                self.assertTrue(page.locator('#deadline').evaluate('(el) => el.required'))
                when=datetime.now(self.settings.zone)+timedelta(days=7)
                page.locator('#start_date').fill(when.date().isoformat())
                page.locator('#clock').fill('09:00')
                page.locator('#deadline').fill((when+timedelta(days=10)).strftime('%Y-%m-%dT%H:%M'))
                page.locator('#business_day_policy').select_option('next')
                for width in (1440,390):
                    page.set_viewport_size({'width':width,'height':1000})
                    self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'),f'Overflow: {width}')
                page.set_viewport_size({'width':1440,'height':1000})
                screenshot=os.environ.get('LEMBRETES_SCREENSHOT_DIR')
                if screenshot:
                    out=Path(screenshot);out.mkdir(parents=True,exist_ok=True)
                    page.screenshot(path=str(out/'formulario.png'),full_page=True)
                page.get_by_role('button',name='Salvar tarefa',exact=True).click()
                page.wait_for_url('**/tarefas/*')
                self.assertIn('Crítica',page.locator('main').inner_text())
                page.get_by_role('link',name='Editar',exact=True).click()
                self.assertEqual(page.locator('#department').input_value(),'Fiscal')
                self.assertEqual(page.locator('#client').input_value(),'Cliente de teste')
                self.assertEqual(page.locator('#business_day_policy').input_value(),'next')
                page.goto(base_url+'/lembretes/?department=Fiscal&client=Cliente&priority=CRITICA')
                self.assertIn('Conferência mensal',page.locator('tbody').inner_text())
                if screenshot:
                    page.screenshot(path=str(out/'dashboard.png'),full_page=True)
                page.get_by_role('link',name='Conferência mensal',exact=True).click()
                page.get_by_role('link',name='Concluir tarefa',exact=True).click()
                page.get_by_role('button',name='Confirmar: marcar tarefa como concluída',exact=True).click()
                page.wait_for_url('**/tarefas/*')
                self.assertIn('Tarefa concluída',page.locator('main').inner_text())
                self.assertEqual(errors,[])
            finally:
                browser.close()
                server.shutdown();server.server_close();thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
