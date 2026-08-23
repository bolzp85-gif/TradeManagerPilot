import streamlit as st
import pandas as pd
import numpy as np

# ============================================================
# 1. STREAMLIT CONFIG
# ============================================================
st.set_page_config(
    page_title="Aggressivitätssteuerung & Trade Manager",
    page_icon="⚙️",
    layout="wide"
)

st.title("⚙️ Trade Manager & Aggressivitätssteuerung")
st.caption("Systematischer Risikorechner, Verfassungs-Check & Gangschaltung nach Schäfermeier-Logik")
st.markdown("---")

# ============================================================
# 2. INPUT SEKTION (3 SPALTEN)
# ============================================================
col_market, col_risk, col_trade = st.columns([1.1, 1, 1.1])

# --- SPALTE 1: MARKTANALYSIS & SENTIMENT ---
with col_market:
    st.subheader("1. Market Analysis")
    
    st.markdown("**Multi-Timeframe Trend Structure**")
    t240 = st.selectbox("SQ 240 (4H Trend)", ["Impulse Wave", "Correction", "Choppy / Sideways"], index=0)
    t60 = st.selectbox("SQ 60 (1H Trend)", ["Impulse Wave", "Correction", "Choppy / Sideways"], index=0)
    t15 = st.selectbox("SQ 15 (15M Trend)", ["Impulse Wave", "Correction", "Choppy / Sideways"], index=0)
    
    st.markdown("**Macro & Sentiment Filter**")
    aaii = st.selectbox("AAII Sentiment", ["Supportive", "Neutral", "Not supportive"], index=0)
    fg_index = st.selectbox("Fear & Greed Index", ["Supportive", "Neutral", "Not supportive"], index=1)
    central_bank = st.selectbox("Central Bank Policy", ["Supportive", "Neutral", "Not supportive"], index=1)
    seasonals = st.selectbox("Seasonals", ["Supportive", "Neutral", "Not supportive"], index=0)

# --- SPALTE 2: RISK & VERFASSUNG ---
with col_risk:
    st.subheader("2. Risk & Environment")
    
    account_balance = st.number_input("Kontostand (€)", value=100000, step=1000)
    base_risk_pct = st.select_slider("Basis-Risikoklasse (%)", options=[0.25, 0.50, 0.75, 1.00, 1.50, 2.00], value=1.00)
    
    st.markdown("**Verfassungs- & Umfeld-Check**")
    health_limit = st.radio("Gesundheitliche Einschränkung / Stress?", ["Nein", "Ja"], horizontal=True)
    appointments = st.radio("Dringende Termine in Kürze?", ["Nein", "Ja"], horizontal=True)
    news_soon = st.radio("High-Impact News / Econ Data < 30m?", ["Nein", "Ja"], horizontal=True)
    location = st.selectbox("Trading Location", ["Home Office", "Unterwegs / Mobil", "Fremdes Büro"])

# --- SPALTE 3: TRADE PLANNING ---
with col_trade:
    st.subheader("3. Trade Planning")
    
    market = st.selectbox("Markt", ["NQ (Nasdaq)", "ES (S&P 500)", "FDAX", "Gold (GC)", "Crude Oil (CL)"])
    direction = st.radio("Richtung", ["Long", "Short"], horizontal=True)
    
    entry_price = st.number_input("Open Rate (Einstieg)", value=16200.0, step=5.0)
    stop_price = st.number_input("Stop-Loss Rate", value=15800.0, step=5.0)
    target_price = st.number_input("Target Rate (Ziel)", value=16800.0, step=5.0)
    
    # Tick-Werte & Multiplikatoren (Beispiel NQ)
    tick_size = 0.25
    tick_value = 5.0  # $5 pro Tick bei Full NQ

# ============================================================
# 3. GEAR CALCULATOR ENGINE (BERECHNUNG DER AGGRESSIVITÄT)
# ============================================================

# Trend-Punkte berechnen
trend_score = sum([1 if t == "Impulse Wave" else (0.5 if t == "Correction" else 0) for t in [t240, t60, t15]])

# Sentiment-Punkte berechnen
sent_score = sum([1 if s == "Supportive" else (0.5 if s == "Neutral" else 0) for s in [aaii, fg_index, central_bank, seasonals]])

# Umwelt-Abzüge
penalties = 0
if health_limit == "Ja": penalties += 1
if appointments == "Ja": penalties += 1
if news_soon == "Ja": penalties += 1.5
if location != "Home Office": penalties += 0.5

# Basis-Gang bestimmen
raw_score = trend_score + (sent_score * 0.75) - penalties

if raw_score >= 5.0:
    gear = 5
    gear_color = "🟢"
    gear_bg = "#1b5e20"
elif raw_score >= 3.8:
    gear = 4
    gear_color = "🟢"
    gear_bg = "#2e7d32"
elif raw_score >= 2.5:
    gear = 3
    gear_color = "🟡"
    gear_bg = "#fbc02d"
elif raw_score >= 1.2:
    gear = 2
    gear_color = "🟠"
    gear_bg = "#f57c00"
else:
    gear = 1
    gear_color = "🔴"
    gear_bg = "#c62828"

# ============================================================
# 4. GANG-REGELN & ANWEISUNGEN (MAPPING)
# ============================================================

