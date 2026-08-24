import streamlit as st
import math

# ============================================================
# 1. STREAMLIT CONFIG
# ============================================================
st.set_page_config(
    page_title="Trade Manager & Decision Cockpit v2.2.1",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ Trade Manager & Decision Cockpit v2.2.1")
st.caption(
    "Systematisches Decision-Gate für Futures und CFDs – "
    "inkl. exakter Kosten-Sizing-Algebra, Freier-Margin-Check & integriertem Micro-Engine"
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
# 3. SIDEBAR – KONTO & MARGIN
# ============================================================
with st.sidebar:
    st.header("⚙️ Konto & Umrechnung")
    account_balance = st.number_input(
        "Kontostand / Equity (€)",
        min_value=0.0, value=100000.0, step=1000.0
    )

    used_margin_eur = st.number_input(
        "Bereits gebundene Margin (€)",
        min_value=0.0, value=0.0, step=500.0,
        help="Margin, die bereits für offene Positionen im Konto reserviert ist."
    )

    free_margin_eur = max(0.0, account_balance - used_margin_eur)
    st.caption(f"Verfügbare freie Margin: **{free_margin_eur:,.2f} €**")

    base_risk_pct = st.select_slider(
        "Basis-Risikoklasse (%)",
        options=[0.25, 0.50, 0.75, 1.00, 1.50, 2.00], value=1.00
    )

    eurusd = st.number_input(
        "EUR/USD Kurs",
        min_value=0.01, value=1.17, step=0.01,
        help="Planungswert für FX-Umrechnungen."
    )

    st.markdown("---")
    st.subheader("🛡️ Tagesrisiko-Monitore")
    daily_loss_limit_pct = st.select_slider(
        "Tagesverlust-Limit (%)",
        options=[0.5, 1.0, 1.5, 2.0, 3.0], value=2.0
    )

    daily_loss_realized_eur = st.number_input(
        "Heute bereits realisiert (€)",
        min_value=0.0, value=0.0, step=50.0
    )

    daily_open_risk_eur = st.number_input(
        "Offenes Risiko laufender Trades (€)",
        min_value=0.0, value=0.0, step=50.0
    )

# ============================================================
# 4. INPUT SEKTION
# ============================================================
col_market, col_trader, col_setup = st.columns([1.1, 1.0, 1.2])

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

with col_trader:
    st.subheader("2. Trader Condition")
    st.markdown("**Verfassungs-Check**")
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
            help="Der Hebel bestimmt NUR die geforderte Planungs-Margin – NICHT das Stop-Risiko!"
        )
        point_value = st.number_input("Währung je Punkt pro 1 Einheit", min_value=0.0001, value=float(spec["point_value"]), step=0.1)
        spread_points = st.number_input(
            "Komp. Spread (in Punkten)",
            min_value=0.0, value=float(spec["default_spread_points"]), step=0.1,
            help="Gesamte Bid/Ask Spanne in Handelspunkten."
        )
        daily_overnight_pct = float(spec["daily_overnight_pct"])

    direction = st.radio("Richtung", ["Long", "Short"], horizontal=True)
    entry_price = st.number_input("Entry", value=16200.0, step=1.0)
    stop_price = st.number_input("Stop Loss", value=15800.0, step=1.0)
    target_price = st.number_input("Target", value=16800.0, step=1.0)
    atr_val = st.number_input("ATR(14)", min_value=0.0, value=45.0, step=0.5, help="Wenn 0: ATR-Filter deaktiviert.")

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
    gear, min_rrr_req, risk_mult, stop_min_atr, stop_max_atr = 5, 2.0, 1.25, 1.0, 2.0
    scale_out = "Nein – Gewinner ausreizen"
elif total_score >= 3.8:
    gear, min_rrr_req, risk_mult, stop_min_atr, stop_max_atr = 4, 1.8, 1.00, 1.5, 2.5
    scale_out = "Optional ab 2.0R"
elif total_score >= 2.5:
    gear, min_rrr_req, risk_mult, stop_min_atr, stop_max_atr = 3, 1.5, 0.80, 1.5, 4.0
    scale_out = "Ja – Teilgewinn ab ca. 1.5R"
elif total_score >= 1.2:
    gear, min_rrr_req, risk_mult, stop_min_atr, stop_max_atr = 2, 1.2, 0.50, 2.0, 4.0
    scale_out = "Ja – frühzeitig Teilgewinne"
else:
    gear, min_rrr_req, risk_mult, stop_min_atr, stop_max_atr = 1, 0.0, 0.0, None, None
    scale_out = "N/A"

# ============================================================
# 6. VALIDIERUNG & SIZING CALCULATOR HELPER
# ============================================================
if direction == "Long":
    is_valid_direction = stop_price < entry_price < target_price
else:
    is_valid_direction = stop_price > entry_price > target_price

risk_points = abs(entry_price - stop_price)
reward_points = abs(target_price - entry_price)
calc_rrr = reward_points / risk_points if risk_points > 0 else 0.0

stop_atr_ratio = risk_points / atr_val if atr_val > 0 else None
atr_ok = True
atr_message = "ATR-Filter deaktiviert."
if atr_val > 0 and stop_max_atr is not None:
    atr_ok = stop_min_atr <= stop_atr_ratio <= stop_max_atr
    atr_message = f"{stop_atr_ratio:.1f}x ATR – erlaubt {stop_min_atr:.1f}x bis {stop_max_atr:.1f}x"

effective_risk_pct = base_risk_pct * risk_mult
risk_budget_eur = account_balance * effective_risk_pct / 100.0

daily_loss_limit_eur = account_balance * daily_loss_limit_pct / 100.0
total_daily_risk_used_eur = daily_loss_realized_eur + daily_open_risk_eur
remaining_daily_loss_eur = max(0.0, daily_loss_limit_eur - total_daily_risk_used_eur)
risk_budget_eur = min(risk_budget_eur, remaining_daily_loss_eur)

def calculate_position(p_type, m_key, budget_eur, is_overnight, nights):
    """Berechnet Positionsgröße so, dass Stop-Risiko + Transaktionskosten <= budget_eur"""
    if budget_eur <= 0 or risk_points <= 0:
        return (0.0 if p_type == "CFD" else 0), 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

    if p_type == "Futures":
        f_spec = FUTURES[m_key]
        is_usd = f_spec["currency"] == "USD"
        r_ticks = risk_points / f_spec["tick_size"]
        r_per_contract_eur = (r_ticks * f_spec["tick_value"]) / eurusd if is_usd else (r_ticks * f_spec["tick_value"])
        
        contracts = math.floor(budget_eur / r_per_contract_eur) if r_per_contract_eur > 0 else 0
        actual_risk = contracts * r_per_contract_eur
        rew_ticks = reward_points / f_spec["tick_size"]
        actual_reward = contracts * ((rew_ticks * f_spec["tick_value"]) / eurusd if is_usd else (rew_ticks * f_spec["tick_value"]))
        m_req = contracts * (f_spec["margin_native"] / eurusd if is_usd else f_spec["margin_native"])
        return contracts, actual_risk, actual_reward, m_req, 0.0, 0.0, 0.0

    else:
        c_spec = CFDS[m_key]
        is_usd = c_spec["currency"] == "USD"
        fx_conv = eurusd if is_usd else 1.0
        
        stop_cost_per_unit = (risk_points * c_spec["point_value"]) / fx_conv
        spread_cost_per_unit = (spread_points * c_spec["point_value"]) / fx_conv
        overnight_cost_per_unit = 0.0
        if is_overnight:
            overnight_cost_per_unit = ((entry_price * c_spec["point_value"]) / fx_conv) * (c_spec["daily_overnight_pct"] / 100.0) * nights
            
        total_risk_per_unit_eur = stop_cost_per_unit + spread_cost_per_unit + overnight_cost_per_unit
        
        # Abrundung auf 2 Nachkommastellen (0.01 CFD-Lots), um Budget-Overflows zu verhindern
        raw_units = budget_eur / total_risk_per_unit_eur if total_risk_per_unit_eur > 0 else 0.0
        units = math.floor(raw_units * 100.0) / 100.0
        
        act_risk = units * stop_cost_per_unit
        act_reward = units * ((reward_points * c_spec["point_value"]) / fx_conv)
        tot_spread = units * spread_cost_per_unit
        tot_overnight = units * overnight_cost_per_unit
        pos_val = (entry_price * units) / fx_conv
        m_req = pos_val / leverage if leverage > 0 else 0.0
        
        return units, act_risk, act_reward, m_req, tot_spread, tot_overnight, pos_val

# Primäre Berechnung ausführen
is_on = (holding_period == "Overnight")
final_contracts, actual_risk_eur, actual_reward_eur, required_margin_eur, spread_cost_eur, overnight_cost_eur, position_value_eur = calculate_position(
    product_type, market_key, risk_budget_eur, is_on, overnight_days
)

# ============================================================
# 7. INTEGRATIVE MICRO-FALLBACK ENGINE
# ============================================================
micro_active = False
micro_key_found = None
micro_contracts = 0
micro_net_rrr = 0.0

if product_type == "Futures" and final_contracts == 0:
    micro_key_found = FUTURES[market_key].get("micro_key")
    if micro_key_found:
        m_cnt, m_risk, m_rew, m_marg, _, _, _ = calculate_position("Futures", micro_key_found, risk_budget_eur, is_on, overnight_days)
        if m_cnt > 0:
            m_net_rrr = m_rew / m_risk if m_risk > 0 else 0.0
            if is_valid_direction and m_net_rrr >= min_rrr_req and m_marg <= free_margin_eur:
                micro_active = True
                micro_contracts = m_cnt
                micro_net_rrr = m_net_rrr
                # Werte auf Micro-Position überschreiben für konsistentes Display:
                final_contracts = m_cnt
                actual_risk_eur = m_risk
                actual_reward_eur = m_rew
                required_margin_eur = m_marg

total_costs_eur = spread_cost_eur + overnight_cost_eur
net_risk_eur = actual_risk_eur + total_costs_eur
net_reward_eur = max(0.0, actual_reward_eur - total_costs_eur)
net_rrr = net_reward_eur / net_risk_eur if net_risk_eur > 0 else 0.0

# ============================================================
# 8. DECISION GATE
# ============================================================
news_block = news_soon == "Ja"
stress_block = trader_stress == "Hoch"
gear_block = gear == 1
crv_block = net_rrr < min_rrr_req
atr_block = not atr_ok
daily_limit_block = remaining_daily_loss_eur <= 0
size_block = final_contracts <= 0
margin_block = required_margin_eur > free_margin_eur

if not is_valid_direction: trade_approval = "🔴 NO TRADE – Preisparameter ungültig"
elif news_block: trade_approval = "🔴 NO TRADE – High-Impact News < 30 Min."
elif stress_block: trade_approval = "🔴 NO TRADE – Stress / Verfassung unzureichend"
elif gear_block: trade_approval = "🔴 NO TRADE – Gear 1 (Marktumfeld schwach)"
elif daily_limit_block: trade_approval = "🔴 NO TRADE – Tagesverlust-Limit erschöpft"
elif atr_block: trade_approval = "🔴 NO TRADE – Stop außerhalb ATR-Regel"
elif crv_block and final_contracts > 0: trade_approval = f"🔴 NO TRADE – Netto-CRV {net_rrr:.2f} < gefordert {min_rrr_req:.2f}"
elif margin_block and final_contracts > 0: trade_approval = "🔴 NO TRADE – Planungs-Margin übersteigt freie Margin"
elif size_block:
    if micro_active:
        trade_approval = f"🟢 TRADE FREIGEGEBEN (via Micro-Fallback: {micro_contracts}x {micro_key_found})"
    else:
        trade_approval = "🔴 NO TRADE – Risikobudget reicht nicht für Mindestpositionsgröße"
else: trade_approval = "🟢 TRADE FREIGEGEBEN"

# ============================================================
# 9. COCKPIT DISPLAY
# ============================================================
st.markdown("---")
gcol1, gcol2, gcol3, gcol4 = st.columns(4)
gear_symbol = {1: "🔴", 2: "🟠", 3: "🟡", 4: "🟢", 5: "🟢"}[gear]

gcol1.metric("GEAR", f"{gear} {gear_symbol}")
gcol2.metric("Score", f"{total_score:.2f}")
display_crv = micro_net_rrr if micro_active else net_rrr
gcol3.metric("Netto-CRV", f"{display_crv:.2f}", delta=f"Brutto {calc_rrr:.2f}")
gcol4.metric("Verfügbares Tagesrisiko", f"{remaining_daily_loss_eur:,.2f} €")

st.markdown("---")

# ============================================================
# 10. DREI EBENEN CHECK
# ============================================================
e1, e2, e3 = st.columns(3)

with e1:
    st.subheader("1️⃣ Umfeld")
    if news_block or stress_block: st.error("🔴 Umfeld blockiert (News/Stress)")
    else: st.success("🟢 Umfeld handelbar")

with e2:
    st.subheader("2️⃣ Aggressivität")
    st.info(f"⚙️ Gear {gear} · Risiko {effective_risk_pct:.2f}%")

with e3:
    st.subheader("3️⃣ Setup")
    if is_valid_direction and atr_ok and (net_rrr >= min_rrr_req or micro_active):
        st.success(f"🟢 Valide · Netto-CRV {display_crv:.2f}")
    else:
        st.error("🔴 Setup abgelehnt")

with st.expander("📊 Warum dieses Gear? (Detaillierte Score-Aufschlüsselung)"):
    s1, s2 = st.columns(2)
    s1.write(f"Trendstruktur (4H/1H/15M): **+{trend_points:.2f}** / 3.00")
    s1.write(f"Sentiment & Makro: **+{sent_points:.2f}** / 3.00")
    s2.write(f"Abzüge (Stress / Standort): **-{penalties:.2f}**")
    s2.write(f"Gesamt-Score: **{total_score:.2f} → Gear {gear}**")

# ============================================================
# 11. TRADE DECISION CARD
# ============================================================
st.markdown("---")
st.subheader("📋 Trade Decision Card")

if "🟢" in trade_approval:
    st.success(f"## {trade_approval}")
else:
    st.error(f"## {trade_approval}")

dc1, dc2, dc3 = st.columns(3)

with dc1:
    st.markdown("**Produkt & Position**")
    if micro_active:
        st.write(f"Ausgewählt: **{market_key}** (🔴 nicht genug Budget)")
        st.write(f"Empfehlung: **{micro_key_found}**")
        st.write(f"Kontrakte: **{micro_contracts}**")
        st.write(f"Planungs-Margin: **{required_margin_eur:,.2f} €**")
    else:
        st.write(f"Produktart: **{product_type}**")
        st.write(f"Instrument: **{market_key}**")
        st.write(f"Richtung: **{direction.upper()}**")

        if product_type == "Futures":
            st.write(f"Kontrakte: **{final_contracts}**")
            st.write(f"Planungs-Margin: **{required_margin_eur:,.2f} €**")
        else:
            st.write(f"Einheiten: **{final_contracts:,.2f}**")
            st.write(f"Hebel: **1:{leverage}**")
            st.write(f"Positionswert: **{position_value_eur:,.2f} €**")
            st.write(f"Planungs-Margin: **{required_margin_eur:,.2f} €**")

with dc2:
    st.markdown("**Preis & Setup**")
    st.write(f"Entry: **{entry_price:,.2f}**")
    st.write(f"Stop: **{stop_price:,.2f}**")
    st.write(f"Target: **{target_price:,.2f}**")
    st.write(f"Stop-Distanz: **{risk_points:,.2f} Punkte**")
    if stop_atr_ratio is not None:
        st.write(f"Stop / ATR: **{stop_atr_ratio:.1f}x** ({atr_message})")

with dc3:
    st.markdown("**Risiko & Ergebnis**")
    st.write(f"Risikobudget max: **{risk_budget_eur:,.2f} €**")
    st.write(f"Brutto Stop-Risiko: **{actual_risk_eur:,.2f} €**")
    st.write(f"Kosten (Spread/Overnight): **{total_costs_eur:,.2f} €**")
    st.write(f"Effektives Max-Risiko: **{net_risk_eur:,.2f} €**")
    st.write(f"Netto-CRV: **{net_rrr:.2f}** (Brutto: {calc_rrr:.2f})")
    st.write(f"Management: **{scale_out}**")

# ============================================================
# 12. HANDLUNGSEMPFEHLUNG
# ============================================================
st.markdown("---")
st.subheader("🧭 Was müsste sich ändern?")

reasons = []

if not is_valid_direction:
    reasons.append("Preisstruktur korrigieren: Stop und Target müssen zur Richtung passen.")
if news_block:
    reasons.append("High-Impact News abwarten (< 30 Min bis Event).")
if stress_block:
    reasons.append("Trader Stress-Level zu hoch – Disziplin sichern.")
if gear_block:
    reasons.append("Kein Trade bei Gear 1 (Gesamt-Score zu niedrig).")

# Sichere Target-Berechnung ohne DivisionByZero
if crv_block and final_contracts > 0:
    req_reward_eur = (min_rrr_req * net_risk_eur) + total_costs_eur
    spec_curr = FUTURES[market_key]["currency"] if product_type == "Futures" else CFDS[market_key]["currency"]
    is_usd = spec_curr == "USD"
    fx_conv = eurusd if is_usd else 1.0

    if product_type == "CFD":
        pt_val = CFDS[market_key]["point_value"]
        req_reward_points = (req_reward_eur * fx_conv) / (pt_val * final_contracts)
    else:
        active_market = micro_key_found if micro_active else market_key
        f_spec = FUTURES[active_market]
        val_per_point = f_spec["tick_value"] / f_spec["tick_size"]
        req_reward_points = (req_reward_eur * fx_conv) / (val_per_point * final_contracts)

    target_needed = entry_price + req_reward_points if direction == "Long" else entry_price - req_reward_points
    reasons.append(f"Für ein Netto-CRV von **{min_rrr_req:.2f}** muss das Target auf mindestens **{target_needed:,.2f}** angepasst werden.")

elif crv_block and final_contracts == 0:
    reasons.append("Netto-CRV zu gering. Erhöhe das Target-Gewinnziel vor der Positionsgrößenanpassung.")

if atr_block and atr_val > 0:
    max_dist = atr_val * stop_max_atr
    s_suggest = entry_price - max_dist if direction == "Long" else entry_price + max_dist
    reasons.append(f"Stop zu weit vom ATR entfernt. Maximaler Stop-Abstand: **{max_dist:,.2f} Punkte** (Stop bei ca. **{s_suggest:,.2f}**).")

if margin_block and final_contracts > 0:
    reasons.append(f"Geforderte Planungs-Margin ({required_margin_eur:,.2f} €) übersteigt freie Margin ({free_margin_eur:,.2f} €). Reduziere Einheiten oder wähle ein Micro-Instrument.")

if daily_limit_block:
    reasons.append("Tagesverlust-Limit erreicht – keine weiteren Trades für heute.")

if not reasons and "🟢" in trade_approval:
    st.success("🟢 Das Setup ist vollständig konform mit allen Risikofiltern.")
else:
    for r in reasons:
        st.write(f"• {r}")

# ============================================================
# 13. RISIKO-HINWEIS
# ============================================================
st.markdown("---")
st.caption(
    "Hinweis: Dieses Dashboard ist ein regelbasiertes Planungs- und "
    "Risikomanagement-Tool und keine Anlageberatung. Futures und CFDs "
    "sind gehebelte Produkte und können zu erheblichen Verlusten führen."
)
