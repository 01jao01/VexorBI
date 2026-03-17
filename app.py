"""
Sistema de Análise de Crédito - Motor de Segmentação de Clientes
Contexto: 12.500 clientes de cartão de crédito ao longo de 8 meses
"""

import json
import random
import math
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)
random.seed(42)

# ─────────────────────────────────────────────
# DADOS SINTÉTICOS DO ESTUDO
# ─────────────────────────────────────────────

TOTAL_CLIENTES = 12500
DIST = {
    "potencial": 0.589,   # 58.9%
    "bom":       0.325,   # 32.5%
    "inadimplente": 0.087 # 8.7%
}
N = {k: int(TOTAL_CLIENTES * v) for k, v in DIST.items()}

TAXA_JUROS_MENSAL = 0.1505  # 15.05% a.m.

# Receita de juros por perfil (valores calculados com base no rotativo)
RECEITA = {
    "potencial":    187_450_000,   # R$ 187.4M – principal fonte de receita
    "bom":           11_230_000,   # R$ 11.2M  – baixa lucratividade
    "inadimplente":  -8_920_000,   # R$ -8.9M  – perda líquida
}
RECEITA_TOTAL = sum(RECEITA.values())

# ─────────────────────────────────────────────
# GERAÇÃO DE DADOS PARA GRÁFICOS
# ─────────────────────────────────────────────

def gerar_scatter_dados():
    """Gera dados de dispersão: Renda Anual vs Dívida Pendente por perfil."""
    pontos = []

    # Bons pagadores: alta renda, dívida baixa
    for _ in range(min(N["bom"], 600)):
        renda = random.gauss(95_000, 22_000)
        divida = random.gauss(18_000, 8_000)
        renda = max(30_000, renda)
        divida = max(1_000, divida)
        pontos.append({"renda": round(renda), "divida": round(divida), "perfil": "Bom Pagador", "razao": round(divida/renda, 2)})

    # Inadimplentes: renda baixa, dívida alta
    for _ in range(min(N["inadimplente"], 400)):
        renda = random.gauss(38_000, 10_000)
        divida = random.gauss(52_000, 15_000)
        renda = max(15_000, renda)
        divida = max(5_000, divida)
        pontos.append({"renda": round(renda), "divida": round(divida), "perfil": "Inadimplente", "razao": round(divida/renda, 2)})

    # Cliente Potencial: renda média, dívida ~1.10x renda
    for _ in range(min(N["potencial"], 800)):
        renda = random.gauss(62_000, 18_000)
        razao = random.gauss(1.10, 0.12)
        divida = renda * max(0.7, min(1.5, razao))
        renda = max(20_000, renda)
        divida = max(5_000, divida)
        pontos.append({"renda": round(renda), "divida": round(divida), "perfil": "Cliente Potencial", "razao": round(divida/renda, 2)})

    return pontos

def gerar_histograma_meses():
    """Distribui clientes por número de meses no rotativo."""
    hist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0}

    # Bons pagadores: concentrados nos primeiros meses
    for _ in range(N["bom"]):
        m = random.choices([1,2,3,4,5,6,7,8], weights=[35,28,16,9,5,3,2,2])[0]
        hist[m] += 1

    # Inadimplentes: distribuição mista
    for _ in range(N["inadimplente"]):
        m = random.choices([1,2,3,4,5,6,7,8], weights=[20,18,15,14,13,10,7,3])[0]
        hist[m] += 1

    # Cliente Potencial: pico em 7-8 meses (crônicos)
    for _ in range(N["potencial"]):
        m = random.choices([1,2,3,4,5,6,7,8], weights=[3,4,6,9,13,18,25,22])[0]
        hist[m] += 1

    return hist

def gerar_evolucao_receita():
    """Evolução mensal da receita por perfil ao longo de 8 meses."""
    meses = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago"]
    fator_cresc = [0.70, 0.76, 0.81, 0.87, 0.91, 0.95, 0.98, 1.00]

    dados = {
        "meses": meses,
        "potencial": [round(RECEITA["potencial"] * f / 1_000_000, 1) for f in fator_cresc],
        "bom":       [round(RECEITA["bom"] * f / 1_000_000, 1) for f in [1.0,0.98,0.97,0.96,0.97,0.99,1.0,1.0]],
        "inadimplente": [round(abs(RECEITA["inadimplente"]) * f / 1_000_000, 1) for f in [0.5,0.6,0.72,0.78,0.83,0.9,0.95,1.0]],
    }
    return dados

def gerar_razao_divida_renda():
    """Histograma de razão dívida/renda."""
    bins = [round(0.2 + i*0.1, 1) for i in range(15)]  # 0.2 a 1.6
    counts = []
    for b in bins:
        if b < 0.5:
            counts.append(int(random.gauss(180, 30)))
        elif b < 0.8:
            counts.append(int(random.gauss(400, 60)))
        elif b < 1.0:
            counts.append(int(random.gauss(950, 100)))
        elif b < 1.2:
            counts.append(int(random.gauss(1850, 150)))  # pico do potencial
        elif b < 1.4:
            counts.append(int(random.gauss(820, 80)))
        else:
            counts.append(int(random.gauss(220, 40)))
    return {"bins": bins, "counts": counts}

# ─────────────────────────────────────────────
# MOTOR DE CLASSIFICAÇÃO DE CRÉDITO
# ─────────────────────────────────────────────

