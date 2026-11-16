"""Lançador local com credencial configurada e entrada manual como alternativa."""
import getpass
import os
import runpy
from pathlib import Path
from of_web.config import database_password


def main():
    temporary_password = not os.environ.get('SISPLAN_PASSWORD')
    try:
        if temporary_password:
            configured = database_password()
            os.environ['SISPLAN_PASSWORD'] = configured or getpass.getpass('Senha do banco SISPLAN (digitacao oculta): ')
            if not os.environ['SISPLAN_PASSWORD']:
                raise SystemExit('Informe a senha para conectar ao SISPLAN.')
        print('Encerre o servidor com Ctrl+C.')
        runpy.run_path(str(Path(__file__).with_name('app.py')), run_name='__main__')
    except KeyboardInterrupt:
        print('\nServidor OF encerrado.')
    finally:
        if temporary_password:
            os.environ.pop('SISPLAN_PASSWORD', None)


if __name__ == '__main__':
    main()
