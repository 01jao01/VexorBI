#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║           CREDITIQ — MOTOR DE ANÁLISE DE CRÉDITO               ║
║           Sistema de Segmentação de 12.500 Clientes             ║
╚══════════════════════════════════════════════════════════════════╝

COMO EXECUTAR:
  1. Instale as dependências:  pip install flask
  2. Execute:                  python3 run.py
  3. Acesse:                   http://localhost:5000

DEPENDÊNCIAS:
  - Python 3.8+
  - Flask >= 2.0

ESTRUTURA DO PROJETO:
  credit_analyzer/
  ├── app.py              ← Lógica backend + motor de classificação
  ├── run.py              ← Este arquivo (entry point)
  └── templates/
      └── index.html      ← Interface completa (HTML + JS + Plotly)
"""

import sys
import os

def check_requirements():
    try:
        import flask
        print(f"✅ Flask {flask.__version__} detectado.")
    except ImportError:
        print("❌ Flask não encontrado. Instale com:")
        print("   pip install flask")
        sys.exit(1)

def main():
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║         CreditIQ — Motor de Análise de Crédito             ║")
    print("║         Segmentação de 12.500 Clientes | 8 Meses           ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()
    check_requirements()
    print()
    print("🚀 Iniciando servidor...")
    print("📊 Dashboard:       http://localhost:5000")
    print("🎯 Motor de Crédito: http://localhost:5000  (menu lateral)")
    print()
    print("Pressione CTRL+C para encerrar.")
    print("─" * 60)

    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    from app import app
    app.run(debug=False, port=5000, host='0.0.0.0')

if __name__ == "__main__":
    main()
