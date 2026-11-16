"""Interface local de OF — etapa de consultas e conferência, sem gravação no ERP."""
import os
from of_web import create_app

app=create_app()

if __name__=='__main__':
    from waitress import serve
    host=os.environ.get('OF_HOST','127.0.0.1')
    port=int(os.environ.get('OF_PORT','5080'))
    print(f'OF · consultas e conferência: http://{host}:{port}',flush=True)
    serve(app,host=host,port=port,threads=4,channel_timeout=60)
