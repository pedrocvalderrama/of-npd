"""Consultas limitadas e parametrizadas, baseadas no catálogo real do SISPLAN."""
from decimal import Decimal

class NotFound(Exception):
    pass

class Repository:
    def __init__(self, session):
        self.db = session

    def context(self):
        return {
            'empresas': self.db.select('SELECT EMP_ID AS ID, EMP_FANTASIA AS NOME, EMP_NOME AS RAZAO FROM EMPRESA ORDER BY EMP_ID'),
            'depositos': self.db.select("SELECT FIRST 201 CODIGO, DESCRICAO, EMPRESA FROM DEPOSITO_001 WHERE COALESCE(ATIVO,'S')<>'N' ORDER BY CODIGO"),
            'tipos': self.db.select("SELECT ID, DESCRICAO FROM TIPO_001 WHERE AREA='PRO' ORDER BY ID"),
            'periodos': self.db.select("SELECT FIRST 201 PRAZO AS CODIGO, DESCRICAO, DT_INICIO, DT_FIM FROM TABPRZ_001 WHERE COALESCE(ATIVO_PRODUCAO,'N')='S' ORDER BY PRAZO"),
            'cores': self.db.select("SELECT FIRST 501 COR AS CODIGO, DESCRICAO FROM CADCOR_001 WHERE COALESCE(INATIVO,'N')<>'S' ORDER BY COR"),
            'complementos': self.db.select('SELECT FIRST 201 CODIGO, CAMPO, DESCRICAO, VALOR, ATIVO FROM OFPADRAO_001 ORDER BY CODIGO'),
            'status_producao': self.db.select("SELECT FIRST 20 STATUS, TELA FROM CONFIGSTATUS WHERE OPERACAO='opProducao' ORDER BY ID"),
        }

    def search_orders(self, term, company):
        base = """SELECT FIRST 31 P.NUMERO, P.CODCLI, E.NOME AS CLIENTE,
                    E.FANTASIA, P.DT_EMISSAO, P.ENTREGA, P.STATUS, P.EMP_ID
                    FROM PEDIDO_001 P LEFT JOIN ENTIDADE_001 E ON E.CODCLI=P.CODCLI
                    WHERE P.EMP_ID=?"""
        params = [company]
        if term:
            if term.isdigit():
                base += ' AND P.NUMERO STARTING WITH ?'
                params.append(term)
            else:
                base += ' AND (E.NOME CONTAINING ? OR E.FANTASIA CONTAINING ?)'
                params += [term, term]
        rows = self.db.select(base+' ORDER BY P.NUMERO DESC', params)
        return {'items': rows[:30], 'more': len(rows)>30}

    def order(self, number, company):
        rows = self.db.select("""SELECT P.NUMERO,P.ID,P.CODCLI,E.NOME AS CLIENTE,
                 E.FANTASIA,P.DT_EMISSAO,P.ENTREGA,P.STATUS,P.OBS,P.DEPOSITO,
                 P.EMP_ID,P.PERIODO,P.PERIODOPROD FROM PEDIDO_001 P
                 LEFT JOIN ENTIDADE_001 E ON E.CODCLI=P.CODCLI
                 WHERE P.NUMERO=? AND P.EMP_ID=?""", (number, company))
        if not rows:
            raise NotFound('Pedido não encontrado na empresa selecionada.')
        order = rows[0]
        order['itens'] = self.db.select("""SELECT I.ID,I.CODIGO,P.DESCRICAO,P.UNIDADE,
            I.COR, C.DESCRICAO AS DESC_COR,I.TAM,I.QTDE,I.QTDE_ORIG,I.QTDE_F,
            I.QTDE_CANC,I.ORDEM,I.DT_ENTREGA,I.DEPOSITO FROM PED_ITEN_001 I
            LEFT JOIN PRODUTO_001 P ON P.CODIGO=I.CODIGO
            LEFT JOIN CADCOR_001 C ON C.COR=I.COR
            WHERE I.NUMERO=? ORDER BY I.ORDEM,I.ID""", (number,))
        return order

    def search_products(self, term):
        sql = "SELECT FIRST 31 CODIGO,DESCRICAO,UNIDADE,ATIVO,ID FROM PRODUTO_001 WHERE COALESCE(ATIVO,'S')<>'N'"
        params = []
        if term:
            sql += ' AND (CODIGO STARTING WITH ? OR DESCRICAO CONTAINING ?)'
            params = [term, term]
        rows = self.db.select(sql+' ORDER BY CODIGO', params)
        return {'items': rows[:30], 'more': len(rows)>30}

    def search_entities(self, term):
        sql = 'SELECT FIRST 31 CODCLI AS CODIGO,NOME AS DESCRICAO,FANTASIA,ID FROM ENTIDADE_001'
        params = []
        if term:
            sql += ' WHERE CODCLI STARTING WITH ? OR NOME CONTAINING ? OR FANTASIA CONTAINING ?'
            params = [term, term, term]
        rows = self.db.select(sql+' ORDER BY CODCLI', params)
        return {'items': rows[:30], 'more': len(rows)>30}

    def entity(self, code):
        rows = self.db.select('SELECT CODCLI,NOME,FANTASIA,ID FROM ENTIDADE_001 WHERE CODCLI=?', (code,))
        if not rows:
            raise NotFound('Facção/terceiro não encontrado no cadastro de entidades.')
        return rows[0]

    def product(self, code):
        rows = self.db.select("""SELECT CODIGO,DESCRICAO,UNIDADE,ATIVO,FAIXA,ID,
              CODCLI,FORNECEDOR,EMP_ID FROM PRODUTO_001 WHERE CODIGO=?""", (code,))
        if not rows:
            raise NotFound('Produto não encontrado.')
        product = rows[0]
        supplier = self.db.select('SELECT NOME FROM ENTIDADE_001 WHERE CODCLI=?', (product['fornecedor'] or '',))
        product['fornecedor_nome'] = supplier[0]['nome'] if supplier else ''
        product['partes'] = self.db.select("""SELECT P.ID,P.PARTE,P.DESC_PARTE,P.FLUXO,
            P.MULTIPLO,P.TIPO FROM PRO_FLUXO_001 P WHERE P.CODIGO=? ORDER BY P.ORDEM,P.ID""", (code,))
        product['setores'] = self.db.select("""SELECT S.PARTE,S.FLUXO,S.SETOR,S.ORDEM,S.DIAS,
            S.OBS,S.TERCEIRO,C.DESCRICAO FROM PRO_FLUXO_SETOR_001 S
            LEFT JOIN CADFLUXO_001 C ON C.CODIGO=S.SETOR
            WHERE S.CODIGO=? ORDER BY S.PARTE,S.FLUXO,S.ORDEM,S.ID""", (code,))
        # IDs da ficha não são globais: preservar também produto e ordem/ID_CONS.
        product['ficha'] = self.db.select("""SELECT F.ID,F.ID_CONS,F.INSUMO,F.TIPO,
            F.APLICACAO,F.PARTE,F.SETOR,F.FAIXA,F.ORDEM,F.CONSUMO,F.CONSUMO_UNIT,
            F.DESPERDICIO,F.VERSAO,
            COALESCE(M.DESCRICAO,P.DESCRICAO) AS DESCRICAO,
            COALESCE(M.UNIDADE,P.UNIDADE) AS UNIDADE
            FROM PCPFT2_001 F
            LEFT JOIN MATERIAL_001 M ON M.CODIGO=F.INSUMO AND F.TIPO='M'
            LEFT JOIN PRODUTO_001 P ON P.CODIGO=F.INSUMO AND F.TIPO='P'
            WHERE F.CODIGO=? ORDER BY F.ORDEM,F.ID""", (code,))
        product['combinacoes'] = self.db.select("""SELECT INSUMO,COR,COR_I,APLICACAO,
              SETOR,FAIXA,ORDEM,ID FROM PCPFT3_001 WHERE CODIGO=? ORDER BY ORDEM,ID""", (code,))
        sizes = self.db.select('SELECT FIRST 1 * FROM PCPFAIXA_001 WHERE FAIXA=?', (product['faixa'] or '',))
        product['tamanhos'] = list(dict.fromkeys(str(v).strip() for key,v in (sizes[0] if sizes else {}).items()
            if key.startswith('tam') and key[3:].isdigit() and v is not None and str(v).strip()))
        return product

    def search_ofs(self, term, company):
        sql = """SELECT FIRST 31 O.NUMERO,O.CODIGO,P.DESCRICAO,O.PEDIDO,O.CODCLI,
            O.DT_INICIO,O.DT_FINAL,O.DATA_CAD,O.ATIVOS,O.FINALIZADO,O.USUARIO
            FROM OF1_001 O LEFT JOIN PRODUTO_001 P ON P.CODIGO=O.CODIGO WHERE O.EMP_ID=?"""
        params = [company]
        if term:
            sql += ' AND (O.NUMERO STARTING WITH ? OR O.PEDIDO=? OR O.CODIGO STARTING WITH ?)'
            params += [term, term, term]
        rows = self.db.select(sql+' ORDER BY O.NUMERO DESC', params)
        return {'items': rows[:30], 'more': len(rows)>30}

    def of(self, number, company):
        rows = self.db.select("""SELECT O.NUMERO,O.CODIGO,P.DESCRICAO,O.CODCLI,
            E.NOME AS CLIENTE,O.PEDIDO,O.PERIODO,O.DEPOSITO,O.DT_INICIO,O.DT_FINAL,
            O.DATA_CAD,O.ATIVOS,O.USUARIO,O.EMP_ID,O.FINALIZADO,O.OBSERVACAO
            FROM OF1_001 O LEFT JOIN PRODUTO_001 P ON P.CODIGO=O.CODIGO
            LEFT JOIN ENTIDADE_001 E ON E.CODCLI=O.CODCLI
            WHERE O.NUMERO=? AND O.EMP_ID=?""", (number, company))
        if not rows:
            raise NotFound('OF não encontrada na empresa selecionada.')
        item = rows[0]
        item['grade'] = self.db.select('SELECT COR,TAM,QTDE,QTDE_B FROM OF_ITEN_001 WHERE NUMERO=? ORDER BY COR,TAM', (number,))
        item['setores'] = self.db.select("""SELECT S.PARTE,S.SETOR,C.DESCRICAO,S.ORDEM,S.ORDEM_ORIG
            FROM FAC_SETOR_001 S LEFT JOIN CADFLUXO_001 C ON C.CODIGO=S.SETOR
            WHERE S.NUMERO=? ORDER BY S.PARTE,S.ORDEM_ORIG,S.ID""", (number,))
        item['consumos'] = self.db.select("""SELECT C.CODIGO,M.DESCRICAO,M.UNIDADE,
            C.COR,C.SETOR,C.CONSUMO,C.BAIXADO FROM OF_CONSUMOS_001 C
            LEFT JOIN MATERIAL_001 M ON M.CODIGO=C.CODIGO AND C.TIPO='M'
            WHERE C.NUMERO=? ORDER BY C.ID""", (number,))
        return item
