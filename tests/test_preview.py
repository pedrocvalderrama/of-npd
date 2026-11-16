from copy import deepcopy
from decimal import Decimal
import pytest
from of_web.preview import make_preview, quantity, ValidationError


@pytest.fixture
def product():
    return {
        'codigo': 'TESTE', 'descricao': 'Produto de teste', 'unidade': 'UN', 'ativo': 'S',
        'partes': [{'id': 7, 'parte': '00', 'fluxo': '18', 'multiplo': 1}],
        # A sequência, e não o menor código, determina o setor inicial.
        'setores': [
            {'parte': '00', 'fluxo': '18', 'setor': '10', 'ordem': 2},
            {'parte': '00', 'fluxo': '18', 'setor': '51', 'ordem': 1}],
        'ficha': [
            {'insumo': 'PAPEL', 'descricao': 'Papel', 'unidade': 'KG', 'parte': '00',
             'setor': '20', 'aplicacao': '1', 'faixa': '0', 'ordem': 1,
             'consumo': Decimal('0.06371'), 'consumo_unit': Decimal('0.06371')},
            {'insumo': 'ALCA', 'descricao': 'Alça', 'unidade': 'UN', 'parte': '00',
             'setor': '60', 'aplicacao': '2', 'faixa': '0', 'ordem': 2,
             'consumo': Decimal('2'), 'consumo_unit': None}],
        'combinacoes': [
            {'insumo': 'PAPEL', 'cor': '0', 'cor_i': '000', 'setor': '20',
             'aplicacao': '1', 'faixa': '0', 'ordem': 1},
            {'insumo': 'ALCA', 'cor': '0', 'cor_i': '001', 'setor': '60',
             'aplicacao': '2', 'faixa': '0', 'ordem': 2}]
    }


@pytest.fixture
def payload():
    return {'produto': 'TESTE', 'pedido': '', 'inicio': '2026-11-16', 'fim': '2026-11-20',
            'deposito': '0006', 'periodo': '99', 'tipo_id': '5', 'partes': ['7'], 'faccoes': {'7':'00000'},
            'grade': [{'cor': '0', 'tam': '0', 'qtde': '3200'}]}


def test_precise_consumption_and_null_unit_coefficient(payload, product):
    result = make_preview(payload, product)
    assert result['conferido']
    assert result['totais_unidade'] == {'KG': Decimal('203.87200'), 'UN': Decimal('6400')}
    assert result['consumos'][0]['coeficiente'] == Decimal('0.06371')
    assert result['numero_of'] is None
    assert result['gravacao_habilitada'] is False


def test_first_sector_comes_from_flow_order(payload, product):
    result = make_preview(payload, product)
    assert result['roteiros'][0]['primeiro'] == '51'
    assert [s['setor'] for s in result['roteiros'][0]['setores']] == ['51', '10']


def test_ambiguous_flow_blocks_conference(payload, product):
    product['setores'][1]['ordem'] = 2
    result = make_preview(payload, product)
    assert not result['conferido']
    assert any('ambígua' in e for e in result['erros'])


def test_part_from_another_product_is_rejected(payload, product):
    payload['partes'] = ['999']
    result = make_preview(payload, product)
    assert not result['conferido']
    assert any('não pertence' in e for e in result['erros'])


def test_duplicate_grade_is_not_counted_twice(payload, product):
    payload['grade'].append(deepcopy(payload['grade'][0]))
    result = make_preview(payload, product)
    assert not result['conferido']
    assert result['total_pecas'] == Decimal('3200')


@pytest.mark.parametrize('value', ['0', '-1', '1.0001', 'nan', 'Infinity', '1e4', '10000000000'])
def test_invalid_quantity_is_rejected(value):
    with pytest.raises(ValidationError):
        quantity(value)


def test_brazilian_decimal_quantity():
    assert quantity('3.200,125') == Decimal('3200.125')


def test_invalid_dates_block_conference(payload, product):
    payload['fim'] = '2026-11-01'
    assert not make_preview(payload, product)['conferido']


def test_consumption_disabled_does_not_calculate(payload, product):
    payload['gerar_consumos'] = False
    result = make_preview(payload, product)
    assert result['conferido']
    assert result['consumos'] == []
    assert result['totais_unidade'] == {}


def test_ambiguous_material_color_is_reported(payload, product):
    extra = deepcopy(product['combinacoes'][0])
    extra['cor_i'] = '999'
    product['combinacoes'].append(extra)
    result = make_preview(payload, product)
    assert not result['conferido']
    assert any('cores' in e for e in result['erros'])


def test_fractional_faction_quantity_has_warning(payload, product):
    payload['grade'][0]['qtde'] = '1.125'
    result = make_preview(payload, product)
    assert any('inteira' in a for a in result['avisos'])


def test_waste_is_disclosed_as_base_consumption(payload, product):
    product['ficha'][0]['desperdicio'] = Decimal('5')
    result = make_preview(payload, product)
    assert result['totais_unidade']['KG'] == Decimal('203.872')
    assert any('consumo base' in a for a in result['avisos'])


def test_third_party_is_required_per_selected_part(payload, product):
    payload['faccoes'] = {}
    result = make_preview(payload, product)
    assert not result['conferido']
    assert any('terceiro' in e for e in result['erros'])


def test_string_false_is_not_a_boolean(payload, product):
    payload['gerar_faccao'] = 'false'
    with pytest.raises(ValidationError):
        make_preview(payload, product)


@pytest.mark.parametrize('field,value', [('volumes','-1'),('volumes','1.5'),('percentual','nan')])
def test_invalid_extra_fields_block_conference(payload, product, field, value):
    payload[field] = value
    assert not make_preview(payload, product)['conferido']


@pytest.mark.parametrize('description,value', [('x'*131,'0'),('válido','100000'),('válido','1.234')])
def test_complement_limits_match_erp_schema(payload, product, description, value):
    payload['complementos']=[{'codigo':'010','descricao':description,'valor':value}]
    assert not make_preview(payload,product)['conferido']
