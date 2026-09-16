"""Lê apenas nome/documento do inventário existente; não importa o app de certificados."""
import json
import sqlite3


def certificate_clients(root):
    path = (root / 'dados/apps/certificados/inventario.sqlite3').resolve()
    if not path.is_file():
        return [], 'Inventário de certificados indisponível. O cliente pode ser preenchido manualmente.'
    con = None
    try:
        con = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)
        result = set()
        for (raw,) in con.execute('SELECT payload FROM certs WHERE seen=1'):
            try:
                item = json.loads(raw)
                name = ' '.join(str(item.get('cliente', '')).split())
                document = str(item.get('documento', '')).strip()
                if name:
                    label = name + (' · ' + document if document else '')
                    if len(label) <= 240:
                        result.add(label)
            except (ValueError, TypeError, AttributeError):
                continue
        return sorted(result, key=str.casefold), ''
    except sqlite3.Error:
        return [], 'Não foi possível consultar o inventário. O cliente pode ser preenchido manualmente.'
    finally:
        if con is not None:
            con.close()
