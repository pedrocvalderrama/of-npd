# Interface de OF — etapa 1

Aplicação Python/Flask independente em `C:\dev\OF`, baseada na linguagem visual da página inicial de `C:\dev\servidor\SERVIDOR`: cabeçalho azul, navegação por módulos, cartões e formulários. O programa de referência não foi alterado nem iniciado.

## Iniciar

Abra `INICIAR_OF.bat` e acesse **http://127.0.0.1:5080** no navegador. A credencial do manual já está configurada em `sisplan.local.json`, ignorado pelo versionamento; não é necessário digitar a senha a cada abertura. Para encerrar, use **Ctrl+C** no terminal.

A variável `SISPLAN_PASSWORD`, quando definida, tem prioridade sobre a configuração local. Se ambas estiverem ausentes, o lançador solicita a senha com digitação oculta: os caracteres não aparecem enquanto você digita; confirme com Enter.

O ambiente `.venv` desta pasta já está instalado neste computador. Para recriá-lo, com Python 3.12 disponível:

```powershell
cd C:\dev\OF
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\INICIAR_OF.bat
```

Também é possível executar `.\.venv\Scripts\python.exe iniciar_of.py` diretamente. O arquivo `iniciar_of.ps1` é uma alternativa que respeita a política de execução do PowerShell; o lançador BAT usa Python e não depende de mudar essa política.

## O que está pronto

- Pesquisa de pedidos por número ou cliente, com empresa selecionável; consulta dos itens, observações, depósito e entrega.
- Pesquisa de produtos por código ou descrição; carregamento de partes, fluxo ordenado, tamanhos, ficha técnica e combinações de cores.
- Grade editável por cor/tamanho, soma de quantidades e cálculo decimal dos materiais, separado por unidade.
- Seleção de facção/terceiro por parte, com pesquisa no cadastro de entidades. O fornecedor do produto é somente uma sugestão inicial e pode ser trocado; não se confunde com o cliente do pedido. O código é validado no servidor durante a conferência.
- Datas, período, tipo de produção, depósito, programação, percentual, volumes, observações e campos complementares de descrição/valor.
- Conferência em memória com avisos e erros; download de um JSON da entrada e dos cálculos para revisão.
- Consulta das OFs existentes, incluindo grade, setores, consumos e observações. A consulta utiliza a empresa escolhida no formulário.
- Interface responsiva, com tabelas que permitem rolagem em telas pequenas.

## Limites desta etapa

**Não há criação ou alteração no ERP.** Todas as conexões de banco usam transações `READ ONLY`, e a aplicação confirma `MON$READ_ONLY=1` antes das consultas. Não existem rotas para INSERT/UPDATE/DELETE, execução de procedures ou reserva de numeração. A única rota POST calcula a conferência em memória.

O número aparece como automático, sem consultar nem avançar os controles de numeração. Não há mudança de setor, movimentação de estoque ou alteração de status do pedido. O JSON baixado é uma conferência e não um arquivo de importação no SISPLAN.

O cálculo reproduz o cenário básico mapeado da tela 220. Usa o coeficiente preciso `PCPFT2.CONSUMO`, com alternativa em `CONSUMO_UNIT` quando necessário; não arredonda o unitário para quatro casas antes de multiplicar. O primeiro setor vem de `PRO_FLUXO_SETOR.ORDEM`, nunca de um código fixo. Divergências de coeficientes, desperdício, múltiplos, quantidades fracionadas e combinações ausentes/ambíguas são sinalizadas. Produtos com regras adicionais ainda precisam de validação específica antes da futura gravação.

Percentual e volumes são conferidos como dados da capa. Percentual não altera silenciosamente a quantidade digitada. Os complementos respeitam os limites mapeados de 130 caracteres na descrição e NUMERIC(7,2) no valor. Opções especiais de sortimento, packs e outros tipos de OF não integram esta etapa.

O servidor inicia somente no próprio computador (`127.0.0.1`). Esta versão não implementa login; a disponibilização para outras estações da LAN será uma etapa de implantação, com controle de acesso.

## Configuração por variáveis do processo

| Variável | Padrão |
|---|---|
| `SISPLAN_HOST` | `192.168.100.168` |
| `SISPLAN_PORT` | `3051` |
| `SISPLAN_DATABASE` | `C:\Sisplan\Base\14215F.FDB` |
| `SISPLAN_USER` | `SYSDBA` |
| `SISPLAN_PASSWORD` | Prioridade sobre `sisplan.local.json`; lançador solicita se nenhuma credencial estiver configurada |
| `SISPLAN_DLL` | `C:\dev\auto_sisplan\fbclient_x64.dll` |
| `OF_HOST` | `127.0.0.1` |
| `OF_PORT` | `5080` |

## Organização

| Arquivo | Responsabilidade |
|---|---|
| `app.py` | Inicialização do servidor Waitress |
| `of_web/db.py` | Conexão protegida de leitura |
| `of_web/repository.py` | Consultas fixas, limitadas e parametrizadas |
| `of_web/preview.py` | Regras de conferência e cálculos Decimal |
| `of_web/__init__.py` | Rotas HTTP e tratamento de erros |
| `templates/of.html` | Formulário, pesquisas e consulta de OFs |
| `static/of.css`, `static/of.js` | Visual e interação local |
| `tests/` | Cálculos, fluxo, validações e proteção de leitura |

APIs de leitura: `/api/contexto`, `/api/pedidos`, `/api/pedidos/<numero>`, `/api/produtos`, `/api/produtos/<codigo>`, `/api/entidades`, `/api/ofs` e `/api/ofs/<numero>`. Pesquisas retornam até 30 resultados e indicam quando é necessário refinar. `/api/conferencia` recebe JSON e retorna a prévia sem gravar. Consultas de pedidos/OFs e a conferência recebem `?empresa=1`.

## Verificação

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Os testes não dependem do ERP. Cobrem precisão dos materiais, coeficiente unitário nulo, primeiro setor diferente de 10, fluxo ambíguo, grade duplicada, quantidade inválida, entidade obrigatória, conexão Firebird de leitura e ausência de reserva do número.

A validação de leitura real utilizou o pedido **23393**, produto **05.04.14.0006** e OF **019400**. Para **3.200** peças, a conferência retornou **203,872 KG** de papel e **6.400 UN** de alças, iguais ao caso mapeado. Os cadastros são consultados novamente; IDs das partes não ficam fixos no código.

O mapeamento detalhado da futura gravação permanece em `MAPEAMENTO_CRIACAO_OF.md`. A rotina de numeração e os casos ainda pendentes estão documentados na análise do Trace da OF 019401.
