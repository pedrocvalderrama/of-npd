"""Configuração local do banco; variáveis do processo têm prioridade."""
import json
import os
from pathlib import Path

LOCAL_CONFIG = Path(__file__).resolve().parent.parent / 'sisplan.local.json'


def database_password():
    if os.environ.get('SISPLAN_PASSWORD'):
        return os.environ['SISPLAN_PASSWORD']
    if not LOCAL_CONFIG.is_file():
        return None
    try:
        config = json.loads(LOCAL_CONFIG.read_text(encoding='utf-8-sig'))
        password = config.get('password') if isinstance(config, dict) else None
        if not isinstance(password, str) or not password:
            raise ValueError('Senha ausente na configuração local.')
        return password
    except (OSError, ValueError) as exc:
        raise ValueError('Verifique o campo password em sisplan.local.json.') from exc
