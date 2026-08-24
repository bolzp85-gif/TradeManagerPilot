import streamlit as st
import pandas as pd
import math

# ============================================================
# 1. STREAMLIT CONFIG
# ============================================================
st.set_page_config(
    page_title="Trade Manager & Decision Cockpit",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ Trade Manager & Decision Cockpit")
st.caption(
    "Systematisches Decision-Gate für Futures und CFDs – "
    "mit Gear-Steuerung, Risikoberechnung und Positionsgrößenplanung"
)
st.markdown("---")

# ============================================================
# 2. INSTRUMENT-DATENBANK
#    Futures: Tick Size / Tick Value
#    CFDs: Punktewert je 1 Einheit + eToro-Spread-Schätzung
#
#    WICHTIG:
#    eToro-Hebel, Spreads und Finanzierung können sich ändern und
#    hängen von Instrument/regulierender Einheit ab. Deshalb sind
#    CFD-Werte editierbar und ausdrücklich als Planungswerte markiert.
# ============================================================
FUTURES = {
    "NQ (Nasdaq 100)": {"tick_size": 0.25, "tick_value": 5.00, "currency": "USD", "micro": "MNQ"},
    "MNQ (Micro Nasdaq)": {"tick_size": 0.25, "tick_value": 0.50, "currency": "USD", "micro": None},
    "ES (S&P 500)": {"tick_size": 0.25, "tick_value": 12.50, "currency": "USD", "micro": "MES"},
    "MES (Micro S&P)": {"tick_size": 0.25, "tick_value": 1.25, "currency": "USD", "micro": None},
    "GC (Gold)": {"tick_size": 0.10, "tick_value": 10.00, "currency": "USD", "micro": "MGC"},
    "MGC (Micro Gold)": {"tick_size": 0.10, "tick_value": 1.00, "currency": "USD", "micro": None},
    "CL (Crude Oil)": {"tick_size": 0.01, "tick_value": 10.00, "currency": "USD", "micro": "MCL"},
    "MCL (Micro Oil)": {"tick_size": 0.01, "tick_value": 1.00, "currency": "USD", "micro": None},
    "FDAX (DAX Future)": {"tick_size": 0.50, "tick_value": 12.50, "currency": "EUR", "micro": "FDXM"},
    "FDXM (Mini DAX)": {"tick_size": 1.00, "tick_value": 5.00, "currency": "EUR", "micro": None},
}

# CFD-Planungswerte.
# "point_value" = Kontowährung pro 1 Kurs-Punkt bei 1 Einheit.
# Bei eToro wird die tatsächliche Handelsgröße/Einheit und der
# anwendbare Hebel vor Orderaufgabe auf der Plattform geprüft.
CFDS = {
    "NASDAQ 100 CFD (NSDQ100)": {
        "point_value": 1.0, "currency": "USD",
        "default_leverage": 20, "max_leverage_reference": 30,
        "spread_pct": 0.007
    },
    "S&P 500 CFD (SPX500)": {
        "point_value": 1.0, "currency": "USD",
        "default_leverage": 20, "max_leverage_reference": 30,
        "spread_pct": 0.007
    },
    "GER40 CFD": {
        "point_value": 1.0, "currency": "EUR",
        "default_leverage": 20, "max_leverage_reference": 30,
        "spread_pct": 0.007
    },
    "Gold CFD": {
        "point_value": 1.0, "currency": "USD",
        "default_leverage": 20, "max_leverage_reference": 30,
        "spread_pct": 0.01
    },
    "Oil CFD": {
        "point_value": 1.0, "currency": "USD",
        "default_leverage": 20, "max_leverage_reference": 30,
        "spread_pct": 0.04
    },
}

# ============================================================
# 3. SIDEBAR – KONTO & WÄHRUNG
# ============================================================
with st.sidebar:
    st.header("⚙️ Konto & Umrechnung")
    account_balance = st.number_input(
        "Kontostand (€)",
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
        step=0.01,
        help="Planungswert. Für Live-Trading sollte der aktuelle EUR/USD-Kurs verwendet werden."
    )

    daily_loss_limit_pct = st.select_slider(
        "Tagesverlust-Limit (%)",
        options=[0.5, 1.0, 1.5, 2.0, 3.0],
        value=2.0
    )

    daily_loss_used_eur = st.number_input(
        "Heute bereits realisiert (€)",
        min_value=0.0,
        value=0.0,
        step=50.0
    )

# ============================================================
# 4. INPUT SEKTION
# ============================================================
col_market, col_trader, col_setup = st.columns([1.1, 1.0, 1.2])

with col_market:
    st.subheader("1. Markt-Umfeld")

    st.markdown("**Multi-Timeframe Trend**")
    t240 = st.selectbox(
        "4H Trend",
        ["Impulse Wave", "Correction", "Choppy / Sideways"],
        index=0
    )
    t60 = st.selectbox(
        "1H Trend",
        ["Impulse Wave", "Correction", "Choppy / Sideways"],
        index=0
    )
    t15 = st.selectbox(
        "15M Trend",
        ["Impulse Wave", "Correction", "Choppy / Sideways"],
        index=0
    )

    st.markdown("**Macro & Sentiment**")
    aaii = st.selectbox(
        "AAII Sentiment",
        ["Supportive", "Neutral", "Not supportive"],
        index=0
    )
    fg_index = st.selectbox(
        "Fear & Greed Index",
        ["Supportive", "Neutral", "Not supportive"],
        index=1
    )
    central_bank = st.selectbox(
        "Notenbank-Politik",
        ["Supportive", "Neutral", "Not supportive"],
        index=1
    )
    seasonals = st.selectbox(
        "Saisonalität",
        ["Supportive", "Neutral", "Not supportive"],
        index=0
    )

with col_trader:
    st.subheader("2. Trader Condition")

    st.markdown("**Verfassungs-Check**")
    trader_stress = st.select_slider(
        "Stress / Müdigkeit / Zeitdruck",
        options=["Niedrig", "Mittel", "Hoch"],
        value="Niedrig"
    )
    location = st.selectbox(
        "Standort",
        ["Home Office", "Mobil / Unterwegs", "Fremdes Büro"]
    )

    st.markdown("**News & Haltedauer**")
    news_soon = st.radio(
        "High-Impact News < 30 Min?",
        ["Nein", "Ja"],
        horizontal=True
    )
    holding_period = st.radio(
        "Haltedauer",
        ["Intraday", "Overnight"],
        horizontal=True
    )

with col_setup:
    st.subheader("3. Produkt & Setup")

    product_type = st.radio(
        "Produktart",
        ["Futures", "CFD"],
        horizontal=True
    )

    if product_type == "Futures":
        market_key = st.selectbox("Futures-Instrument", list(FUTURES.keys()))
        spec = FUTURES[market_key]
        leverage = None
        point_value = None
        spread_pct = 0.0

    else:
        market_key = st.selectbox("CFD-Instrument", list(CFDS.keys()))
        spec = CFDS[market_key]

        leverage_options = [1, 2, 5, 10, 20, 30]
        default_lev = spec["default_leverage"]
        leverage = st.select_slider(
            "CFD-Hebel",
            options=leverage_options,
            value=default_lev if default_lev in leverage_options else 20,
            help="Nur Hebel verwenden, der auf deinem konkreten eToro-Instrument tatsächlich angeboten wird."
        )

        point_value = st.number_input(
            "€/$ pro Punkt je 1 Einheit",
            min_value=0.0001,
            value=float(spec["point_value"]),
            step=0.1,
            help="Editierbarer Planungswert. Prüfe die tatsächliche Einheiten-/Punkte-Definition bei eToro."
        )

        spread_pct = st.number_input(
            "eToro Spread-Schätzung (% pro Trade)",
            min_value=0.0,
            value=float(spec["spread_pct"]),
            step=0.001,
            format="%.3f",
            help="Planungswert aus der eToro-Spreads-Tabelle. Tatsächliche Kosten können abweichen."
        )

    direction = st.radio(
        "Richtung",
        ["Long", "Short"],
        horizontal=True
    )

    entry_price = st.number_input(
        "Entry",
        value=16200.0,
        step=1.0
    )
    stop_price = st.number_input(
        "Stop Loss",
        value=15800.0,
        step=1.0
    )
    target_price = st.number_input(
        "Target",
        value=16800.0,
        step=1.0
    )
    atr_val = st.number_input(
        "ATR(14)",
        min_value=0.0,
        value=45.0,
        step=0.5,
        help="Wenn 0: ATR-Filter wird deaktiviert."
    )

# ============================================================
# 5. GEAR ENGINE
# ============================================================
trend_points = sum(
    1.0 if t == "Impulse Wave"
    else (0.5 if t == "Correction" else 0.0)
    for t in [t240, t60, t15]
)

sent_points = sum(
    0.75 if s == "Supportive"
    else (0.25 if s == "Neutral" else 0.0)
    for s in [aaii, fg_index, central_bank, seasonals]
)

penalties = 0.0
if trader_stress == "Mittel":
    penalties += 0.5
elif trader_stress == "Hoch":
    penalties += 1.5

if location != "Home Office":
    penalties += 0.5

total_score = max(0.0, trend_points + sent_points - penalties)

if total_score >= 5.0:
    gear = 5
    min_rrr_req = 2.0
    risk_mult = 1.25
    stop_min_atr = 1.0
    stop_max_atr = 2.0
    scale_out = "Nein – Gewinner ausreizen"
elif total_score >= 3.8:
    gear = 4
    min_rrr_req = 1.8
    risk_mult = 1.00
    stop_min_atr = 1.5
    stop_max_atr = 2.5
    scale_out = "Optional ab 2.0R"
elif total_score >= 2.5:
    gear = 3
    min_rrr_req = 1.5
    risk_mult = 0.80
    stop_min_atr = 1.5
    stop_max_atr = 4.0
    scale_out = "Ja – Teilgewinn ab ca. 1.5R"
elif total_score >= 1.2:
    gear = 2
    min_rrr_req = 1.2
    risk_mult = 0.50
    stop_min_atr = 2.0
    stop_max_atr = 4.0
    scale_out = "Ja – frühzeitig Teilgewinne"
else:
    gear = 1
    min_rrr_req = 0.0
    risk_mult = 0.0
    stop_min_atr = None
    stop_max_atr = None
    scale_out = "N/A"

# ============================================================
# 6. VALIDIERUNG
# ============================================================
if direction == "Long":
    is_valid_direction = stop_price < entry_price < target_price
    validation_msg = (
        "Long: Stop < Entry < Target"
        if is_valid_direction
        else "❌ Long ungültig: Stop muss unter Entry und Target über Entry liegen."
    )
else:
    is_valid_direction = stop_price > entry_price > target_price
    validation_msg = (
        "Short: Stop > Entry > Target"
        if is_valid_direction
        else "❌ Short ungültig: Stop muss über Entry und Target unter Entry liegen."
    )

risk_points = abs(entry_price - stop_price)
reward_points = abs(target_price - entry_price)

calc_rrr = reward_points / risk_points if risk_points > 0 else 0.0

stop_atr_ratio = (
    risk_points / atr_val
    if atr_val > 0
    else None
)

atr_ok = True
atr_message = "ATR-Filter deaktiviert."
if atr_val > 0 and stop_max_atr is not None:
    atr_ok = stop_min_atr <= stop_atr_ratio <= stop_max_atr
    atr_message = (
        f"{stop_atr_ratio:.1f}x ATR – "
        f"erlaubt {stop_min_atr:.1f}x bis {stop_max_atr:.1f}x"
    )

# ============================================================
# 7. RISK ENGINE – FUTURES ODER CFD
# ============================================================
effective_risk_pct = base_risk_pct * risk_mult
risk_budget_eur = account_balance * effective_risk_pct / 100.0

# Tageslimit
daily_loss_limit_eur = account_balance * daily_loss_limit_pct / 100.0
remaining_daily_loss_eur = max(
    0.0,
    daily_loss_limit_eur - daily_loss_used_eur
)

risk_budget_eur = min(risk_budget_eur, remaining_daily_loss_eur)

if product_type == "Futures":
    tick_size = spec["tick_size"]
    tick_value = spec["tick_value"]

    risk_ticks = risk_points / tick_size
    reward_ticks = reward_points / tick_size

    risk_per_contract_native = risk_ticks * tick_value
    reward_per_contract_native = reward_ticks * tick_value

    if spec["currency"] == "USD":
        risk_per_contract_eur = risk_per_contract_native / eurusd
        reward_per_contract_eur = reward_per_contract_native / eurusd
    else:
        risk_per_contract_eur = risk_per_contract_native
        reward_per_contract_eur = reward_per_contract_native

    raw_position_size = (
        risk_budget_eur / risk_per_contract_eur
        if risk_per_contract_eur > 0 else 0.0
    )
    final_contracts = math.floor(raw_position_size)
    actual_risk_eur = final_contracts * risk_per_contract_eur
    actual_reward_eur = final_contracts * reward_per_contract_eur

    position_value_eur = None
    margin_eur = None
    cost_eur = 0.0

else:
    # CFD:
    # point_value ist der Geldwert je Kurs-Punkt für 1 Einheit.
    # Die Positionsgröße wird so bestimmt, dass das Stop-Risiko
    # das verfügbare Risikobudget nicht überschreitet.
    risk_per_unit_native = risk_points * point_value
    reward_per_unit_native = reward_points * point_value

    if spec["currency"] == "USD":
        risk_per_unit_eur = risk_per_unit_native / eurusd
        reward_per_unit_eur = reward_per_unit_native / eurusd
    else:
        risk_per_unit_eur = risk_per_unit_native
        reward_per_unit_eur = reward_per_unit_native

    raw_position_size = (
        risk_budget_eur / risk_per_unit_eur
        if risk_per_unit_eur > 0 else 0.0
    )

    # Bei CFDs kann die Größe je nach Broker/instrument auch
    # fraktional sein. Daher kein automatisches Abrunden auf 1.
    final_contracts = max(0.0, raw_position_size)

    actual_risk_eur = final_contracts * risk_per_unit_eur
    actual_reward_eur = final_contracts * reward_per_unit_eur

    # Positionswert basiert auf Entry * Einheiten.
    if spec["currency"] == "USD":
        position_value_eur = entry_price * final_contracts / eurusd
    else:
        position_value_eur = entry_price * final_contracts

    margin_eur = position_value_eur / leverage if leverage > 0 else 0.0

    # eToro veröffentlicht bei CFDs Öffnungs-/Schließspreads als
    # prozentuale Kosten je nach Instrument. Für die Planung wird
    # hier konservativ mit 2x Spread gerechnet.
    estimated_spread_cost_eur = position_value_eur * (spread_pct / 100.0) * 2.0
    cost_eur = estimated_spread_cost_eur

# Netto-Betrachtung
net_risk_eur = actual_risk_eur + cost_eur
net_reward_eur = max(0.0, actual_reward_eur - cost_eur)
net_rrr = net_reward_eur / net_risk_eur if net_risk_eur > 0 else 0.0

# ============================================================
# 8. DECISION GATE
# ============================================================
news_block = news_soon == "Ja"
stress_block = trader_stress == "Hoch"
gear_block = gear == 1
crv_block = calc_rrr < min_rrr_req
atr_block = not atr_ok
daily_limit_block = remaining_daily_loss_eur <= 0
size_block = final_contracts <= 0

if not is_valid_direction:
    trade_approval = "🔴 NO TRADE – ungültige Preisparameter"
elif news_block:
    trade_approval = "🔴 NO TRADE – High-Impact News < 30 Min."
elif stress_block:
    trade_approval = "🔴 NO TRADE – Trader Condition"
elif gear_block:
    trade_approval = "🔴 NO TRADE – Gear 1"
elif crv_block:
    trade_approval = (
        f"🔴 NO TRADE – CRV {calc_rrr:.2f} < {min_rrr_req:.2f}"
    )
elif atr_block:
    trade_approval = "🔴 NO TRADE – Stop außerhalb der ATR-Gear-Regel"
elif daily_limit_block:
    trade_approval = "🔴 NO TRADE – Tagesverlust-Limit erreicht"
elif size_block:
    trade_approval = "🔴 NO TRADE – Risikobudget reicht nicht aus"
else:
    trade_approval = "🟢 TRADE FREIGEGEBEN"

# ============================================================
# 9. COCKPIT
# ============================================================
st.markdown("---")

gear_symbol = {
    1: "🔴",
    2: "🟠",
    3: "🟡",
    4: "🟢",
    5: "🟢"
}[gear]

gcol1, gcol2, gcol3, gcol4 = st.columns(4)

gcol1.metric("GEAR", f"{gear} {gear_symbol}")
gcol2.metric("Score", f"{total_score:.2f}")
gcol3.metric("CRV", f"{calc_rrr:.2f}")
gcol4.metric("Effektives Risiko", f"{effective_risk_pct:.2f}%")

st.markdown("---")

# ============================================================
# 10. DREI EBENEN
# ============================================================
e1, e2, e3 = st.columns(3)

with e1:
    st.subheader("1️⃣ Umfeld")
    if news_block or stress_block:
        st.error("🔴 Umfeld blockiert")
    else:
        st.success("🟢 Umfeld handelbar")

with e2:
    st.subheader("2️⃣ Aggressivität")
    st.info(
        f"⚙️ Gear {gear} · "
        f"Risiko {effective_risk_pct:.2f}%"
    )

with e3:
    st.subheader("3️⃣ Setup")
    if is_valid_direction and not crv_block and not atr_block:
        st.success(
            f"🟢 Valide · CRV {calc_rrr:.2f}"
        )
    else:
        st.error("🔴 Setup abgelehnt")

# ============================================================
# 11. SCORE-ZERLEGUNG
# ============================================================
with st.expander("📊 Warum dieses Gear?"):
    s1, s2 = st.columns(2)

    with s1:
        st.write(f"Trendstruktur: **+{trend_points:.2f}** / 3.00")
        st.write(f"Sentiment/Makro: **+{sent_points:.2f}** / 3.00")

    with s2:
        st.write(f"Trader-Condition/Standort: **-{penalties:.2f}**")
        st.write(f"Gesamt: **{total_score:.2f} → Gear {gear}**")

# ============================================================
# 12. TRADE DECISION CARD
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
    st.write(f"Produktart: **{product_type}**")
    st.write(f"Instrument: **{market_key}**")
    st.write(f"Richtung: **{direction.upper()}**")

    if product_type == "Futures":
        st.write(f"Kontrakte: **{final_contracts}**")
        st.write(f"Risiko/Contract: **{risk_per_contract_eur:,.2f} €**")
    else:
        st.write(f"Einheiten: **{final_contracts:,.2f}**")
        st.write(f"Hebel: **1:{leverage}**")
        st.write(f"Positionswert: **{position_value_eur:,.2f} €**")
        st.write(f"Margin: **{margin_eur:,.2f} €**")

with dc2:
    st.markdown("**Preis & Setup**")
    st.write(f"Entry: **{entry_price:,.2f}**")
    st.write(f"Stop: **{stop_price:,.2f}**")
    st.write(f"Target: **{target_price:,.2f}**")
    st.write(f"Stop-Distanz: **{risk_points:,.2f} Punkte**")

    if stop_atr_ratio is not None:
        st.write(f"Stop / ATR: **{stop_atr_ratio:.1f}x**")
        st.write(f"ATR-Regel: **{atr_message}**")

with dc3:
    st.markdown("**Risiko & Ergebnis**")
    st.write(f"Risikobudget: **{risk_budget_eur:,.2f} €**")
    st.write(f"Tatsächliches Stop-Risiko: **{actual_risk_eur:,.2f} €**")
    st.write(f"Brutto-Zielgewinn: **{actual_reward_eur:,.2f} €**")

    if product_type == "CFD":
        st.write(f"Geschätzte Spreadkosten: **{cost_eur:,.2f} €**")
        st.write(f"Netto-CRV: **{net_rrr:.2f}**")

    st.write(f"Brutto-CRV: **{calc_rrr:.2f}**")
    st.write(f"Management: **{scale_out}**")

# ============================================================
# 13. CFD-SPEZIALHINWEISE
# ============================================================
if product_type == "CFD":
    st.markdown("---")
    with st.expander("ℹ️ CFD / eToro Hinweise"):
        st.info(
            "Die CFD-Parameter sind Planungswerte. Prüfe vor der Order "
            "den tatsächlich angebotenen Hebel, die Einheiten/Mindestgröße, "
            "den aktuellen Spread und die Overnight-Finanzierung direkt "
            "im eToro-Orderfenster. Diese Werte können sich ändern."
        )

        if holding_period == "Overnight":
            st.warning(
                "Overnight gewählt: mögliche tägliche Finanzierungs-/"
                "Übernachtkosten sind in dieser Version NICHT automatisch "
                "eingerechnet. Für einen präzisen Netto-Trade müssen die "
                "aktuell angezeigten eToro-Finanzierungskosten manuell "
                "ergänzt werden."
            )

# ============================================================
# 14. HANDLUNGSEMPFEHLUNG
# ============================================================
st.markdown("---")
st.subheader("🧭 Was müsste sich ändern?")

reasons = []

if not is_valid_direction:
    reasons.append("Preisstruktur korrigieren: Stop und Target müssen zur Richtung passen.")

if news_block:
    reasons.append("High-Impact News abwarten.")

if stress_block:
    reasons.append("Trader Condition verbessern; bei hohem Stress kein Trade.")

if gear_block:
    reasons.append("Kein Trade bei Gear 1.")

if crv_block:
    required_target = (
        entry_price + risk_points * min_rrr_req
        if direction == "Long"
        else entry_price - risk_points * min_rrr_req
    )
    reasons.append(
        f"Für das Mindest-CRV von {min_rrr_req:.2f} müsste das Target "
        f"mindestens bei {required_target:,.2f} liegen."
    )

if atr_block and atr_val > 0:
    required_stop_distance = atr_val * stop_max_atr
    if direction == "Long":
        suggested_stop = entry_price - required_stop_distance
    else:
        suggested_stop = entry_price + required_stop_distance

    reasons.append(
        f"Stop liegt außerhalb der Gear-ATR-Regel. "
        f"Maximale Stop-Distanz: {required_stop_distance:,.2f} Punkte "
        f"(entspricht ungefähr Stop {suggested_stop:,.2f})."
    )

if daily_limit_block:
    reasons.append("Tagesverlust-Limit erreicht – keine weiteren Trades.")

if not reasons:
    st.success("🟢 Keine Korrektur erforderlich. Setup erfüllt die aktuellen Decision-Gates.")
else:
    for reason in reasons:
        st.write(f"• {reason}")

# ============================================================
# 15. RISIKO-HINWEIS
# ============================================================
st.markdown("---")
st.caption(
    "Hinweis: Dieses Dashboard ist ein regelbasiertes Planungs- und "
    "Risikomanagement-Tool und keine Anlageberatung. Futures und CFDs "
    "sind gehebelte Produkte und können zu erheblichen Verlusten führen. "
    "Insbesondere bei CFDs müssen die aktuell im Broker-Orderfenster "
    "angezeigten Hebel-, Spread- und Finanzierungskonditionen geprüft werden."
)
