import streamlit as st
import pandas as pd
import math

# ============================================================
# 1. STREAMLIT CONFIG
# ============================================================
st.set_page_config(
    page_title="Trade Manager & Decision Cockpit v2",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ Trade Manager & Decision Cockpit v2")
st.caption(
    "Systematisches Decision-Gate für Futures und CFDs – "
    "inkl. Netto-CRV, Margin-Checks, Micro-Fallback & Overnight-Kosten"
)
st.markdown("---")

# ============================================================
# 2. INSTRUMENT-DATENBANK
# ============================================================
FUTURES = {
    "NQ (Nasdaq 100)": {
        "tick_size": 0.25, "tick_value": 5.00, "currency": "USD",
        "margin_native": 18000, "micro_key": "MNQ (Micro Nasdaq)"
    },
    "MNQ (Micro Nasdaq)": {
        "tick_size": 0.25, "tick_value": 0.50, "currency": "USD",
        "margin_native": 1800, "micro_key": None
    },
    "ES (S&P 500)": {
        "tick_size": 0.25, "tick_value": 12.50, "currency": "USD",
        "margin_native": 12000, "micro_key": "MES (Micro S&P)"
    },
    "MES (Micro S&P)": {
        "tick_size": 0.25, "tick_value": 1.25, "currency": "USD",
        "margin_native": 1200, "micro_key": None
    },
    "GC (Gold)": {
        "tick_size": 0.10, "tick_value": 10.00, "currency": "USD",
        "margin_native": 10000, "micro_key": "MGC (Micro Gold)"
    },
    "MGC (Micro Gold)": {
        "tick_size": 0.10, "tick_value": 1.00, "currency": "USD",
        "margin_native": 1000, "micro_key": None
    },
    "CL (Crude Oil)": {
        "tick_size": 0.01, "tick_value": 10.00, "currency": "USD",
        "margin_native": 7000, "micro_key": "MCL (Micro Oil)"
    },
    "MCL (Micro Oil)": {
        "tick_size": 0.01, "tick_value": 1.00, "currency": "USD",
        "margin_native": 700, "micro_key": None
    },
    "FDAX (DAX Future)": {
        "tick_size": 0.50, "tick_value": 12.50, "currency": "EUR",
        "margin_native": 30000, "micro_key": "FDXM (Mini DAX)"
    },
    "FDXM (Mini DAX)": {
        "tick_size": 1.00, "tick_value": 5.00, "currency": "EUR",
        "margin_native": 6000, "micro_key": None
    },
}

CFDS = {
    "NASDAQ 100 CFD": {
        "point_value": 1.0, "currency": "USD",
        "default_spread_points": 1.5, "max_leverage": 20, "daily_overnight_pct": 0.015
    },
    "S&P 500 CFD": {
        "point_value": 1.0, "currency": "USD",
        "default_spread_points": 0.5, "max_leverage": 20, "daily_overnight_pct": 0.015
    },
    "GER40 CFD": {
        "point_value": 1.0, "currency": "EUR",
        "default_spread_points": 1.0, "max_leverage": 20, "daily_overnight_pct": 0.015
    },
    "Gold CFD": {
        "point_value": 1.0, "currency": "USD",
        "default_spread_points": 0.3, "max_leverage": 20, "daily_overnight_pct": 0.02
    },
    "Oil CFD": {
        "point_value": 1.0, "currency": "USD",
        "default_spread_points": 0.04, "max_leverage": 10, "daily_overnight_pct": 0.025
    },
}

# ============================================================
# 3. SIDEBAR – KONTO & WÄHRUNG
# ============================================================
with st.sidebar:
    st.header("⚙️ Konto & Tageslimit")
    account_balance = st.number_input(
        "Kontostand / Equity (€)",
        min_value=0.0,
        value=100000.0,
        step=1000.0
    )

    base_risk_pct = st.select_slider(
        "Basis-Risikoklasse (%)",
        options=[0.25, 0.50, 0.75, 1.00, 1.50, 2.00],
        value=1.00
    )

    eurusd = st.number_input(
        "EUR/USD Kurs",
        min_value=0.01,
        value=1.17,
        step=0.01
    )

    st.markdown("---")
    st.subheader("🛡️ Tagesrisiko-Monitore")
    daily_loss_limit_pct = st.select_slider(
        "Tagesverlust-Limit (%)",
        options=[0.5, 1.0, 1.5, 2.0, 3.0],
        value=2.0
    )

    daily_loss_realized_eur = st.number_input(
        "Heute bereits realisiert (€)",
        min_value=0.0,
        value=0.0,
        step=50.0
    )

    daily_open_risk_eur = st.number_input(
        "Offenes Risiko laufender Trades (€)",
        min_value=0.0,
        value=0.0,
        step=50.0,
        help="Risiko von Trades, die aktuell noch offen am Markt sind."
    )

# ============================================================
# 4. INPUT SEKTION
# ============================================================
col_market, col_trader, col_setup = st.columns([1.1, 1.0, 1.2])

with col_market:
    st.subheader("1. Markt-Umfeld")
    t240 = st.selectbox("4H Trend", ["Impulse Wave", "Correction", "Choppy / Sideways"], index=0)
    t60 = st.selectbox("1H Trend", ["Impulse Wave", "Correction", "Choppy / Sideways"], index=0)
    t15 = st.selectbox("15M Trend", ["Impulse Wave", "Correction", "Choppy / Sideways"], index=0)

    st.markdown("**Macro & Sentiment**")
    aaii = st.selectbox("AAII Sentiment", ["Supportive", "Neutral", "Not supportive"], index=0)
    fg_index = st.selectbox("Fear & Greed Index", ["Supportive", "Neutral", "Not supportive"], index=1)
    central_bank = st.selectbox("Notenbank-Politik", ["Supportive", "Neutral", "Not supportive"], index=1)
    seasonals = st.selectbox("Saisonalität", ["Supportive", "Neutral", "Not supportive"], index=0)

with col_trader:
    st.subheader("2. Trader Condition")
    trader_stress = st.select_slider("Stress / Müdigkeit / Zeitdruck", options=["Niedrig", "Mittel", "Hoch"], value="Niedrig")
    location = st.selectbox("Standort", ["Home Office", "Mobil / Unterwegs", "Fremdes Büro"])

    st.markdown("**News & Haltedauer**")
    news_soon = st.radio("High-Impact News < 30 Min?", ["Nein", "Ja"], horizontal=True)
    holding_period = st.radio("Haltedauer", ["Intraday", "Overnight"], horizontal=True)

    overnight_days = 1
    if holding_period == "Overnight":
        overnight_days = st.number_input("Haltedauer (Nächte)", min_value=1, max_value=30, value=1)

with col_setup:
    st.subheader("3. Produkt & Setup")
    product_type = st.radio("Produktart", ["Futures", "CFD"], horizontal=True)

    if product_type == "Futures":
        market_key = st.selectbox("Futures-Instrument", list(FUTURES.keys()))
        spec = FUTURES[market_key]
        margin_native = spec["margin_native"]
        margin_per_contract_eur = margin_native / eurusd if spec["currency"] == "USD" else margin_native
        leverage = None
        spread_points = 0.0
        daily_overnight_pct = 0.0
    else:
        market_key = st.selectbox("CFD-Instrument", list(CFDS.keys()))
        spec = CFDS[market_key]

        max_lev = spec["max_leverage"]
        leverage_options = [l for l in [1, 2, 5, 10, 20, 30] if l <= max_lev]
        leverage = st.select_slider(
            "CFD-Hebel",
            options=leverage_options,
            value=max_lev if max_lev in leverage_options else leverage_options[-1],
            help="Der Hebel bestimmt NUR die geforderte Margin – NICHT dein Stop-Risiko!"
        )

        point_value = st.number_input(
            "Währung je Punkt pro 1 Einheit",
            min_value=0.0001,
            value=float(spec["point_value"]),
            step=0.1
        )

        spread_points = st.number_input(
            "Spread (in Punkten)",
            min_value=0.0,
            value=float(spec["default_spread_points"]),
            step=0.1,
            help="Typische Spreads in Handelspunkten (z.B. 1.5 Punkte NQ)."
        )

        daily_overnight_pct = float(spec["daily_overnight_pct"])

    direction = st.radio("Richtung", ["Long", "Short"], horizontal=True)
    entry_price = st.number_input("Entry", value=16200.0, step=1.0)
    stop_price = st.number_input("Stop Loss", value=15800.0, step=1.0)
    target_price = st.number_input("Target", value=16800.0, step=1.0)
    atr_val = st.number_input("ATR(14)", min_value=0.0, value=45.0, step=0.5)

# ============================================================
# 5. GEAR ENGINE
# ============================================================
trend_points = sum(1.0 if t == "Impulse Wave" else (0.5 if t == "Correction" else 0.0) for t in [t240, t60, t15])
sent_points = sum(0.75 if s == "Supportive" else (0.25 if s == "Neutral" else 0.0) for s in [aaii, fg_index, central_bank, seasonals])

penalties = 0.0
if trader_stress == "Mittel": penalties += 0.5
elif trader_stress == "Hoch": penalties += 1.5
if location != "Home Office": penalties += 0.5

total_score = max(0.0, trend_points + sent_points - penalties)

if total_score >= 5.0:
    gear, min_rrr_req, risk_mult, stop_min_atr, stop_max_atr, scale_out = 5, 2.0, 1.25, 1.0, 2.0, "Nein – Gewinner ausreizen"
elif total_score >= 3.8:
    gear, min_rrr_req, risk_mult, stop_min_atr, stop_max_atr, scale_out = 4, 1.8, 1.00, 1.5, 2.5, "Optional ab 2.0R"
elif total_score >= 2.5:
    gear, min_rrr_req, risk_mult, stop_min_atr, stop_max_atr, scale_out = 3, 1.5, 0.80, 1.5, 4.0, "Ja – Teilgewinn ab ca. 1.5R"
elif total_score >= 1.2:
    gear, min_rrr_req, risk_mult, stop_min_atr, stop_max_atr, scale_out = 2, 1.2, 0.50, 2.0, 4.0, "Ja – frühzeitig Teilgewinne"
else:
    gear, min_rrr_req, risk_mult, stop_min_atr, stop_max_atr, scale_out = 1, 0.0, 0.0, None, None, "N/A"

# ============================================================
# 6. PREIS- & ATR-VALIDIERUNG
# ============================================================
is_valid_direction = (stop_price < entry_price < target_price) if direction == "Long" else (stop_price > entry_price > target_price)

risk_points = abs(entry_price - stop_price)
reward_points = abs(target_price - entry_price)
calc_rrr = reward_points / risk_points if risk_points > 0 else 0.0

stop_atr_ratio = risk_points / atr_val if atr_val > 0 else None
atr_ok = True
if atr_val > 0 and stop_max_atr is not None:
    atr_ok = stop_min_atr <= stop_atr_ratio <= stop_max_atr

# ============================================================
# 7. RISK & POSITION SIZING ENGINE
# ============================================================
effective_risk_pct = base_risk_pct * risk_mult
risk_budget_eur = account_balance * effective_risk_pct / 100.0

# Tagesverlust-Berechnung inklusive offener Trades
daily_loss_limit_eur = account_balance * daily_loss_limit_pct / 100.0
total_daily_risk_used_eur = daily_loss_realized_eur + daily_open_risk_eur
remaining_daily_loss_eur = max(0.0, daily_loss_limit_eur - total_daily_risk_used_eur)

# Deckelung des Trade-Risikos auf verbleibendes Tagesbudget
risk_budget_eur = min(risk_budget_eur, remaining_daily_loss_eur)

micro_recommendation = None

if product_type == "Futures":
    tick_size = spec["tick_size"]
    tick_value = spec["tick_value"]
    risk_ticks = risk_points / tick_size
    reward_ticks = reward_points / tick_size

    risk_per_contract_native = risk_ticks * tick_value
    reward_per_contract_native = reward_ticks * tick_value

    is_usd = spec["currency"] == "USD"
    risk_per_contract_eur = risk_per_contract_native / eurusd if is_usd else risk_per_contract_native
    reward_per_contract_eur = reward_per_contract_native / eurusd if is_usd else reward_per_contract_native

    raw_position_size = risk_budget_eur / risk_per_contract_eur if risk_per_contract_eur > 0 else 0.0
    final_contracts = math.floor(raw_position_size)

    # Micro Fallback Automatik
    if final_contracts == 0 and spec["micro_key"] is not None:
        micro_key = spec["micro_key"]
        m_spec = FUTURES[micro_key]
        m_risk_native = (risk_points / m_spec["tick_size"]) * m_spec["tick_value"]
        m_risk_eur = m_risk_native / eurusd if m_spec["currency"] == "USD" else m_risk_native
        m_contracts = math.floor(risk_budget_eur / m_risk_eur) if m_risk_eur > 0 else 0
        if m_contracts > 0:
            micro_recommendation = f"Standard-Kontrakt zu groß. Empfehlung: **{m_contracts}x {micro_key}** handeln."

    actual_risk_eur = final_contracts * risk_per_contract_eur
    actual_reward_eur = final_contracts * reward_per_contract_eur
    required_margin_eur = final_contracts * margin_per_contract_eur
    total_costs_eur = 0.0

else: # CFD Logic
    risk_per_unit_native = risk_points * point_value
    reward_per_unit_native = reward_points * point_value

    is_usd = spec["currency"] == "USD"
    risk_per_unit_eur = risk_per_unit_native / eurusd if is_usd else risk_per_unit_native
    reward_per_unit_eur = reward_per_unit_native / eurusd if is_usd else reward_per_unit_native

    raw_position_size = risk_budget_eur / risk_per_unit_eur if risk_per_unit_eur > 0 else 0.0
    final_contracts = max(0.0, raw_position_size)

    actual_risk_eur = final_contracts * risk_per_unit_eur
    actual_reward_eur = final_contracts * reward_per_unit_eur

    position_value_eur = (entry_price * final_contracts / eurusd) if is_usd else (entry_price * final_contracts)
    required_margin_eur = position_value_eur / leverage if leverage > 0 else 0.0

    # CFD Kosten: Exakte Punkte-Spread-Berechnung + Overnight
    spread_cost_native = spread_points * final_contracts * point_value
    spread_cost_eur = spread_cost_native / eurusd if is_usd else spread_cost_native

    overnight_cost_eur = 0.0
    if holding_period == "Overnight":
        overnight_cost_eur = position_value_eur * (daily_overnight_pct / 100.0) * overnight_days

    total_costs_eur = spread_cost_eur + overnight_cost_eur

# Netto Risikokennzahlen für Decision Gate
net_risk_eur = actual_risk_eur + total_costs_eur
net_reward_eur = max(0.0, actual_reward_eur - total_costs_eur)
net_rrr = net_reward_eur / net_risk_eur if net_risk_eur > 0 else 0.0

# ============================================================
# 8. DECISION GATE (PRÜFUNG AUF NETTO-CRV UND MARGIN)
# ============================================================
news_block = news_soon == "Ja"
stress_block = trader_stress == "Hoch"
gear_block = gear == 1
crv_block = net_rrr < min_rrr_req
atr_block = not atr_ok
daily_limit_block = remaining_daily_loss_eur <= 0
size_block = final_contracts <= 0
margin_block = required_margin_eur > account_balance

if not is_valid_direction: trade_approval = "🔴 NO TRADE – Preisparameter ungültig"
elif news_block: trade_approval = "🔴 NO TRADE – High-Impact News < 30 Min."
elif stress_block: trade_approval = "🔴 NO TRADE – Stress / Verfassung unzureichend"
elif gear_block: trade_approval = "🔴 NO TRADE – Gear 1 (Marktumfeld schwach)"
elif crv_block: trade_approval = f"🔴 NO TRADE – Netto-CRV {net_rrr:.2f} < gefordert {min_rrr_req:.2f}"
elif atr_block: trade_approval = "🔴 NO TRADE – Stop außerhalb ATR-Regel"
elif daily_limit_block: trade_approval = "🔴 NO TRADE – Tagesverlust-Limit erschöpft"
elif margin_block: trade_approval = "🔴 NO TRADE – Geforderte Margin übersteigt Kontoguthaben"
elif size_block: trade_approval = "🔴 NO TRADE – Risikobudget reicht nicht für 1 Einzeltag/Kontrakt"
else: trade_approval = "🟢 TRADE FREIGEGEBEN"

# ============================================================
# 9. DASHBOARD DASHBOARD DISPLAY
# ============================================================
gcol1, gcol2, gcol3, gcol4 = st.columns(4)
gear_symbol = {1: "🔴", 2: "🟠", 3: "🟡", 4: "🟢", 5: "🟢"}[gear]

gcol1.metric("GEAR", f"{gear} {gear_symbol}")
gcol2.metric("Score", f"{total_score:.2f}")
gcol3.metric("Netto-CRV", f"{net_rrr:.2f}", delta=f"Brutto {calc_rrr:.2f}")
gcol4.metric("Verfügbares Tagesrisiko", f"{remaining_daily_loss_eur:,.2f} €")

st.markdown("---")

# ============================================================
# 10. DECISION CARD
# ============================================================
if "🟢" in trade_approval:
    st.success(f"## {trade_approval}")
else:
    st.error(f"## {trade_approval}")

if micro_recommendation:
    st.info(f"💡 **Micro-Alternative:** {micro_recommendation}")

dc1, dc2, dc3 = st.columns(3)

with dc1:
    st.markdown("**Produkt & Position**")
    st.write(f"Produktart: **{product_type}**")
    st.write(f"Instrument: **{market_key}**")
    st.write(f"Richtung: **{direction.upper()}**")

    if product_type == "Futures":
        st.write(f"Kontrakte: **{final_contracts}**")
        st.write(f"Geforderte Margin: **{required_margin_eur:,.2f} €**")
    else:
        st.write(f"Einheiten: **{final_contracts:,.2f}**")
        st.write(f"Gewählter Hebel: **1:{leverage}**")
        st.write(f"Geforderte Margin: **{required_margin_eur:,.2f} €**")

with dc2:
    st.markdown("**Preis & Setup**")
    st.write(f"Entry / Stop / Target: **{entry_price} / {stop_price} / {target_price}**")
    st.write(f"Stop-Distanz: **{risk_points:,.2f} Punkte**")
    if stop_atr_ratio is not None:
        st.write(f"Stop / ATR: **{stop_atr_ratio:.1f}x** (Limit: {stop_min_atr}x - {stop_max_atr}x)")

with dc3:
    st.markdown("**Risiko & Kosten**")
    st.write(f"Geplantes Risiko (Brutto): **{actual_risk_eur:,.2f} €**")
    st.write(f"Gebühren & Costs (Spread/Overnight): **{total_costs_eur:,.2f} €**")
    st.write(f"Effektives Risiko (Netto): **{net_risk_eur:,.2f} €**")
    st.write(f"Netto-CRV: **{net_rrr:.2f}** (Min: {min_rrr_req:.2f})")

# ============================================================
# 11. REPARATUR-VORSCHLÄGE
# ============================================================
st.markdown("---")
st.subheader("🧭 Was müsste sich ändern?")

reasons = []
if crv_block:
    # Berechnung des nötigen Targets unter Berücksichtigung der Kosten
    req_reward_eur = (min_rrr_req * actual_risk_eur) + total_costs_eur
    req_reward_points = (req_reward_eur * eurusd / point_value / final_contracts) if product_type == "CFD" and is_usd else (req_reward_eur / final_contracts / (tick_value/tick_size if product_type=="Futures" else point_value))
    target_needed = entry_price + req_reward_points if direction == "Long" else entry_price - req_reward_points
    reasons.append(f"Für ein Netto-CRV von {min_rrr_req:.2f} muss das Target auf mindestens **{target_needed:,.2f}** angepasst werden.")

if atr_block and atr_val > 0:
    max_dist = atr_val * stop_max_atr
    s_suggest = entry_price - max_dist if direction == "Long" else entry_price + max_dist
    reasons.append(f"Stop zu weit vom ATR entfernt. Maximaler Stop-Abstand: **{max_dist:,.2f} Punkte** (Stop bei ca. **{s_suggest:,.2f}**).")

if margin_block:
    reasons.append("Margin übersteigt Kontokapital. Reduziere Kontrakte/Einheiten oder wähle ein Micro-Instrument.")

if news_block: reasons.append("News abwarten (< 30 Min bis Event).")
if stress_block: reasons.append("Trader Stress-Level zu hoch – Disziplin sichern.")
if daily_limit_block: reasons.append("Tageslimit erreicht – Handel für heute einstellen.")

if not reasons and "🟢" in trade_approval:
    st.success("🟢 Das Setup ist vollständig konform mit allen Risikofiltern.")
else:
    for r in reasons:
        st.write(f"• {r}")
