import datetime
import logging
from decimal import Decimal
from flask import Flask, jsonify, render_template, request
from flask.json.provider import DefaultJSONProvider
from .db import DatabaseUnavailable, read_session
from .repository import Repository, NotFound
from .preview import ValidationError, make_preview

class JSONProvider(DefaultJSONProvider):
    @staticmethod
    def default(value):
        if isinstance(value,Decimal):
            return format(value,'f')
        if isinstance(value,(datetime.date,datetime.datetime)):
            return value.isoformat()
        return DefaultJSONProvider.default(value)

def create_app(session_factory=None):
    app=Flask(__name__,template_folder='../templates',static_folder='../static')
    app.json=JSONProvider(app)
    app.json.ensure_ascii=False
    app.config.update(MAX_CONTENT_LENGTH=128*1024,JSON_SORT_KEYS=False)
    factory=session_factory or read_session

    def company():
        try:
            value=int(request.args.get('empresa','1'))
            if value<1:raise ValueError()
            return value
        except ValueError as exc:
            raise ValidationError('Selecione uma empresa válida.') from exc

    def text_arg(name='q',limit=80):
        value=request.args.get(name,'').strip()
        if len(value)>limit:raise ValidationError('O texto de pesquisa é muito longo.')
        return value

    @app.get('/')
    def index():
        return render_template('of.html')

    @app.get('/api/contexto')
    def context():
        with factory() as session:
            data=Repository(session).context()
        data['somente_leitura']=True
        return jsonify(data)

    @app.get('/api/pedidos')
    def orders():
        with factory() as s:return jsonify(Repository(s).search_orders(text_arg(),company()))

    @app.get('/api/pedidos/<number>')
    def order(number):
        if len(number)>16:raise ValidationError('Número de pedido inválido.')
        with factory() as s:return jsonify(Repository(s).order(number,company()))

    @app.get('/api/produtos')
    def products():
        with factory() as s:return jsonify(Repository(s).search_products(text_arg()))

    @app.get('/api/produtos/<code>')
    def product(code):
        if len(code)>40:raise ValidationError('Código de produto inválido.')
        with factory() as s:return jsonify(Repository(s).product(code))

    @app.get('/api/entidades')
    def entities():
        with factory() as s:return jsonify(Repository(s).search_entities(text_arg()))

    @app.get('/api/ofs')
    def ofs():
        with factory() as s:return jsonify(Repository(s).search_ofs(text_arg(),company()))

    @app.get('/api/ofs/<number>')
    def existing_of(number):
        if len(number)>20:raise ValidationError('Número de OF inválido.')
        with factory() as s:return jsonify(Repository(s).of(number,company()))

    @app.post('/api/conferencia')
    def preview():
        # Só recebe JSON da própria origem; a operação calcula em memória.
        if request.headers.get('Origin') and request.headers['Origin']!=request.host_url.rstrip('/'):
            return jsonify(error='Origem da solicitação inválida.'),403
        payload=request.get_json(silent=True)
        if not isinstance(payload,dict):raise ValidationError('Envie os dados da OF em formato válido.')
        empresa_id=company()
        codigo=payload.get('produto')
        if not isinstance(codigo,str) or not codigo or len(codigo)>40:raise ValidationError('Selecione um produto.')
        if payload.get('pedido') and (not isinstance(payload['pedido'],str)or len(payload['pedido'])>16):raise ValidationError('Pedido inválido.')
        with factory() as s:
            repo=Repository(s)
            prod=repo.product(codigo)
            pedido=repo.order(payload['pedido'],empresa_id) if payload.get('pedido') else None
            context=repo.context()
            faccoes=payload.get('faccoes',{})
            if not isinstance(faccoes,dict) or len(faccoes)>30:
                raise ValidationError('Seleção de facções inválida.')
            selected=payload.get('partes',[])
            if not isinstance(selected,list):raise ValidationError('Seleção de partes inválida.')
            entities={}
            if payload.get('gerar_faccao',True):
                for part in prod['partes']:
                    key=str(part['id'])
                    if key in map(str,selected):
                        codigo=faccoes.get(key,'')
                        if codigo:
                            if not isinstance(codigo,str) or len(codigo)>8:raise ValidationError('Código de facção inválido.')
                            if codigo not in entities:entities[codigo]=repo.entity(codigo)
        if payload.get('deposito') not in {d['codigo']for d in context['depositos']}:raise ValidationError('Depósito não encontrado.')
        if payload.get('periodo') not in {p['codigo']for p in context['periodos']}:raise ValidationError('Período de produção não encontrado.')
        if str(payload.get('tipo_id')) not in {str(t['id'])for t in context['tipos']}:raise ValidationError('Tipo de produção não encontrado.')
        if empresa_id not in {int(e['id'])for e in context['empresas']}:raise ValidationError('Empresa não encontrada.')
        complements=payload.get('complementos',[])
        if not isinstance(complements,list) or any(not isinstance(c,dict) for c in complements):raise ValidationError('Informações complementares inválidas.')
        if any(c.get('codigo') not in {str(x['codigo'])for x in context['complementos']}for c in complements):raise ValidationError('Complemento não encontrado no cadastro.')
        result=make_preview(payload,prod,pedido)
        result['produto']={'codigo':prod['codigo'],'descricao':prod['descricao'],'unidade':prod['unidade']}
        result['pedido']=pedido['numero'] if pedido else None
        result['faccoes']=entities
        return jsonify(result)

    @app.errorhandler(NotFound)
    def not_found(exc):return jsonify(error=str(exc)),404

    @app.errorhandler(ValidationError)
    def validation(exc):return jsonify(error=str(exc)),400

    @app.errorhandler(DatabaseUnavailable)
    def unavailable(exc):
        app.logger.warning('Consulta indisponível: %s',exc)
        return jsonify(error='SISPLAN indisponível. Verifique a conexão e a configuração do servidor.'),503

    @app.errorhandler(Exception)
    def failure(exc):
        from werkzeug.exceptions import HTTPException
        if isinstance(exc,HTTPException):return jsonify(error=exc.description),exc.code
        app.logger.exception('Falha na consulta ao ERP')
        return jsonify(error='Não foi possível concluir a consulta. Tente novamente.'),500

    @app.after_request
    def headers(response):
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='SAMEORIGIN'
        return response
    return app
