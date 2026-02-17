# 💰 Portfólio V.1.0

**Sistema de Controle de Portfólio de Investimentos**

*by Marcus Aleks*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/GUI-PySide6-green.svg)](https://doc.qt.io/qtforpython-6/)

---

## 📋 Sobre

Portfólio é um sistema desktop para controle e acompanhamento de investimentos em renda variável no mercado brasileiro e internacional. Permite registrar transações de compra e venda, acompanhar posições abertas com cotações em tempo real, e gerar relatórios para apuração de impostos.

## ✨ Funcionalidades

### Dashboard
- Cards de resumo: Patrimônio Total, Custo Total, Ganho/Perda, Posições Abertas
- Gráfico de alocação por classe de ativos (pizza)
- Gráfico de resultado mensal dos últimos 12 meses (barras)

### Transações
- Registro de compras e vendas com validação automática
- Suporte a BRL e USD com taxa de câmbio
- Indicador de notas por transação
- Validação de data e recalculação automática

### Posições Abertas
- Visão consolidada e detalhada (por instituição)
- Cotações de mercado via Yahoo Finance
- Preço de mercado editável manualmente
- Color coding: verde (lucro) / vermelho (prejuízo)
- Cálculo de resultado realizável

### Razão Auxiliar de Ativos
- Histórico completo de operações por ticker
- Preço médio corrente calculado automaticamente
- Saldo de quantidade e resultado realizado
- Indicador de notas com visualização por clique

### Custódia por Instituição
- Agrupamento por corretora/banco
- Cotações editáveis sincronizadas com Posições Abertas
- Totais por instituição e total geral

### Apuração de Resultado / IRRF
- Cálculo de impostos por período (mensal)
- Separação Day Trade vs Swing Trade
- Compensação de prejuízos acumulados

### Outros
- 📄 Exportação PDF e CSV em todos os relatórios
- 📥 Importação de operações via CSV da B3
- 🔄 Eventos corporativos (desdobramentos e grupamentos)

## 🏦 Ativos Suportados

| Classe | Exemplos |
|--------|----------|
| Ações BR | PETR4, VALE3, BBAS3 |
| Ações US | AAPL, MSFT, GOOGL |
| FIIs | HGLG11, XPLG11 |
| BDRs | AAPL34, MSFT34 |
| ETFs | BOVA11, IVVB11 |
| Renda Fixa | Tesouro, CDB |

## 🚀 Instalação

### Opção 1: Instalador Windows (Recomendado)
1. Baixe o instalador na [página de Releases](https://github.com/marcusaleks/portfolio/releases)
2. Execute `PortfolioSetup_v1.0.0.exe`
3. Siga o assistente de instalação

### Opção 2: Executar a partir do código-fonte
```bash
# Clone o repositório
git clone https://github.com/marcusaleks/portfolio.git
cd portfolio

# Crie um ambiente virtual
python -m venv .venv
.venv\Scripts\activate

# Instale as dependências
pip install -r requirements.txt

# Execute o sistema
python main.py
```

## 🛠️ Desenvolvimento

### Pré-requisitos
- Python 3.11 ou superior
- pip (gerenciador de pacotes)

### Executar testes
```bash
pip install pytest
python -m pytest tests/ -v
```

### Gerar executável
```bash
pip install pyinstaller
pyinstaller portfolio.spec
```

## 📁 Estrutura do Projeto

```
portfolio/
├── main.py                 # Ponto de entrada
├── domain/                 # Camada de domínio
│   ├── entities.py         # Entidades (Transaction, Position, etc.)
│   ├── enums.py            # Enumerações (AssetClass, Currency, etc.)
│   └── value_objects.py    # Objetos de valor
├── application/            # Camada de aplicação
│   ├── use_cases.py        # Casos de uso
│   ├── position_calculator.py
│   └── tax_calculator.py
├── infrastructure/         # Camada de infraestrutura
│   ├── database.py         # Configuração SQLAlchemy
│   ├── repositories.py     # Repositórios de dados
│   └── price_provider.py   # Provedor de cotações (yfinance)
├── ui/                     # Interface gráfica (PySide6)
│   ├── main_window.py      # Janela principal
│   ├── dashboard.py        # Dashboard com gráficos
│   ├── table_models.py     # Modelos de tabela
│   ├── custody_view.py     # Custódia por instituição
│   └── ...
├── reports/                # Exportação de relatórios
│   └── report_export.py    # PDF e CSV
└── tests/                  # Testes automatizados
```

## 📄 Licença

Este projeto está licenciado sob a [MIT License](LICENSE).

## 👤 Autor

**Marcus Aleks** — [GitHub](https://github.com/marcusaleks)
