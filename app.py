import streamlit as st
import pandas as pd
import numpy as np
import math

# ============================================================
# 1. STREAMLIT CONFIG & DESIGN
# ============================================================
st.set_page_config(
    page_title="Trade Manager & Decision Cockpit",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ Trade Manager & Decision Cockpit")
st.caption("Systematischer Risikorechner, Trader-Condition-Check & Decision-Gate")
st.markdown("---")

# ============================================================
# 2. INSTRUMENTEN-DATENBANK (FUTURES SPECS)
# ============================================================
INSTRUMENTS = {
    "NQ (Nasdaq 100)": {"tick_size": 0.25, "tick_value": 5.0, "currency": "$", "micro": "MNQ"},
    "MNQ (Micro Nasdaq)": {"tick_size": 0.25, "tick_value": 0.5, "currency": "$", "micro": "MNQ"},
    "ES (S&P 500)": {"tick_size": 0.25, "tick_value": 12.5, "currency": "$", "micro": "MES"},
    "MES (Micro S&P)": {"tick_size": 0.25, "tick_value": 1.25, "currency": "$", "micro": "MES"},
    "FDAX (DAX Future)": {"tick_size": 0.50, "tick_value": 12.5, "currency": "€", "micro": "FDXM"},
    "FDXM (Mini DAX)": {"tick_size": 1.00, "tick_value": 5.0, "currency": "€", "micro": "FDXM"},
    "GC (Gold)": {"tick_size": 0.10, "tick_value": 10.0, "currency": "$", "micro": "MGC"},
    "MGC (Micro Gold)": {"tick_size": 0.10, "tick_value": 1.0, "currency": "$", "micro": "MGC"},
    "CL (Crude Oil)": {"tick_size": 0.01, "tick_value": 10.0, "currency": "$", "micro": "MCL"},
    "MCL (Micro Oil)": {"tick_size": 0.01, "tick_value": 1.0, "currency": "$", "micro": "MCL"}
}

# ============================================================
# 3. INPUT SEKTION (3 SPALTEN)
# ============================================================
col_market, col_trader, col_setup = st.columns([1.1, 1, 1.1])

# --- SPALTE 1: MARKTANALYSIS & SENTIMENT ---
with col_market:
    st.subheader("1. Markt-Umfeld")
    
    st.markdown("**Multi-Timeframe Trend**")
    t240 = st.selectbox("4H Trend", ["Impulse Wave", "Correction", "Choppy / Sideways"], index=0)
    t60 = st.selectbox("1H Trend", ["Impulse Wave", "Correction", "Choppy / Sideways"], index=0)
    t15 = st.selectbox("15M Trend", ["Impulse Wave", "Correction", "Choppy / Sideways"], index=0)
    
    st.markdown("**Macro & Sentiment**")
    aaii = st.selectbox("AAII Sentiment", ["Supportive", "Neutral", "Not supportive"], index=0)
    fg_index = st.selectbox("Fear & Greed Index", ["Supportive", "Neutral", "Not supportive"], index=1)
    central_bank = st.selectbox("Notenbank-Politik", ["Supportive", "Neutral", "Not supportive"], index=1)
    seasonals = st.selectbox("Saisonalität", ["Supportive", "Neutral", "Not supportive"], index=0)

# --- SPALTE 2: TRADER CONDITION & ENVIRONMENT ---
with col_trader:
    st.subheader("2. Trader Condition")
    
    account_balance = st.number_input("Kontostand (€)", value=100000, step=1000)
    base_risk_pct = st.select_slider("Basis-Risikoklasse (%)", options=[0.25, 0.50, 0.75, 1.00, 1.50, 2.00], value=1.00)
    
    st.markdown("**Verfassungs-Check**")
    trader_stress = st.select_slider("Stress / Müdigkeit / Zeitdruck", options=["Niedrig", "Mittel", "Hoch"], value="Niedrig")
    location = st.selectbox("Standort", ["Home Office", "Mobil / Unterwegs", "Fremdes Büro"])
    
    st.markdown("**High-Impact News**")
    news_soon = st.radio("Wichtige News in < 30 Minuten?", ["Nein", "Ja"], horizontal=True)

# --- SPALTE 3: SETUP & VALIDAION ---
with col_setup:
    st.subheader("3. Setup & Parameter")
    
    market_key = st.selectbox("Instrument", list(INSTRUMENTS.keys()))
    direction = st.radio("Richtung", ["Long", "Short"], horizontal=True)
    
    entry_price = st.number_input("Entry (Einstieg)", value=16200.0, step=1.0)
    stop_price = st.number_input("Stop Loss", value=15800.0, step=1.0)
    target_price = st.number_input("Target (Ziel)", value=16800.0, step=1.0)
    atr_val = st.number_input("Aktueller ATR(14) [Optional]", value=45.0, step=0.5)

# ============================================================
# 4. GEAR CALCULATOR & SCORE ZERLEGUNG
# ============================================================

# Punktesystem
trend_points = sum([1.0 if t == "Impulse Wave" else (0.5 if t == "Correction" else 0) for t in [t240, t60, t15]])
sent_points = sum([0.75 if s == "Supportive" else (0.25 if s == "Neutral" else 0) for s in [aaii, fg_index, central_bank, seasonals]])

penalties = 0.0
if trader_stress == "Mittel": penalties += 0.5
elif trader_stress == "Hoch": penalties += 1.5

if location != "Home Office": penalties += 0.5

total_score = max(0.0, trend_points + sent_points - penalties)

# Gear-Bestimmung
if total_score >= 5.0:
    gear = 5
    min_rrr_req = 2.0
    risk_mult = 1.25
    stop_atr_text = "1.0x - 2.0x ATR"
    scale_out = "Nein, Gewinner ausreizen"
elif total_score >= 3.8:
    gear = 4
    min_rrr_req = 1.8
    risk_mult = 1.00
    stop_atr_text = "1.5x - 2.5x ATR"
    scale_out = "Optional ab 2.0 RRR"
elif total_score >= 2.5:
    gear = 3
    min_rrr_req = 1.5
    risk_mult = 0.80
    stop_atr_text = "1.5x - 4.0x ATR"
    scale_out = "Ja, mind. 1.5x ATR"
elif total_score >= 1.2:
    gear = 2
    min_rrr_req = 1.2
    risk_mult = 0.50
    stop_atr_text = "2.0x - 4.0x ATR"
    scale_out = "Ja, frühzeitig Teilgewinne"
else:
    gear = 1
    min_rrr_req = 0.0
    risk_mult = 0.00
    stop_atr_text = "N/A"
    scale_out = "N/A"

# News Hard Block Override
if news_soon == "Ja" and gear > 2:
    gear = 2
    risk_mult = 0.50
    min_rrr_req = 1.5

# ============================================================
# 5. DYNAMISCHE BERECHNUNGEN & VALIDIERUNG
# ============================================================

inst_spec = INSTRUMENTS[market_key]
tick_size = inst_spec["tick_size"]
tick_value = inst_spec["tick_value"]

# 1. Long/Short-Validierung
is_valid_direction = True
validation_msg = ""

if direction == "Long":
    if not (stop_price < entry_price < target_price):
        is_valid_direction = False
        validation_msg = "❌ Ungültiger Long-Trade: Stop muss UNTER und Target UBER dem Einstieg liegen!"
elif direction == "Short":
    if not (stop_price > entry_price > target_price):
        is_valid_direction = False
        validation_msg = "❌ Ungültiger Short-Trade: Stop muss ÜBER und Target UNTER dem Einstieg liegen!"

# 2. Mathematisches Risikomanagement
risk_points = abs(entry_price - stop_price)
reward_points = abs(target_price - entry_price)

risk_ticks = risk_points / tick_size
reward_ticks = reward_points / tick_size

calc_rrr = reward_points / risk_points if risk_points > 0 else 0.0

# ATR Check
stop_atr_ratio = risk_points / atr_val if atr_val > 0 else 0.0

# Effektive Geldbeträge
effective_risk_pct = base_risk_pct * risk_mult
effective_risk_eur = account_balance * (effective_risk_pct / 100)

cost_per_contract = risk_ticks * tick_value
raw_position_size = effective_risk_eur / cost_per_contract if cost_per_contract > 0 else 0

# Ganzzahlige Abrundung
final_contracts = math.floor(raw_position_size)
actual_risk_eur = final_contracts * cost_per_contract
actual_reward_eur = actual_risk_eur * calc_rrr

# 3. Decision Gate Decision Tree
level1_ok = (trader_stress != "Hoch") and (news_soon == "Nein")
level2_ok = (gear >= 2)
level3_ok = is_valid_direction and (calc_rrr >= min_rrr_req) and (final_contracts >= 1)

if not is_valid_direction:
    trade_approval = "🔴 NO TRADE (Ungültige Preis-Parameter)"
elif news_soon == "Ja":
    trade_approval = "🔴 NO TRADE (News Block < 30m)"
elif gear == 1:
    trade_approval = "🔴 NO TRADE (Gear 1 / Zu schlechter Score)"
elif calc_rrr < min_rrr_req:
    trade_approval = f"🔴 NO TRADE (CRV {calc_rrr:.2f} < gefordert {min_rrr_req:.2f})"
elif final_contracts < 1:
    trade_approval = "🔴 NO TRADE (Risikobudget zu klein für 1 Kontrakt)"
else:
    trade_approval = f"🟢 TRADE FREIGEGEBEN ({direction.upper()} {final_contracts}x {market_key})"

# ============================================================
# 6. COCKPIT AUSGABE & SCORE-ZERLEGUNG
# ============================================================

st.markdown("---")

# SCORE ZERLEGUNG DETAILS
with st.expander("📊 Score-Zerlegung anzeigen (Warum dieses Gear?)"):
    sc_col1, sc_col2 = st.columns(2)
    with sc_col1:
        st.write(f"• **Trends (Max 3.0):** +{trend_points:.2f}")
        st.write(f"• **Sentiment & Makro (Max 3.0):** +{sent_points:.2f}")
    with sc_col2:
        st.write(f"• **Abzug Stress/Verfassung:** -{penalties:.2f}")
        if news_soon == "Ja":
            st.write("• **News-Dämpfer:** Gear gedrosselt auf max. Gear 2")
        st.markdown(f"**Gesamt-Score: {total_score:.2f} Pkt. → Gear {gear}**")

st.markdown("<br>", unsafe_allow_html=True)

# 3-EBENEN CHECK
e1, e2, e3 = st.columns(3)
with e1:
    st.markdown("### Ebene 1: Umfeld")
    if level1_ok:
        st.success("🟢 Trader & Umfeld bereit")
    else:
        st.error("🔴 Erhöhtes Risiko / News")

with e2:
    st.markdown("### Ebene 2: Aggressivität")
    st.info(f"⚙️ **GEAR {gear}** (Max. Risk: {effective_risk_pct:.2f}%)")

with e3:
    st.markdown("### Ebene 3: Setup")
    if level3_ok:
        st.success(f"🟢 Setup valide (CRV {calc_rrr:.2f})")
    else:
        st.error(f"🔴 Setup abgelehnt")

st.markdown("---")

# VALIDIERUNGS-WARNHINWEIS
if not is_valid_direction:
    st.error(validation_msg)

# FINAL TRADE CARD
st.subheader("📋 Trade Decision Card")

if "🟢" in trade_approval:
    st.success(f"## {trade_approval}")
    
    tc_col1, tc_col2, tc_col3 = st.columns(3)
    
    with tc_col1:
        st.markdown("**Order Details**")
        st.write(f"• **Instrument:** {market_key}")
        st.write(f"• **Richtung:** {direction.upper()}")
        st.write(f"• **Ganzzahlige Position:** **{final_contracts} Kontrakt(e)**")
        st.write(f"*(Abgerundet von ungerundeten {raw_position_size:.2f})*")

    with tc_col2:
        st.markdown("**Preis-Level & Ticks**")
        st.write(f"• **Entry:** {entry_price:,.2f}")
        st.write(f"• **Stop Loss:** {stop_price:,.2f} ({risk_ticks:.0f} Ticks / {stop_atr_ratio:.1f}x ATR)")
        st.write(f"• **Target:** {target_price:,.2f} ({reward_ticks:.0f} Ticks)")

    with tc_col3:
        st.markdown("**Risiko & Ausführung**")
        st.write(f"• **Tatsächliches Risiko:** **{actual_risk_eur:,.2f} €**")
        st.write(f"• **Ziel-Gewinn:** {actual_reward_eur:,.2f} €")
        st.write(f"• **CRV:** {calc_rrr:.2f} (Mindest-CRV: {min_rrr_req:.2f})")
        st.write(f"• **Management:** {scale_out}")

else:
    st.error(f"## {trade_approval}")
    st.warning("Kein Order-Vorschlag generiert. Passe das Setup an oder warte auf bessere Marktbedingungen.")
