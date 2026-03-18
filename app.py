"""
Vexor — Motor de Análise de Crédito
Base sintética de 12.500 clientes gerada uma vez e filtrada em tempo real.
"""

import random
import math
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

TAXA_JUROS_MENSAL     = 0.1505   # 15,05% a.m. — crédito rotativo (438% a.a.)
TAXA_JUROS_PARCELADO  = 0.0925   # 9,25% a.m.  — cartão parcelado (189% a.a.)
TOTAL_CLIENTES        = 12500

# Alvos do estudo (Banco Central dez/2025)
RECEITA_ALVO = {
    "potencial":    14_848_743,
    "inadimplente":    375_038,
    "bom":              25_106,
}
# Receita por cliente alvo → define a dívida média de cada perfil
# Potencial:    R$2.017/cliente ÷ 15,05% ÷ 5,9 meses ≈ R$2.270
# Inadimplente: R$347/cliente  ÷  9,25% ÷ 3,5 meses ≈ R$1.072
# Bom Pagador:  R$6/cliente    ÷ 15,05% ÷ 1 mês     ≈ R$40  (praticamente zero)

# ─────────────────────────────────────────────
# GERAÇÃO DA BASE COMPLETA (executada uma vez)
# ─────────────────────────────────────────────

def _gerar_base():
    rng = random.Random(42)
    clientes = []

    perfis = [
        ("potencial",    int(TOTAL_CLIENTES * 0.589)),
        ("bom",          int(TOTAL_CLIENTES * 0.325)),
        ("inadimplente", int(TOTAL_CLIENTES * 0.087)),
    ]

    for perfil, n in perfis:
        for _ in range(n):

            # ── Idade ──
            if perfil == "bom":
                idade = int(rng.gauss(44, 10))
            elif perfil == "inadimplente":
                idade = int(rng.gauss(31, 8))
            else:
                idade = int(rng.gauss(37, 10))
            idade = max(18, min(80, idade))

            # ── Salário mensal ──
            if perfil == "bom":
                salario = rng.gauss(8500, 3500)
            elif perfil == "inadimplente":
                salario = rng.gauss(2800, 900)
            else:
                salario = rng.gauss(4800, 1800)
            salario = max(1200, salario)

            # ── Meses no rotativo ──
            if perfil == "bom":
                meses = rng.choices(range(1, 9), weights=[35,28,16,9,5,3,2,2])[0]
            elif perfil == "inadimplente":
                meses = rng.choices(range(1, 9), weights=[20,18,15,14,13,10,7,3])[0]
            else:
                meses = rng.choices(range(1, 9), weights=[3,4,6,9,13,18,25,22])[0]

            # ── Razão D/R e dívida ──
            # Dívidas calibradas para que receita total bata com o estudo do grupo:
            # Potencial → R$14.848.743 (dívida média ~R$2.270)
            # Inadimplente → R$375.038 (dívida média ~R$1.072, taxa 9,25%)
            # Bom Pagador → R$25.106 (praticamente sem juros)
            salario_anual = salario * 12
            if perfil == "bom":
                divida = max(10, rng.gauss(41, 20))         # saldo residual mínimo — R$41 média
                razao  = divida / salario_anual
            elif perfil == "inadimplente":
                divida = max(200, rng.gauss(1_066, 380))    # saldo parcelado — R$1.066 média
                razao  = divida / salario_anual
            else:
                divida = max(500, rng.gauss(2_270, 700))    # saldo rotativo — R$2.270 média
                razao  = divida / salario_anual

            # ── Receita de juros gerada (fórmula do grupo) ──
            # Receita = Dívida_Pendente × taxa_mensal × meses_rotativo
            if perfil == "potencial":
                receita = divida * TAXA_JUROS_MENSAL * meses
            elif perfil == "bom":
                receita = divida * TAXA_JUROS_MENSAL * 1     # 1 mês residual
            else:
                # Inadimplente: receita positiva para o banco (juros do parcelado)
                receita = divida * TAXA_JUROS_PARCELADO * meses

            clientes.append({
                "perfil":         perfil,
                "idade":          idade,
                "salario_mensal": round(salario, 2),
                "salario_anual":  round(salario_anual, 2),
                "meses_rotativo": meses,
                "razao_dr":       round(razao, 3),
                "divida":         round(divida, 2),
                "receita":        round(receita, 2),
            })

    return clientes

# Base gerada uma única vez na inicialização
BASE: list[dict] = _gerar_base()

