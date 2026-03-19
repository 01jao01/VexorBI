"""
Vexor — Motor de Análise de Crédito
─────────────────────────────────────────────────────────
Pipeline completo:
  1. Geração da base sintética de 12.500 clientes
  2. Treinamento de Random Forest na inicialização
  3. Predição de perfil via ML no simulador
  4. Heurísticas financeiras para score, receita e alertas
─────────────────────────────────────────────────────────
"""

import random
import numpy as np
from flask import Flask, render_template, jsonify, request
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import cross_val_score

app = Flask(__name__)

# ─────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────

TAXA_JUROS_MENSAL    = 0.1505   # 15,05% a.m. — crédito rotativo (438% a.a.)
TAXA_JUROS_PARCELADO = 0.0925   # 9,25% a.m.  — cartão parcelado (189% a.a.)
TOTAL_CLIENTES       = 12500
MAX_COMPROMETIMENTO  = 0.30     # 30% da renda — limite máximo recomendado
ALVO_COMPROMETIMENTO = 0.25     # 25% da renda — alvo conservador
MINIMO_PCT           = 0.15     # pagamento mínimo = 15% da fatura (padrão BC)

# ─────────────────────────────────────────────
# GERAÇÃO DA BASE SINTÉTICA (seed fixo = reproduzível)
# ─────────────────────────────────────────────

def _gerar_base():
    rng = random.Random(42)
    np.random.seed(42)
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

            # ── Atrasos ──
            if perfil == "inadimplente":
                atrasos = rng.random() < 0.88
            elif perfil == "potencial":
                atrasos = rng.random() < 0.12
            else:
                atrasos = rng.random() < 0.03
            atrasos = int(atrasos)

            # ── Dívida e razão D/R ──
            # Dívidas calibradas para receita total bater com estudo (BC dez/2025)
            # E para criar separação comportamental clara entre perfis:
            #   Bom:          dívida baixíssima, salário alto → razão D/R < 0.05
            #   Potencial:    dívida moderada, salário médio  → razão D/R 0.05–0.20
            #   Inadimplente: dívida alta, salário baixo      → razão D/R > 0.20
            salario_anual = salario * 12
            if perfil == "bom":
                divida = max(10, rng.gauss(41, 15))
                razao  = divida / salario          # D/R mensal: dívida ÷ salário mensal
            elif perfil == "inadimplente":
                divida = max(200, rng.gauss(1_066, 300))
                razao  = divida / salario
            else:
                divida = max(500, rng.gauss(2_270, 600))
                razao  = divida / salario

            # ── Comprometimento de renda ──
            pag_min     = divida * MINIMO_PCT   # 15% da dívida
            comprom     = pag_min / salario if salario > 0 else 0

            # ── Receita gerada (fórmula do grupo: dívida × taxa × meses) ──
            # Nota: receita incide sobre o saldo rotativo, independente do mínimo
            if perfil == "potencial":
                receita = divida * TAXA_JUROS_MENSAL * meses
            elif perfil == "bom":
                receita = divida * TAXA_JUROS_MENSAL * 1
            else:
                receita = divida * TAXA_JUROS_PARCELADO * meses

            clientes.append({
                "perfil":        perfil,
                "idade":         idade,
                "salario_mensal":round(salario, 2),
                "salario_anual": round(salario_anual, 2),
                "meses_rotativo":meses,
                "atrasos":       atrasos,
                "razao_dr":      round(razao, 4),
                "divida":        round(divida, 2),
                "comprometimento": round(comprom, 4),
                "receita":       round(receita, 2),
            })

    return clientes

BASE: list[dict] = _gerar_base()

# ─────────────────────────────────────────────
# TREINAMENTO DO RANDOM FOREST
# ─────────────────────────────────────────────
#
# Features usadas pelo modelo:
#   [0] idade              — maturidade financeira
#   [1] salario_mensal     — capacidade de pagamento absoluta
#   [2] meses_rotativo     — cronicidade no crédito rotativo
#   [3] atrasos            — histórico de inadimplência (0/1)
#   [4] razao_dr           — pressão de dívida relativa à renda
#   [5] comprometimento    — % da renda comprometida com o mínimo
#
# Target: perfil (potencial / bom / inadimplente)
#
# Por que Random Forest?
#   - Robusto a features de escalas muito diferentes
#   - Captura interações não-lineares (ex: meses altos + atrasos = inadimplente)
#   - Fornece probabilidades calibradas por perfil
#   - Resistente a overfitting com n_estimators adequado