GEAR_RULES = {
    5: {
        "strategy": "Aggressive Trend Following & Breakouts (BOR, SQ, Gap Follow)",
        "risk_mult": 1.25,
        "stop_atr": "1.0x - 2.0x ATR (Enger Stop am Swingtief)",
        "scale_out": "Nein, Gewinner maximal ausreizen",
        "min_rrr": "2.0+",
        "re_entry": "Ja, bis zu 2 Re-Entries erlaubt",
        "tmg": "Aggressiv (Trailing Stop nah am Markt)"
    },
    4: {
        "strategy": "Standard Trend Following & Momentum",
        "risk_mult": 1.0,
        "stop_atr": "1.5x - 2.5x ATR",
        "scale_out": "Optional bei 2.0 RRR",
        "min_rrr": "1.8 - 2.0",
        "re_entry": "Ja, max 1 Re-Entry",
        "tmg": "Standard / Neutral"
    },
    3: {
        "strategy": "SQ, BOR (Standard), Retracements & Gap Close",
        "risk_mult": 0.8,
        "stop_atr": "1.5x - 4.0x ATR (Großes Retracement)",
        "scale_out": "Ja, immer (mind. 1.5x ATR Händlerebene)",
        "min_rrr": "1.5 - 2.0",
        "re_entry": "Nein",
        "tmg": "Neutral / Defensiv"
    },
    2: {
        "strategy": "Nur stark abgesicherte Setups / Defensiv (Gap Close, Anti-Trend)",
        "risk_mult": 0.5,
        "stop_atr": "2.0x - 4.0x ATR (Signifikantes Hoch/Tief)",
        "scale_out": "Ja, frühzeitig Teilgewinne sichern",
        "min_rrr": "1.2 - 1.5",
        "re_entry": "Nein",
        "tmg": "Defensiv (Schnell auf Breakeven)"
    },
    1: {
        "strategy": "🚫 NO TRADING / TIGHT DEFENSE",
        "risk_mult": 0.0,
        "stop_atr": "N/A",
        "scale_out": "N/A",
        "min_rrr": "N/A",
        "re_entry": "Nein",
        "tmg": "N/A"
    }
}

rule = GEAR_RULES[gear]

# ============================================================
# 5. DYNAMISCHE TRADE-BERECHNUNG
# ============================================================

effective_risk_pct = base_risk_pct * rule["risk_mult"]
effective_risk_eur = account_balance * (effective_risk_pct / 100)

risk_points = abs(entry_price - stop_price)
reward_points = abs(target_price - entry_price)

rrr = reward_points / risk_points if risk_points > 0 else 0
risk_ticks = risk_points / tick_size
reward_ticks = reward_points / tick_size

# Annahme: Risk pro Tick für 1 Full Kontrakt = (tick_value)
risk_per_contract = risk_ticks * tick_value
position_size = effective_risk_eur / risk_per_contract if risk_per_contract > 0 else 0

# ============================================================
# 6. COCKPIT & AUSGABE
# ============================================================
st.markdown("---")

# DASHBOARD HEADER: GANGSCHALTUNG
st.markdown(
    f"""
    <div style="background-color: {gear_bg}; padding: 15px; border-radius: 10px; text-align: center; color: white;">
        <h1 style="margin:0;">GEAR {gear} {gear_color}</h1>
        <p style="margin:0; font-size: 18px;">Empfohlene Ausrichtung: <b>{rule['strategy']}</b></p>
    </div>
    """, 
    unsafe_allow_html=True
)

st.markdown("<br>", unsafe_allow_html=True)

res_col1, res_col2 = st.columns(2)

with res_col1:
    st.subheader("📋 Handlungsanweisungen (Execution Matrix)")
    
    st.write(f"• **Effektives Risiko:** {effective_risk_pct:.2f}% ({effective_risk_eur:,.2f} €)")
    st.write(f"• **Initial-Stop Vorgabe:** {rule['stop_atr']}")
    st.write(f"• **Scale-Out Regel:** {rule['scale_out']}")
    st.write(f"• **Mindest-CRV (Ziel):** {rule['min_rrr']} (Aktuell berechnet: **{rrr:.2f}**)")
    st.write(f"• **Wiedereinstieg (Re-Entry):** {rule['re_entry']}")
    st.write(f"• **Trade Management (TMG):** {rule['tmg']}")

with res_col2:
    st.subheader("🎯 Trade Ausführung & Positionsgröße")
    
    if gear == 1:
        st.error("⛔ **Trading-Sperre aktiv!** Markt- oder Verfassungsbedingungen erlauben aktuell keine Trades.")
    else:
        st.metric("Berechnetes CRV (RRR)", f"{rrr:.2f}", delta="OK" if rrr >= 1.5 else "CRV zu gering", delta_color="normal" if rrr >= 1.5 else "inverse")
        
        m_c1, m_c2 = st.columns(2)
        m_c1.metric("Risiko (€)", f"{effective_risk_eur:,.0f} €", f"{risk_ticks:.0f} Ticks")
        m_c2.metric("Ziel-Gewinn (€)", f"{(effective_risk_eur * rrr):,.0f} €", f"{reward_ticks:.0f} Ticks")
        
        st.success(f"🛒 **Order-Vorschlag:** {direction.upper()} **{position_size:.2f} Kontrakte** {market}")
