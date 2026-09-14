"""Opcional: copie para a raiz do portal somente se houver proxy HTTPS local configurado."""
from portal.servidor import application, USUARIOS
from portal.primeiro_admin import configurar
from waitress import serve

if __name__=='__main__':
    configurar(USUARIOS)
    print('Backend do portal em 127.0.0.1:8081; acesso externo somente pelo proxy HTTPS local.')
    serve(application,host='127.0.0.1',port=8081,threads=8,
          trusted_proxy='127.0.0.1',trusted_proxy_count=1,
          trusted_proxy_headers={'x-forwarded-proto','x-forwarded-host','x-forwarded-port'},
          clear_untrusted_proxy_headers=True,max_request_body_size=33*1024*1024)