LABEL_MAP     = {"potencial": 0, "bom": 1, "inadimplente": 2}
LABEL_REVERSE = {v: k for k, v in LABEL_MAP.items()}

def _extrair_features(c: dict) -> list:
    """
    Features para o Random Forest — projetadas para separar os 3 perfis
    mesmo com dívidas de valores distintos por perfil:

    [0] meses_rotativo      — cronicidade: bom<3, potencial>5, inad variado
    [1] atrasos             — histórico: inad=0.88, pot=0.12, bom=0.03
    [2] salario_mensal      — capacidade: bom>8k, pot~4.8k, inad~2.8k
    [3] idade               — maturidade: bom~44, pot~37, inad~31
    [4] razao_dr            — pressão: bom~0, pot~0.05, inad~0.20
    [5] comprometimento     — estresse: segue razao_dr
    [6] divida_abs          — nível absoluto de endividamento
    [7] meses_x_atrasos     — interação: meses altos + atrasos = inadimplente claro
    [8] salario_faixa       — 1=até3k, 2=3-6k, 3=6-10k, 4=acima10k
    """
    sal = c["salario_mensal"]
    faixa = 1 if sal < 3000 else (2 if sal < 6000 else (3 if sal < 10000 else 4))
    return [
        c["meses_rotativo"],
        c["atrasos"],
        c["salario_mensal"],
        c["idade"],
        c["razao_dr"],
        c["comprometimento"],
        c["divida"],
        c["meses_rotativo"] * c["atrasos"],
        faixa,
    ]

def _treinar_modelo():
    X = np.array([_extrair_features(c) for c in BASE])
    y = np.array([LABEL_MAP[c["perfil"]] for c in BASE])

    modelo = Pipeline([
        ("scaler", StandardScaler()),
        ("rf", RandomForestClassifier(
            n_estimators=200,       # 200 árvores — boa estabilidade sem custo excessivo
            max_depth=12,           # profundidade controlada — evita overfitting
            min_samples_leaf=8,     # mínimo 8 amostras por folha — generalização
            class_weight="balanced",# compensa o desbalanceamento (59% potencial)
            random_state=42,
            n_jobs=-1,
        )),
    ])

    modelo.fit(X, y)

    # Validação cruzada rápida (5 folds) para reportar acurácia real
    scores = cross_val_score(modelo, X, y, cv=5, scoring="f1_weighted")
    print(f"  Random Forest — F1 médio (5-fold CV): {scores.mean():.3f} ± {scores.std():.3f}")

    # Importância das features
    rf = modelo.named_steps["rf"]
    feature_names = ["idade","salario_mensal","meses_rotativo","atrasos","razao_dr","comprometimento"]
    importancias   = rf.feature_importances_
    print("  Importância das features:")
    for fn, imp in sorted(zip(feature_names, importancias), key=lambda x: -x[1]):
        bar = "█" * int(imp * 40)
        print(f"    {fn:<20} {imp:.3f}  {bar}")

    return modelo

print("\n" + "="*55)
print("  VEXOR — Treinando modelo de classificação...")
MODELO = _treinar_modelo()
print("  Modelo pronto.")
print("="*55 + "\n")