# ─────────────────────────────────────────────
# FUNÇÕES DE FILTRO E AGREGAÇÃO
# ─────────────────────────────────────────────

RENDA_FAIXAS = {
    "todos":    (0,       float("inf")),
    "ate3k":    (0,       3000),
    "3a6k":     (3000,    6000),
    "6a10k":    (6000,    10000),
    "acima10k": (10000,   float("inf")),
}

def _filtrar(perfis_ativos, renda, meses_min, meses_max, idade_min, idade_max):
    rmin, rmax = RENDA_FAIXAS.get(renda, (0, float("inf")))
    return [
        c for c in BASE
        if c["perfil"] in perfis_ativos
        and rmin <= c["salario_mensal"] < rmax
        and meses_min <= c["meses_rotativo"] <= meses_max
        and idade_min <= c["idade"] <= idade_max
    ]

def _calcular_metricas(sub):
    n_total  = len(sub)
    if n_total == 0:
        return {k: 0 for k in [
            "total_clientes","receita_total","receita_potencial","receita_bom",
            "receita_inadimplente","n_potencial","n_bom","n_inadimplente",
            "pct_potencial","pct_bom","pct_inadimplente","taxa_juros",
            "dr_medio_potencial"
        ]}

    por_perfil = {"potencial": [], "bom": [], "inadimplente": []}
    for c in sub:
        por_perfil[c["perfil"]].append(c)

    def receita(p): return sum(c["receita"] for c in por_perfil[p])
    def n(p):       return len(por_perfil[p])
    def pct(p):     return round(n(p) / n_total * 100, 1) if n_total else 0
    def dr_medio(p):
        lst = por_perfil[p]
        return round(sum(c["razao_dr"] for c in lst) / len(lst), 2) if lst else 0

    return {
        "total_clientes":      n_total,
        "receita_total":       round(sum(c["receita"] for c in sub)),
        "receita_potencial":   round(receita("potencial")),
        "receita_bom":         round(receita("bom")),
        "receita_inadimplente":round(receita("inadimplente")),
        "n_potencial":         n("potencial"),
        "n_bom":               n("bom"),
        "n_inadimplente":      n("inadimplente"),
        "pct_potencial":       pct("potencial"),
        "pct_bom":             pct("bom"),
        "pct_inadimplente":    pct("inadimplente"),
        "taxa_juros":          TAXA_JUROS_MENSAL * 100,
        "dr_medio_potencial":  dr_medio("potencial"),
    }

def _calcular_evolucao(sub):
    meses_label = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago"]
    # Fatores de crescimento por perfil por mês (simulam acumulação)
    fat_pot  = [0.70, 0.76, 0.81, 0.87, 0.91, 0.95, 0.98, 1.00]
    fat_bom  = [1.00, 0.98, 0.97, 0.96, 0.97, 0.99, 1.00, 1.00]
    fat_inad = [0.50, 0.60, 0.72, 0.78, 0.83, 0.90, 0.95, 1.00]

    por_perfil = {"potencial": [], "bom": [], "inadimplente": []}
    for c in sub:
        por_perfil[c["perfil"]].append(c)

    def serie(p, fat):
        total = sum(c["receita"] for c in por_perfil[p])
        return [round(total * f / 1_000_000, 2) for f in fat]

    return {
        "meses":        meses_label,
        "potencial":    serie("potencial", fat_pot),
        "bom":          serie("bom",       fat_bom),
        "inadimplente": [abs(v) for v in serie("inadimplente", fat_inad)],
    }

def _calcular_hist_meses(sub):
    hist = {i: 0 for i in range(1, 9)}
    for c in sub:
        hist[c["meses_rotativo"]] += 1
    return hist

def _calcular_razao_hist(sub):
    bins  = [round(0.2 + i * 0.1, 1) for i in range(15)]
    counts = [0] * len(bins)
    for c in sub:
        idx = min(int((c["razao_dr"] - 0.2) / 0.1), len(bins) - 1)
        if idx >= 0:
            counts[idx] += 1
    return {"bins": bins, "counts": counts}