def classificar_cliente(idade, salario_mensal, score, atrasos, divida_pendente, meses_rotativo):
    """
    Classifica cliente em uma das 3 personas e gera análise financeira.
    
    Score: "Baixo" (<500), "Bom" (500-750), "Ótimo" (>750)
    """
    salario_anual = salario_mensal * 12
    razao_divida_renda = divida_pendente / salario_anual if salario_anual > 0 else 0

    # ── Lógica de Classificação ──
    if not atrasos and score == "Ótimo":
        perfil = "bom"
    elif atrasos and score == "Baixo":
        perfil = "inadimplente"
    elif atrasos and razao_divida_renda > 1.3:
        perfil = "inadimplente"
    elif score in ("Bom", "Baixo") and razao_divida_renda >= 0.7 and not (atrasos and score == "Baixo"):
        perfil = "potencial"
    elif not atrasos and score == "Bom" and razao_divida_renda < 0.7:
        perfil = "bom"
    else:
        # Análise de desempate por razão
        if razao_divida_renda >= 0.9:
            perfil = "potencial" if not (atrasos and score == "Baixo") else "inadimplente"
        else:
            perfil = "bom"

    # ── Cálculos Financeiros ──
    receita_mensal_juros = divida_pendente * TAXA_JUROS_MENSAL
    receita_projetada_8m = receita_mensal_juros * min(meses_rotativo, 8)

    # Comprometimento máximo recomendado: 30% da renda mensal líquida
    MAX_COMPROMETIMENTO = 0.30
    pagamento_minimo_atual = divida_pendente * 0.05  # 5% da dívida = mínimo típico
    comprometimento_atual = pagamento_minimo_atual / salario_mensal if salario_mensal > 0 else 0

    # Crédito adicional máximo que ainda respeita 30% de comprometimento
    margem_disponivel = (salario_mensal * MAX_COMPROMETIMENTO) - pagamento_minimo_atual
    credito_adicional_max = (margem_disponivel / 0.05) if margem_disponivel > 0 else 0  # reverso do mínimo
    credito_adicional_max = max(0, credito_adicional_max)

    # Score de risco interno (0-100)
    score_map = {"Baixo": 30, "Bom": 60, "Ótimo": 90}
    score_num = score_map.get(score, 50)
    penalidade_atraso = 20 if atrasos else 0
    penalidade_razao = min(25, razao_divida_renda * 15)
    bonus_idade = 5 if 30 <= idade <= 55 else 0
    score_interno = max(0, min(100, score_num - penalidade_atraso - penalidade_razao + bonus_idade))

    # Probabilidade de ruptura
    prob_ruptura = min(95, int(razao_divida_renda * 60 + (20 if atrasos else 0) + (10 if score == "Baixo" else 0)))
    if salario_mensal < 3000:
        prob_ruptura = min(95, prob_ruptura + 15)

    return {
        "perfil": perfil,
        "razao_divida_renda": round(razao_divida_renda, 2),
        "receita_mensal_juros": round(receita_mensal_juros, 2),
        "receita_projetada_8m": round(receita_projetada_8m, 2),
        "comprometimento_atual_pct": round(comprometimento_atual * 100, 1),
        "credito_adicional_max": round(credito_adicional_max, 2),
        "score_interno": score_interno,
        "prob_ruptura": prob_ruptura,
        "pagamento_minimo_atual": round(pagamento_minimo_atual, 2),
        "salario_anual": salario_anual,
        "divida_pendente": divida_pendente,
        "meses_rotativo": meses_rotativo,
    }

# ─────────────────────────────────────────────
# ROTAS FLASK
# ─────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/dashboard-data")
def dashboard_data():
    scatter = gerar_scatter_dados()
    hist_meses = gerar_histograma_meses()
    evolucao = gerar_evolucao_receita()
    razao_hist = gerar_razao_divida_renda()

    return jsonify({
        "metricas": {
            "total_clientes": TOTAL_CLIENTES,
            "receita_total": RECEITA_TOTAL,
            "receita_potencial": RECEITA["potencial"],
            "receita_bom": RECEITA["bom"],
            "receita_inadimplente": RECEITA["inadimplente"],
            "n_potencial": N["potencial"],
            "n_bom": N["bom"],
            "n_inadimplente": N["inadimplente"],
            "pct_potencial": round(DIST["potencial"]*100, 1),
            "pct_bom": round(DIST["bom"]*100, 1),
            "pct_inadimplente": round(DIST["inadimplente"]*100, 1),
            "taxa_juros": TAXA_JUROS_MENSAL * 100,
        },
        "scatter": scatter,
        "hist_meses": hist_meses,
        "evolucao": evolucao,
        "razao_hist": razao_hist,
    })

@app.route("/api/analisar-cliente", methods=["POST"])
def analisar_cliente():
    data = request.get_json()
    resultado = classificar_cliente(
        idade=int(data.get("idade", 35)),
        salario_mensal=float(data.get("salario_mensal", 5000)),
        score=data.get("score", "Bom"),
        atrasos=bool(data.get("atrasos", False)),
        divida_pendente=float(data.get("divida_pendente", 10000)),
        meses_rotativo=int(data.get("meses_rotativo", 6)),
    )
    return jsonify(resultado)

if __name__ == "__main__":
    print("\n" + "="*60)
    print("  SISTEMA DE ANÁLISE DE CRÉDITO")
    print("  Motor de Segmentação — 12.500 Clientes")
    print("="*60)
    print("  Acesse: http://localhost:5000")
    print("="*60 + "\n")
    app.run(debug=True, port=5000)