# ─────────────────────────────────────────────
# FILTRO E AGREGAÇÃO DA BASE (dashboard)
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
    n_total = len(sub)
    if n_total == 0:
        return {k: 0 for k in [
            "total_clientes","receita_total","receita_potencial","receita_bom",
            "receita_inadimplente","n_potencial","n_bom","n_inadimplente",
            "pct_potencial","pct_bom","pct_inadimplente","taxa_juros",
        ]}
    pp = {"potencial": [], "bom": [], "inadimplente": []}
    for c in sub:
        pp[c["perfil"]].append(c)

    def rec(p): return sum(c["receita"] for c in pp[p])
    def n(p):   return len(pp[p])
    def pct(p): return round(n(p) / n_total * 100, 1)

    return {
        "total_clientes":       n_total,
        "receita_total":        round(sum(c["receita"] for c in sub)),
        "receita_potencial":    round(rec("potencial")),
        "receita_bom":          round(rec("bom")),
        "receita_inadimplente": round(rec("inadimplente")),
        "n_potencial":          n("potencial"),
        "n_bom":                n("bom"),
        "n_inadimplente":       n("inadimplente"),
        "pct_potencial":        pct("potencial"),
        "pct_bom":              pct("bom"),
        "pct_inadimplente":     pct("inadimplente"),
        "taxa_juros":           TAXA_JUROS_MENSAL * 100,
    }

def _calcular_evolucao(sub):
    meses_label = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago"]
    fat_pot  = [0.70, 0.76, 0.81, 0.87, 0.91, 0.95, 0.98, 1.00]
    fat_bom  = [1.00, 0.98, 0.97, 0.96, 0.97, 0.99, 1.00, 1.00]
    fat_inad = [0.50, 0.60, 0.72, 0.78, 0.83, 0.90, 0.95, 1.00]
    pp = {"potencial": [], "bom": [], "inadimplente": []}
    for c in sub:
        pp[c["perfil"]].append(c)
    def serie(p, fat):
        total = sum(c["receita"] for c in pp[p])
        return [round(total * f / 1_000_000, 4) for f in fat]
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
    bins   = [round(0.2 + i * 0.1, 1) for i in range(15)]
    counts = [0] * len(bins)
    for c in sub:
        idx = min(int((c["razao_dr"] - 0.2) / 0.1), len(bins) - 1)
        if idx >= 0:
            counts[idx] += 1
    return {"bins": bins, "counts": counts}

def _calcular_area(sub):
    meses_label = ["Mês 1","Mês 2","Mês 3","Mês 4","Mês 5","Mês 6","Mês 7","Mês 8"]
    n_pot  = sum(1 for c in sub if c["perfil"] == "potencial")
    n_bom  = sum(1 for c in sub if c["perfil"] == "bom")
    n_inad = sum(1 for c in sub if c["perfil"] == "inadimplente")
    n_tot  = n_pot + n_bom + n_inad
    if n_tot == 0:
        return {"meses": meses_label, "potencial":[0]*8, "bom":[0]*8, "inadimplente":[0]*8}
    fat_pot  = [0.90, 0.92, 0.94, 0.96, 0.97, 0.98, 0.99, 1.00]
    fat_bom  = [1.00, 0.88, 0.76, 0.65, 0.56, 0.48, 0.42, 0.37]
    fat_inad = [1.00, 0.95, 0.88, 0.80, 0.72, 0.64, 0.55, 0.45]
    series   = {"potencial": [], "bom": [], "inadimplente": []}
    for i in range(8):
        ap = n_pot  * fat_pot[i]
        ab = n_bom  * fat_bom[i]
        ai = n_inad * fat_inad[i]
        tot = ap + ab + ai
        if tot == 0:
            for p in series: series[p].append(0)
        else:
            series["potencial"].append(   round(ap / tot * 100, 1))
            series["bom"].append(         round(ab / tot * 100, 1))
            series["inadimplente"].append(round(ai / tot * 100, 1))
    return {"meses": meses_label, **series}