def _calcular_dr_evolucao(sub):
    """Razão D/R média por perfil ao longo dos 8 meses (clientes filtrados)."""
    meses_label = ["Mês 1","Mês 2","Mês 3","Mês 4","Mês 5","Mês 6","Mês 7","Mês 8"]

    por_perfil = {"potencial": [], "bom": [], "inadimplente": []}
    for c in sub:
        por_perfil[c["perfil"]].append(c)

    def dr_serie(p, base_dr, fat):
        """Parte da D/R média real do perfil filtrado e aplica fator de deterioração."""
        lst = por_perfil[p]
        if not lst:
            return [0] * 8
        dr_base = sum(c["razao_dr"] for c in lst) / len(lst)
        return [round(dr_base * f, 3) for f in fat]

    # Fatores: Potencial deteriora, Bom melhora, Inadimplente estoura
    fat_pot  = [0.76, 0.81, 0.86, 0.91, 0.95, 0.98, 1.01, 1.04]
    fat_bom  = [1.20, 1.12, 1.05, 1.00, 0.96, 0.93, 0.91, 0.89]
    fat_inad = [0.71, 0.76, 0.83, 0.89, 0.94, 0.97, 0.99, 1.00]

    return {
        "meses":        meses_label,
        "potencial":    dr_serie("potencial",    1.10, fat_pot),
        "bom":          dr_serie("bom",          0.32, fat_bom),
        "inadimplente": dr_serie("inadimplente", 1.28, fat_inad),
    }

def _calcular_area(sub):
    """Composição % da carteira ativa por mês."""
    meses_label = ["Mês 1","Mês 2","Mês 3","Mês 4","Mês 5","Mês 6","Mês 7","Mês 8"]
    n_pot  = sum(1 for c in sub if c["perfil"] == "potencial")
    n_bom  = sum(1 for c in sub if c["perfil"] == "bom")
    n_inad = sum(1 for c in sub if c["perfil"] == "inadimplente")
    n_tot  = n_pot + n_bom + n_inad
    if n_tot == 0:
        return {"meses": meses_label, "potencial": [0]*8, "bom": [0]*8, "inadimplente": [0]*8}

    # Clientes ativos por mês: bom e inad saem progressivamente, potencial fica
    fat_pot  = [0.90, 0.92, 0.94, 0.96, 0.97, 0.98, 0.99, 1.00]
    fat_bom  = [1.00, 0.88, 0.76, 0.65, 0.56, 0.48, 0.42, 0.37]
    fat_inad = [1.00, 0.95, 0.88, 0.80, 0.72, 0.64, 0.55, 0.45]

    series = {"potencial": [], "bom": [], "inadimplente": []}
    for i in range(8):
        ativos_pot  = n_pot  * fat_pot[i]
        ativos_bom  = n_bom  * fat_bom[i]
        ativos_inad = n_inad * fat_inad[i]
        total_mes   = ativos_pot + ativos_bom + ativos_inad
        if total_mes == 0:
            series["potencial"].append(0)
            series["bom"].append(0)
            series["inadimplente"].append(0)
        else:
            series["potencial"].append(round(ativos_pot  / total_mes * 100, 1))
            series["bom"].append(      round(ativos_bom  / total_mes * 100, 1))
            series["inadimplente"].append(round(ativos_inad / total_mes * 100, 1))

    return {"meses": meses_label, **series}

# ─────────────────────────────────────────────
# MOTOR DE CLASSIFICAÇÃO INDIVIDUAL
# ─────────────────────────────────────────────

