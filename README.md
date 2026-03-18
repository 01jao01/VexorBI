# Vexor — Motor de Análise de Crédito

Sistema de análise e segmentação de carteira de crédito para **12.500 clientes** ao longo de **8 meses**.

## 🚀 Como Executar

### Pré-requisitos
- Python 3.8 ou superior
- pip

### Instalação

```bash
# Instale a única dependência necessária
pip install flask

# Execute o sistema
python3 run.py

# Acesse no navegador
# http://localhost:5000
```

---

## 📊 Funcionalidades

### Página 1 — Dashboard de Segmentação (Visão Macro)

- **Cards de Métricas**: Receita total, receita por perfil, razão D/R crítica
- **Insight Banner**: Contexto da descoberta principal (Cliente Potencial)
- **Gráfico 1**: Clientes vs. Receita por perfil — a desproporção invisível
- **Gráfico 2**: Evolução mensal da receita ao longo dos 8 meses
- **Gráfico 3**: Scatter — Renda Anual vs. Dívida Pendente com zona de risco destacada
- **Gráfico 4**: Histograma de cronicidade (meses no rotativo)
- **Gráfico 5**: Distribuição da Razão Dívida/Renda na carteira

### Página 2 — Motor de Análise Individual (Visão Micro)

**Inputs:**
- Idade (slider)
- Salário Mensal Líquido (slider)
- Score de Crédito (Baixo / Bom / Ótimo)
- Histórico de Atrasos (Sim / Não)
- Dívida Pendente Total (slider)
- Meses no Rotativo (slider)

**Outputs:**
- Classificação em 3 perfis: **Bom Pagador | Cliente Potencial | Inadimplente**
- Score interno de risco (0–100)
- Receita de juros mensal gerada (taxa 15,05% a.m.)
- Receita projetada no horizonte informado
- Comprometimento de renda com barra de progresso
- Crédito adicional máximo suportável (limite de 30% comprometimento)
- **Alertas Estratégicos:**
  - 🔴 Risco de Ruptura
  - 🟢 Risco de Oportunidade (oferta de crédito)
  - 🟡 Monitoramento / Ação Recomendada

---

## 🏛️ Arquitetura

```
credit_analyzer/
├── app.py          ← Backend Flask + motor de classificação
├── run.py          ← Entry point
├── README.md       ← Este arquivo
└── templates/
    └── index.html  ← Frontend completo (HTML/CSS/JS + Plotly.js)
```

**Stack:**
- Backend: Python + Flask
- Frontend: HTML/CSS/JS puro + Plotly.js (via CDN)
- Sem banco de dados — dados sintéticos gerados deterministicamente

---

## 📈 A Grande Descoberta: O Cliente Potencial

| Perfil | % da Base | Receita de Juros |
|--------|-----------|-----------------|
| Cliente Potencial | 58,9% | R$ 187,4M |
| Bom Pagador | 32,5% | R$ 11,2M |
| Inadimplente | 8,7% | -R$ 8,9M |

O **Cliente Potencial** é o cliente que:
- Paga sempre o mínimo da fatura
- Entra cronicamente no rotativo (pico em 7–8 meses)
- Tem razão Dívida/Renda média de **1,10×** (zona de pressão financeira)
- É **invisível** aos sistemas de risco tradicionais
- Mas gera **98,6% da receita líquida de juros**

---

*CreditIQ Analytics Platform — Estudo de segmentação de carteira de crédito*