# ─────────────────────────────────────────────
# MOTOR DE ANÁLISE INDIVIDUAL
# ─────────────────────────────────────────────
#
# CLASSIFICAÇÃO — Random Forest (ML)
# ───────────────────────────────────
# O modelo prediz o perfil com base nas 6 features treinadas.
# Retorna também as probabilidades de cada classe, usadas para
# enriquecer os alertas estratégicos.
#
# SCORE INTERNO (0–100) — Heurística de Pressão Financeira
# ──────────────────────────────────────────────────────────
# Mede o nível de estresse financeiro do cliente. Composto por:
#
#   Componente              Peso máx.   Lógica
#   ─────────────────────── ─────────── ────────────────────────────────────
#   Razão D/R               40 pts      razao_dr × 36 (cap em 40)
#   Comprometimento renda   25 pts      comprometimento × 80 (cap em 25)
#   Cronicidade rotativo    20 pts      (meses - 1) × 2.9 (cap em 20)
#   Histórico de atrasos    12 pts      fixo se atrasos = True
#   Bônus maturidade        -3 pts      desconto p/ clientes 30–60 anos
#   ─────────────────────── ─────────── ────────────────────────────────────
#   TOTAL                   0–100
#
# Interpretação: 0–25 = saudável | 26–50 = atenção | 51–75 = risco | 76–100 = crítico
#
# PROBABILIDADE DE RUPTURA (0–95%) — Heurística de Risco de Calote
# ─────────────────────────────────────────────────────────────────
# Estima a chance de o cliente se tornar inadimplente. Componentes:
#
#   razao_dr × 45            — dívida alta relativa à renda = principal driver
#   comprometimento × 30     — renda muito comprometida com o mínimo
#   atrasos × 18             — histórico de atraso é forte preditor de calote
#   (meses - 4) × 2          — cronicidade acima de 4 meses aumenta risco
#   (idade - 30) × -0.3      — clientes mais velhos tendem a ser mais estáveis
#
# CRÉDITO ADICIONAL MÁXIMO — Heurística de Capacidade de Endividamento
# ──────────────────────────────────────────────────────────────────────
# Limite seguro de crédito adicional respeitando 30% de comprometimento:
#
#   margem = (salario × 30%) - pagamento_minimo_atual
#   credito_max = margem / 5%   ← reverso do cálculo do mínimo (5% da dívida)
#
# Se margem ≤ 0: cliente já está no limite ou acima → crédito_max = 0