def classificar_cliente(idade, salario_mensal, atrasos, divida_pendente, meses_rotativo):
    """
    Classifica o cliente em uma das 3 personas com base em:
    - Razão Dívida/Renda (principal driver)
    - Comprometimento de renda com o pagamento mínimo
    - Cronicidade no rotativo (meses)
    - Histórico de atrasos
    - Idade (fator de estabilidade)

    Score interno (0–100) mede pressão financeira: quanto maior, maior o risco.
    """
    salario_anual      = salario_mensal * 12
    razao_dr           = divida_pendente / salario_anual if salario_anual > 0 else 0
    pagamento_minimo   = divida_pendente * 0.05          # 5% da dívida = mínimo típico
    comprometimento    = pagamento_minimo / salario_mensal if salario_mensal > 0 else 0

    # ── Score interno de pressão financeira (0 = saudável, 100 = crítico) ──
    # Cada componente contribui com um peso proporcional à sua relevância real
    s_dr           = min(40, razao_dr * 36)          # até 40 pts — driver principal
    s_comprom      = min(25, comprometimento * 80)   # até 25 pts — quanto da renda vai pro mínimo
    s_meses        = min(20, (meses_rotativo - 1) * 2.9)  # até 20 pts — cronicidade
    s_atraso       = 12 if atrasos else 0             # 12 pts fixos se tem atraso
    s_idade        = max(0, (25 - max(0, idade - 30)) * 0.15)  # bônus leve para maturidade
    score_interno  = max(0, min(100, round(s_dr + s_comprom + s_meses + s_atraso - s_idade)))

    # ── Classificação por regras financeiras objetivas ──
    # Inadimplente: tem atraso E está muito endividado
    if atrasos and razao_dr > 1.20:
        perfil = "inadimplente"
    elif atrasos and comprometimento > 0.50:
        perfil = "inadimplente"

    # Bom Pagador: baixo endividamento, sem atraso, comprometimento confortável
    elif not atrasos and razao_dr < 0.55 and comprometimento < 0.20:
        perfil = "bom"
    elif not atrasos and razao_dr < 0.40:
        perfil = "bom"

    # Cliente Potencial: endividamento médio-alto, pode ou não ter atraso pontual
    elif razao_dr >= 0.75 and not (atrasos and razao_dr > 1.20):
        perfil = "potencial"

    # Zona cinza: decide pelo comprometimento
    elif comprometimento >= 0.25 and not atrasos:
        perfil = "potencial"
    else:
        perfil = "bom"

    # ── Cálculos financeiros ──
    receita_mensal_juros = divida_pendente * TAXA_JUROS_MENSAL
    receita_projetada    = receita_mensal_juros * min(meses_rotativo, 8)
    margem_disponivel    = (salario_mensal * 0.30) - pagamento_minimo
    credito_adicional    = max(0, (margem_disponivel / 0.05) if margem_disponivel > 0 else 0)

    # Probabilidade de ruptura: derivada diretamente das métricas financeiras
    prob_ruptura = min(95, max(5, round(
        razao_dr * 45
        + comprometimento * 30
        + (18 if atrasos else 0)
        + max(0, (meses_rotativo - 4) * 2)
        - max(0, (idade - 30) * 0.3)
    )))

    return {
        "perfil":                    perfil,
        "razao_divida_renda":        round(razao_dr, 2),
        "comprometimento_atual_pct": round(comprometimento * 100, 1),
        "receita_mensal_juros":      round(receita_mensal_juros, 2),
        "receita_projetada_8m":      round(receita_projetada, 2),
        "credito_adicional_max":     round(credito_adicional, 2),
        "score_interno":             score_interno,
        "prob_ruptura":              prob_ruptura,
        "pagamento_minimo_atual":    round(pagamento_minimo, 2),
        "salario_anual":             salario_anual,
        "divida_pendente":           divida_pendente,
        "meses_rotativo":            meses_rotativo,
    }

# ─────────────────────────────────────────────
# ROTAS
# ─────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/dashboard-data", methods=["GET","POST"])
def dashboard_data():
    # Lê filtros (GET = sem filtro, POST = com filtros)
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
    else:
        body = {}

    perfis_ativos = body.get("perfis", ["potencial","bom","inadimplente"])
    renda         = body.get("renda",  "todos")
    meses_min     = int(body.get("meses_min", 1))
    meses_max     = int(body.get("meses_max", 8))
    idade_min     = int(body.get("idade_min", 18))
    idade_max     = int(body.get("idade_max", 80))

    sub = _filtrar(perfis_ativos, renda, meses_min, meses_max, idade_min, idade_max)

    return jsonify({
        "metricas":    _calcular_metricas(sub),
        "evolucao":    _calcular_evolucao(sub),
        "hist_meses":  _calcular_hist_meses(sub),
        "razao_hist":  _calcular_razao_hist(sub),
        "dr_evolucao": _calcular_dr_evolucao(sub),
        "area":        _calcular_area(sub),
    })

@app.route("/api/analisar-cliente", methods=["POST"])
def analisar_cliente():
    data = request.get_json()
    return jsonify(classificar_cliente(
        idade          = int(data.get("idade", 35)),
        salario_mensal = float(data.get("salario_mensal", 5000)),
        atrasos        = bool(data.get("atrasos", False)),
        divida_pendente= float(data.get("divida_pendente", 10000)),
        meses_rotativo = int(data.get("meses_rotativo", 6)),
    ))

if __name__ == "__main__":
    print(f"\n{'='*55}")
    print("  VEXOR — Motor de Análise de Crédito")
    print(f"  Base gerada: {len(BASE):,} clientes")
    print(f"  Acesse: http://localhost:5000")
    print(f"{'='*55}\n")
    app.run(debug=False, port=5000)
