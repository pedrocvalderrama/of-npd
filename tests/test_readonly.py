from contextlib import contextmanager
import pytest
import fdb
from of_web import create_app
from of_web.db import ReadSession, DatabaseUnavailable
import of_web.db as database


def test_read_session_refuses_writes_without_executing():
    class NoCursor:
        def cursor(self):
            pytest.fail('Uma gravação tentou obter cursor.')
    session = ReadSession(NoCursor())
    for sql in ['INSERT INTO OF1_001 (NUMERO) VALUES (?)', 'UPDATE CODIGOS_001 SET PROXIMO=1',
                'DELETE FROM OF1_001', 'EXECUTE PROCEDURE RESERVAR_NUMERO']:
        with pytest.raises(ValueError):
            session.select(sql)


@pytest.mark.parametrize('read_only', [0, 1])
def test_connection_requires_firebird_read_only_transaction(monkeypatch, read_only):
    calls = []
    class Cursor:
        description = [('READ_ONLY',)]
        def execute(self, sql, params):
            calls.append(sql)
        def fetchall(self):
            return [(read_only,)]
        def close(self):
            pass
    class Connection:
        def cursor(self):
            return Cursor()
        def rollback(self):
            calls.append('rollback')
        def close(self):
            calls.append('close')
    def connect(**kwargs):
        assert kwargs['isolation_level'] == (
            fdb.isc_tpb_read, fdb.isc_tpb_read_committed,
            fdb.isc_tpb_rec_version, fdb.isc_tpb_nowait)
        return Connection()
    monkeypatch.setenv('SISPLAN_PASSWORD', 'test-only')
    monkeypatch.setattr(database, '_api_loaded', True)
    monkeypatch.setattr(fdb, 'connect', connect)
    if read_only:
        with database.read_session() as session:
            assert isinstance(session, ReadSession)
    else:
        with pytest.raises(DatabaseUnavailable):
            with database.read_session():
                pytest.fail('Transação sem proteção de leitura foi aceita.')
    assert calls[-2:] == ['rollback', 'close']
    assert 'MON$READ_ONLY' in calls[0]


def test_interface_and_errors_do_not_need_database():
    @contextmanager
    def unavailable():
        raise DatabaseUnavailable('test-only')
        yield
    client = create_app(unavailable).test_client()
    assert client.get('/').status_code == 200
    assert client.get('/api/contexto').status_code == 503
    assert client.post('/api/conferencia', json={}).status_code == 400
    assert client.post('/api/ofs', json={}).status_code == 405
    assert client.post('/api/conferencia', json={}, headers={'Origin': 'https://example.org'}).status_code == 403


def test_conference_only_reads_and_returns_no_reserved_number(monkeypatch):
    calls = []
    class Repo:
        def __init__(self, session):
            pass
        def product(self, codigo):
            calls.append(('product', codigo))
            return {'codigo': codigo, 'descricao': 'Teste', 'unidade': 'UN', 'ativo': 'S',
                    'partes': [], 'setores': [], 'ficha': [], 'combinacoes': []}
        def context(self):
            calls.append(('context',))
            return {'depositos': [{'codigo': '0006'}], 'periodos': [{'codigo': '99'}], 'tipos': [{'id': 5}], 'empresas':[{'id':1}], 'complementos':[]}
    @contextmanager
    def fake_session():
        yield object()
    monkeypatch.setattr('of_web.Repository', Repo)
    client = create_app(fake_session).test_client()
    result = client.post('/api/conferencia', json={
        'produto': 'TESTE', 'inicio': '2026-11-16', 'fim': '2026-11-20',
        'deposito': '0006', 'periodo': '99', 'tipo_id': '5', 'partes': [],
        'gerar_faccao': False, 'gerar_consumos': False,
        'grade': [{'cor': '0', 'tam': '0', 'qtde': '3200'}]})
    assert result.status_code == 200
    assert result.json['conferido']
    assert result.json['numero_of'] is None
    assert result.json['gravacao_habilitada'] is False
    assert calls == [('product', 'TESTE'), ('context',)]