def analisar_cliente_ml(idade, salario_mensal, atrasos, divida_pendente, meses_rotativo):
    salario_anual   = salario_mensal * 12
    razao_dr        = divida_pendente / salario_mensal if salario_mensal > 0 else 0  # D/R mensal
    pag_min         = divida_pendente * MINIMO_PCT
    comprometimento = pag_min / salario_mensal if salario_mensal > 0 else 0

    # ── Classificação via Random Forest ──
    sal_faixa = 1 if salario_mensal < 3000 else (2 if salario_mensal < 6000 else (3 if salario_mensal < 10000 else 4))
    features = np.array([[
        meses_rotativo,
        int(atrasos),
        salario_mensal,
        idade,
        razao_dr,
        comprometimento,
        divida_pendente,
        meses_rotativo * int(atrasos),
        sal_faixa,
    ]])
    perfil_idx = MODELO.predict(features)[0]
    perfil     = LABEL_REVERSE[perfil_idx]
    proba      = MODELO.predict_proba(features)[0]  # [pot, bom, inad]
    prob_dict  = {LABEL_REVERSE[i]: round(float(p) * 100, 1) for i, p in enumerate(proba)}

    # ── Score interno de pressão financeira (0–100) ──
    # Com dívidas menores (calibradas para receita do estudo), os drivers
    # principais passam a ser meses no rotativo, atrasos e salário relativo.
    #
    # Componente              Peso máx.   Lógica
    # ─────────────────────── ─────────── ──────────────────────────────────
    # Cronicidade rotativo    35 pts      meses × 4.4 (cap em 35)
    # Salário baixo relativo  25 pts      quanto menor o salário vs. R$8k, mais risco
    # Atraso                  20 pts      fixo se atrasos = True
    # Razão D/R escalada      15 pts      razao_dr × 300 (cap em 15) — escala pequena
    # Bônus maturidade        -5 pts      desconto p/ 30–60 anos
    s_meses   = min(35, meses_rotativo * 4.4)
    s_salario = min(25, max(0, (8000 - salario_mensal) / 8000 * 25))
    s_atraso  = 20 if atrasos else 0
    s_dr      = min(15, razao_dr * 300)
    s_idade   = max(0, min(5, (idade - 30) * 0.15)) if 30 <= idade <= 60 else 0
    score_interno = max(0, min(100, round(s_meses + s_salario + s_atraso + s_dr - s_idade)))

    # ── Probabilidade de ruptura (0–95%) ──
    # Reescalada para as novas magnitudes
    prob_ruptura = min(95, max(5, round(
        meses_rotativo * 6
        + max(0, (8000 - salario_mensal) / 8000 * 30)
        + (25 if atrasos else 0)
        + razao_dr * 200
        - max(0, (idade - 30) * 0.4)
    )))

    # ── Cálculos financeiros ──
    receita_mensal_juros = divida_pendente * TAXA_JUROS_MENSAL
    receita_projetada    = receita_mensal_juros * min(meses_rotativo, 8)

    # Crédito adicional máximo — regra correta:
    # (divida_atual + credito_novo) × 15% ≤ salário × 30%
    # → credito_novo ≤ (salário × 30% / 15%) - divida_atual
    limite_divida_total = (salario_mensal * MAX_COMPROMETIMENTO) / MINIMO_PCT
    credito_adicional   = max(0, limite_divida_total - divida_pendente)

    # Verificação: mínimo do crédito novo não deve ultrapassar 25% sozinho
    credito_adicional_conservador = max(0, (salario_mensal * ALVO_COMPROMETIMENTO / MINIMO_PCT) - divida_pendente)

    return {
        "perfil":                    perfil,
        "prob_perfis":               prob_dict,
        "razao_divida_renda":        round(razao_dr, 3),
        "comprometimento_atual_pct": round(comprometimento * 100, 1),
        "receita_mensal_juros":      round(receita_mensal_juros, 2),
        "receita_projetada_8m":      round(receita_projetada, 2),
        "credito_adicional_max":     round(credito_adicional, 2),
        "credito_adicional_conserv": round(credito_adicional_conservador, 2),
        "pag_min_nova_divida":       round(credito_adicional * MINIMO_PCT, 2),
        "comprom_total_pct":         round((pag_min + credito_adicional * MINIMO_PCT) / salario_mensal * 100, 1),
        "score_interno":             score_interno,
        "prob_ruptura":              prob_ruptura,
        "pagamento_minimo_atual":    round(pag_min, 2),
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

@app.route("/api/dashboard-data", methods=["GET", "POST"])
def dashboard_data():
    body = request.get_json(silent=True) or {}
    perfis_ativos = body.get("perfis", ["potencial","bom","inadimplente"])
    renda         = body.get("renda",  "todos")
    meses_min     = int(body.get("meses_min", 1))
    meses_max     = int(body.get("meses_max", 8))
    idade_min     = int(body.get("idade_min", 18))
    idade_max     = int(body.get("idade_max", 80))

    sub = _filtrar(perfis_ativos, renda, meses_min, meses_max, idade_min, idade_max)

    return jsonify({
        "metricas":   _calcular_metricas(sub),
        "evolucao":   _calcular_evolucao(sub),
        "hist_meses": _calcular_hist_meses(sub),
        "razao_hist": _calcular_razao_hist(sub),
        "area":       _calcular_area(sub),
    })

@app.route("/api/analisar-cliente", methods=["POST"])
def analisar_cliente():
    data = request.get_json()
    return jsonify(analisar_cliente_ml(
        idade          = int(data.get("idade", 35)),
        salario_mensal = float(data.get("salario_mensal", 5000)),
        atrasos        = bool(data.get("atrasos", False)),
        divida_pendente= float(data.get("divida_pendente", 10000)),
        meses_rotativo = int(data.get("meses_rotativo", 6)),
    ))

if __name__ == "__main__":
    print(f"\n{'='*55}")
    print("  VEXOR — Motor de Análise de Crédito")
    print(f"  Base: {len(BASE):,} clientes | Modelo: Random Forest")
    print(f"  Acesse: http://localhost:5000")
    print(f"{'='*55}\n")
    app.run(debug=False, port=5000)
