"""Conexões exclusivas de leitura. Nenhum numerador, DML ou procedure é exposto."""
import os
import threading
from contextlib import contextmanager
from pathlib import Path
import fdb
from .config import database_password

_api_lock = threading.Lock()
_api_loaded = False

class DatabaseUnavailable(Exception):
    pass

class ReadSession:
    def __init__(self, connection):
        self.connection = connection

    def select(self, sql, params=()):
        if not sql.strip().upper().startswith('SELECT '):
            raise ValueError('A aplicação aceita somente consultas SELECT predefinidas.')
        cur = self.connection.cursor()
        try:
            cur.execute(sql, params)
            names = [d[0].strip().lower() for d in cur.description]
            result = []
            for values in cur.fetchall():
                row = dict(zip(names, values))
                for key, value in row.items():
                    if isinstance(value, fdb.BlobReader):
                        row[key] = value.read()
                    elif isinstance(value, str):
                        row[key] = value.rstrip()
                result.append(row)
            return result
        finally:
            cur.close()

@contextmanager
def read_session():
    global _api_loaded
    try:
        password = database_password()
    except ValueError as exc:
        raise DatabaseUnavailable(str(exc)) from exc
    if not password:
        raise DatabaseUnavailable('Configure SISPLAN_PASSWORD ou sisplan.local.json no servidor da aplicação.')
    dll = os.environ.get('SISPLAN_DLL', r'C:\dev\auto_sisplan\fbclient_x64.dll')
    try:
        with _api_lock:
            if not _api_loaded:
                if not Path(dll).is_file():
                    raise DatabaseUnavailable('Biblioteca cliente do Firebird não localizada.')
                fdb.load_api(dll)
                _api_loaded = True
        conn = fdb.connect(
            host=os.environ.get('SISPLAN_HOST', '192.168.100.168'),
            port=int(os.environ.get('SISPLAN_PORT', '3051')),
            database=os.environ.get('SISPLAN_DATABASE', r'C:\Sisplan\Base\14215F.FDB'),
            user=os.environ.get('SISPLAN_USER', 'SYSDBA'), password=password,
            charset='WIN1252',
            isolation_level=(fdb.isc_tpb_read, fdb.isc_tpb_read_committed,
                             fdb.isc_tpb_rec_version, fdb.isc_tpb_nowait))
    except DatabaseUnavailable:
        raise
    except (fdb.Error, OSError) as exc:
        raise DatabaseUnavailable('Não foi possível conectar ao SISPLAN.') from exc
    try:
        session = ReadSession(conn)
        check = session.select('SELECT MON$READ_ONLY AS READ_ONLY FROM MON$TRANSACTIONS WHERE MON$TRANSACTION_ID=CURRENT_TRANSACTION')
        if not check or check[0]['read_only'] != 1:
            raise DatabaseUnavailable('A conexão não confirmou proteção de leitura.')
        yield session
    finally:
        conn.rollback()
        conn.close()
