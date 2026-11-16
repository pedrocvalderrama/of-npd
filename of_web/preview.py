"""Conferência e cálculo em memória. Nenhuma reserva ou gravação de OF."""
import datetime
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation

class ValidationError(ValueError):
    pass

def quantity(value):
    text = str(value).strip()
    if ',' in text:
        text = text.replace('.', '').replace(',', '.')
    if not re.fullmatch(r'\d{1,10}(?:\.\d{1,3})?', text):
        raise ValidationError('Informe uma quantidade positiva com até três casas decimais.')
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ValidationError('Quantidade inválida.') from exc
    if result <= 0 or result >= Decimal('10000000000'):
        raise ValidationError('A quantidade precisa ser maior que zero e caber na grade do ERP.')
    return result

def code(value):
    return str(value or '').strip()

def make_preview(payload, product, order=None):
    errors, warnings = [], []
    for option in ['gerar_faccao','gerar_consumos','desconsiderar_fim_semana']:
        if option in payload and not isinstance(payload[option],bool):
            raise ValidationError('As opções da ordem precisam ser marcadas ou desmarcadas.')
    faccoes=payload.get('faccoes',{})
    if not isinstance(faccoes,dict):raise ValidationError('Seleção de facções inválida.')
    volumes=code(payload.get('volumes','0'))
    if not re.fullmatch(r'\d{1,10}',volumes) or int(volumes)>2147483647:
        errors.append('Informe um número inteiro de volumes maior ou igual a zero.')
    percentual=code(payload.get('percentual','0')).replace(',','.')
    if not re.fullmatch(r'\d{1,9}(?:\.\d{1,2})?',percentual):
        errors.append('Informe um percentual válido com até duas casas decimais.')
    if len(code(payload.get('programacao',''))) > 15:
        errors.append('A programação aceita até 15 caracteres.')
    complements=payload.get('complementos',[])
    if not isinstance(complements,list) or len(complements)>201:
        raise ValidationError('Informações complementares inválidas.')
    complement_keys=set()
    for item in complements:
        if not isinstance(item,dict):raise ValidationError('Informações complementares inválidas.')
        key=code(item.get('codigo'))
        if not key or key in complement_keys:errors.append('Há um complemento sem código ou repetido.')
        complement_keys.add(key)
        if not isinstance(item.get('descricao',''),str) or len(item.get('descricao',''))>130:
            errors.append(f'A descrição do complemento {key} aceita até 130 caracteres.')
        if not re.fullmatch(r'-?\d{1,5}(?:\.\d{1,2})?',str(item.get('valor','0')).replace(',','.')):
            errors.append(f'O valor do complemento {key} aceita até cinco dígitos inteiros e duas casas decimais.')
    for field,label in [('inicio','início'),('fim','fim')]:
        try:
            datetime.date.fromisoformat(str(payload.get(field,'')))
        except ValueError:
            errors.append(f'Informe uma data de {label} válida.')
    if not errors and payload['fim'] < payload['inicio']:
        errors.append('A data final não pode ser anterior à data inicial.')
    if not code(payload.get('deposito')):
        errors.append('Selecione o depósito.')
    if not code(payload.get('periodo')):
        errors.append('Selecione o período de produção.')
    if not payload.get('tipo_id'):
        errors.append('Selecione o tipo de produção.')
    if product.get('ativo') == 'N':
        errors.append('O produto selecionado está inativo.')
    rows, seen = [], set()
    grade = payload.get('grade', [])
    if not isinstance(grade,list) or not 1 <= len(grade) <= 100:
        raise ValidationError('Preencha de uma a cem linhas na grade.')
    for row in grade:
        if not isinstance(row,dict):
            raise ValidationError('Formato de grade inválido.')
        cor,tam = code(row.get('cor')),code(row.get('tam'))
        if not cor or not tam or len(cor)>14 or len(tam)>12:
            errors.append('Informe cor e tamanho válidos em todas as linhas.')
            continue
        if (cor,tam) in seen:
            errors.append(f'A combinação de cor {cor} e tamanho {tam} está repetida.')
            continue
        seen.add((cor,tam))
        try:
            q = quantity(row.get('qtde',''))
        except ValidationError as exc:
            errors.append(str(exc))
            continue
        rows.append({'cor':cor,'tam':tam,'qtde':q})
    total = sum((r['qtde'] for r in rows), Decimal(0))
    if total >= Decimal('10000000000'):
        errors.append('O total excede a capacidade do campo de quantidade da OF.')
    parts = payload.get('partes',[])
    if not isinstance(parts,list) or len(parts)>30:
        raise ValidationError('Seleção de partes inválida.')
    keys={(str(p['id'])):p for p in product['partes']}
    selected=[]
    for part in dict.fromkeys(map(str,parts)):
        if part not in keys:
            errors.append('Uma das partes selecionadas não pertence ao produto.')
        else:
            selected.append(keys[part])
    faction = bool(payload.get('gerar_faccao',True))
    if faction and not selected:
        errors.append('Selecione ao menos uma parte para a facção.')
    routes=[]
    for part in selected:
        if faction and not code(faccoes.get(str(part['id']))):
            errors.append(f"Selecione a facção/terceiro da parte {part['parte']}.")
        sectors=[s for s in product['setores'] if s['parte']==part['parte'] and s['fluxo']==part['fluxo']]
        if not sectors:
            errors.append(f"A parte {part['parte']} não possui setores no fluxo {part['fluxo']}.")
            continue
        positions=[s['ordem'] for s in sectors]
        if any(v is None for v in positions) or len(set(positions))!=len(positions):
            errors.append(f"O fluxo da parte {part['parte']} tem uma sequência de setores ambígua.")
        ordered=sorted(sectors,key=lambda s:s['ordem'] if s['ordem'] is not None else 99999)
        routes.append({'parte':part['parte'],'fluxo':part['fluxo'],'primeiro':ordered[0]['setor'],
                       'faccao':code(faccoes.get(str(part['id']))),'setores':ordered})
        multiple=Decimal(str(part.get('multiplo') or 1))
        if multiple>1 and total % multiple:
            warnings.append(f"O total não é múltiplo de {multiple} na parte {part['parte']}.")
    if faction and any(r['qtde'] % 1 for r in rows):
        warnings.append('A grade tem frações de peça; a quantidade de facção é inteira nesta instalação.')
    if order and not any(i['codigo']==product['codigo'] for i in order['itens']):
        warnings.append('O produto não está nos itens do pedido selecionado.')
    consumption=[];totals=defaultdict(lambda:Decimal(0))
    if payload.get('gerar_consumos',True):
        if not product['ficha']:
            warnings.append('O produto não possui ficha de consumo cadastrada.')
        part_codes={p['parte'] for p in selected}
        for ft in product['ficha']:
            if part_codes and ft['parte'] and ft['parte'] not in part_codes:
                continue
            raw=ft.get('consumo')
            unit_raw=ft.get('consumo_unit')
            if raw is None:
                raw=unit_raw
            if raw is None:
                warnings.append(f"O insumo {ft['insumo']} está sem coeficiente de consumo.")
                continue
            coefficient=Decimal(str(raw))
            if coefficient < 0:
                errors.append(f"O insumo {ft['insumo']} possui coeficiente negativo.")
                continue
            if unit_raw is not None and Decimal(str(unit_raw)) != coefficient:
                warnings.append(f"O insumo {ft['insumo']} possui coeficientes diferentes na ficha; confirme a regra antes da inclusão.")
            if Decimal(str(ft.get('desperdicio') or 0)):
                warnings.append(f"O insumo {ft['insumo']} possui desperdício cadastrado; esta conferência mostra o consumo base.")
            by_color=defaultdict(lambda:Decimal(0))
            for g in rows:
                combos=[c for c in product['combinacoes'] if c['insumo']==ft['insumo'] and code(c['cor'])==g['cor']
                    and code(c['setor'])==code(ft['setor']) and code(c['aplicacao'])==code(ft['aplicacao'])
                    and code(c['faixa'])==code(ft['faixa']) and c['ordem']==ft['ordem']]
                colors={code(c['cor_i']) for c in combos if code(c['cor_i'])}
                if not colors:
                    colors={''}
                    warnings.append(f"Confira a cor do insumo {ft['insumo']} para a cor {g['cor']}.")
                if len(colors)>1:
                    errors.append(f"A combinação de cores do insumo {ft['insumo']} está ambígua.")
                    continue
                by_color[next(iter(colors))]+=g['qtde']*coefficient
            for color,amount in by_color.items():
                unit=code(ft.get('unidade')) or 'não definida'
                consumption.append({'codigo':ft['insumo'],'descricao':ft.get('descricao') or 'Insumo sem descrição',
                    'cor':color,'setor':ft['setor'],'parte':ft['parte'],'unidade':unit,
                    'coeficiente':coefficient,'quantidade':amount})
                totals[unit]+=amount
    return {'total_pecas':total,'grade':rows,'roteiros':routes,'consumos':consumption,
        'totais_unidade':dict(totals),'erros':list(dict.fromkeys(errors)),
        'avisos':list(dict.fromkeys(warnings)),'conferido':not errors,
        'gravacao_habilitada':False,'numero_of':None}
