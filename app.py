import streamlit as st
import math

# ============================================================
# 1. STREAMLIT CONFIG & DESIGN
# ============================================================
st.set_page_config(
    page_title="Trade Manager & Decision Cockpit v2.8",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ Trade Manager & Decision Cockpit v2.8")
st.caption(
    "Systematisches Decision-Gate – Dual-Limit Sizing "
    "(Risiko vs. Margin), automatische Planungsparameter "
    "für CFDs & Futures sowie Was-wäre-wenn-Analyse"
)
st.markdown("---")


# ============================================================
# 2. INSTRUMENTEN-DATENBANK
#    WICHTIG: Diese Werte sind PLANUNGSANNAHMEN.
#    Sie müssen nicht bei jedem Trade live eingegeben werden.
# ============================================================

FUTURES = {
    "NQ (Nasdaq 100)": {
        "tick_size": 0.25, "tick_value": 5.00, "currency": "USD",
        "margin_native": 18000, "default_comm_roundturn": 4.00,
        "micro_key": "MNQ (Micro Nasdaq)"
    },
    "MNQ (Micro Nasdaq)": {
        "tick_size": 0.25, "tick_value": 0.50, "currency": "USD",
        "margin_native": 1800, "default_comm_roundturn": 1.50,
        "micro_key": None
    },
    "ES (S&P 500)": {
        "tick_size": 0.25, "tick_value": 12.50, "currency": "USD",
        "margin_native": 12000, "default_comm_roundturn": 4.00,
        "micro_key": "MES (Micro S&P)"
    },
    "MES (Micro S&P)": {
        "tick_size": 0.25, "tick_value": 1.25, "currency": "USD",
        "margin_native": 1200, "default_comm_roundturn": 1.50,
        "micro_key": None
    },
    "GC (Gold)": {
        "tick_size": 0.10, "tick_value": 10.00, "currency": "USD",
        "margin_native": 10000, "default_comm_roundturn": 4.50,
        "micro_key": "MGC (Micro Gold)"
    },
    "MGC (Micro Gold)": {
        "tick_size": 0.10, "tick_value": 1.00, "currency": "USD",
        "margin_native": 1000, "default_comm_roundturn": 1.50,
        "micro_key": None
    },
    "CL (Crude Oil)": {
        "tick_size": 0.01, "tick_value": 10.00, "currency": "USD",
        "margin_native": 7000, "default_comm_roundturn": 4.50,
        "micro_key": "MCL (Micro Oil)"
    },
    "MCL (Micro Oil)": {
        "tick_size": 0.01, "tick_value": 1.00, "currency": "USD",
        "margin_native": 700, "default_comm_roundturn": 1.50,
        "micro_key": None
    },
    "FDAX (DAX Future)": {
        "tick_size": 0.50, "tick_value": 12.50, "currency": "EUR",
        "margin_native": 30000, "default_comm_roundturn": 3.00,
        "micro_key": "FDXM (Mini DAX)"
    },
    "FDXM (Mini DAX)": {
        "tick_size": 1.00, "tick_value": 5.00, "currency": "EUR",
        "margin_native": 6000, "default_comm_roundturn": 1.50,
        "micro_key": None
    },
}

CFDS = {
    # Planungswerte – keine Echtzeit-Eingabe pro Trade erforderlich.
    "NASDAQ 100 CFD": {
        "contract_size": 1.0, "point_value": 1.0, "currency": "USD",
        "default_spread": 1.5, "max_leverage": 20,
        "default_overnight_pct": 0.015, "min_units": 0.01,
        "unit_step": 0.01, "margin_model": "Leverage-Based"
    },
    "S&P 500 CFD": {
        "contract_size": 1.0, "point_value": 1.0, "currency": "USD",
        "default_spread": 0.5, "max_leverage": 20,
        "default_overnight_pct": 0.015, "min_units": 0.01,
        "unit_step": 0.01, "margin_model": "Leverage-Based"
    },
    "GER40 CFD": {
        "contract_size": 1.0, "point_value": 1.0, "currency": "EUR",
        "default_spread": 1.0, "max_leverage": 20,
        "default_overnight_pct": 0.015, "min_units": 0.01,
        "unit_step": 0.01, "margin_model": "Leverage-Based"
    },
    "Gold CFD": {
        "contract_size": 1.0, "point_value": 1.0, "currency": "USD",
        "default_spread": 0.30, "max_leverage": 20,
        "default_overnight_pct": 0.020, "min_units": 0.01,
        "unit_step": 0.01, "margin_model": "Leverage-Based"
    },
    "Oil CFD": {
        "contract_size": 1.0, "point_value": 1.0, "currency": "USD",
        "default_spread": 0.04, "max_leverage": 10,
        "default_overnight_pct": 0.025, "min_units": 0.01,
        "unit_step": 0.01, "margin_model": "Leverage-Based"
    },
}


# ============================================================
# 3. SIDEBAR – KONTO & RISIKOPARAMETER
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
        help="Planungs-Margin bestehender offener Positionen."
    )

    free_margin_eur = max(0.0, account_balance - used_margin_eur)

    st.caption(
        f"Verfügbare freie Planungs-Margin: "
        f"**{free_margin_eur:,.2f} €**"
    )

    base_risk_pct = st.select_slider(
        "Basis-Risikoklasse (%)",
        options=[0.25, 0.50, 0.75, 1.00, 1.50, 2.00],
        value=1.00
    )

    eurusd = st.number_input(
        "EUR/USD Planungskurs",
        min_value=0.01, value=1.17, step=0.01,
        help="Planungskurs – kein Echtzeitkurs erforderlich."
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
        "Offenes Risiko ANDERER Positionen (€)",
        min_value=0.0, value=0.0, step=50.0,
        help="Risiko sonstiger offener Trades."
    )


# ============================================================
# 4. HAUPT-INPUTS
# ============================================================

col_market, col_trader, col_setup = st.columns([1.1, 1.0, 1.2])


with col_market:
    st.subheader("1. Markt-Umfeld")
    st.markdown("**Multi-Timeframe Trend**")

    t240 = st.selectbox(
        "4H Trend",
        ["Impulse Wave", "Correction", "Choppy / Sideways"], index=0
    )
    t60 = st.selectbox(
        "1H Trend",
        ["Impulse Wave", "Correction", "Choppy / Sideways"], index=0
    )
    t15 = st.selectbox(
        "15M Trend",
        ["Impulse Wave", "Correction", "Choppy / Sideways"], index=0
    )

    st.markdown("**Macro & Sentiment**")

    aaii = st.selectbox(
        "AAII Sentiment",
        ["Supportive", "Neutral", "Not supportive"], index=0
    )
    fg_index = st.selectbox(
        "Fear & Greed Index",
        ["Supportive", "Neutral", "Not supportive"], index=1
    )
    central_bank = st.selectbox(
        "Notenbank-Politik",
        ["Supportive", "Neutral", "Not supportive"], index=1
    )
    seasonals = st.selectbox(
        "Saisonalität",
        ["Supportive", "Neutral", "Not supportive"], index=0
    )


with col_trader:
    st.subheader("2. Trader Condition")
    st.markdown("**Verfassungs-Check**")

    trader_stress = st.select_slider(
        "Stress / Müdigkeit / Zeitdruck",
        options=["Niedrig", "Mittel", "Hoch"], value="Niedrig"
    )

    location = st.selectbox(
        "Standort",
        ["Home Office", "Mobil / Unterwegs", "Fremdes Büro"]
    )

    st.markdown("**News & Haltedauer**")

    news_soon = st.radio(
        "High-Impact News < 30 Min?",
        ["Nein", "Ja"], horizontal=True
    )

    holding_period = st.radio(
        "Haltedauer",
        ["Intraday", "Overnight"], horizontal=True
    )

    overnight_nights = 0
    extra_fee_units = 0

    if holding_period == "Overnight":
        c_n1, c_n2 = st.columns(2)
        overnight_nights = c_n1.number_input(
            "Haltedauer (Nächte)",
            min_value=1, max_value=30, value=1
        )
        extra_fee_units = c_n2.number_input(
            "Zusätzl. Gebühreneinheiten",
            min_value=0, max_value=10, value=0,
            help="Z.B. +2 für Wochenend-/Triple-Fee als Planungsannahme."
        )


with col_setup:
    st.subheader("3. Produkt & Setup")

    product_type = st.radio(
        "Produktart", ["Futures", "CFD"], horizontal=True
    )

    if product_type == "Futures":
        market_key = st.selectbox(
            "Futures-Instrument", list(FUTURES.keys())
        )
        spec = FUTURES[market_key]

        leverage = None

        fut_comm_rt_native = spec["default_comm_roundturn"]

        spread_points = 0.0
        daily_overnight_pct = 0.0

        st.caption(
            f"Planungs-Kommission: "
            f"{fut_comm_rt_native:.2f} {spec['currency']} R/T"
        )

    else:
        market_key = st.selectbox(
            "CFD-Instrument", list(CFDS.keys())
        )
        spec = CFDS[market_key]

        leverage_options = [
            l for l in [1, 2, 5, 10, 20, 30]
            if l <= spec["max_leverage"]
        ]

        leverage = st.select_slider(
            "CFD-Hebel",
            options=leverage_options,
            value=(
                spec["max_leverage"]
                if spec["max_leverage"] in leverage_options
                else leverage_options[-1]
            ),
            help=(
                "Planungshebel für die Margin-Berechnung. "
                "Kein Einfluss auf das Stop-Loss-Risiko."
            )
        )

        # Keine Echtzeitkosten-Eingabe mehr:
        # Spread und Overnight werden automatisch aus der
        # Instrumenten-Datenbank als Planungswerte verwendet.
        spread_points = spec["default_spread"]
        daily_overnight_pct = spec["default_overnight_pct"]

        st.caption(
            f"Automatische Planungsannahmen: "
            f"Spread {spread_points:g} Punkte · "
            f"Overnight {daily_overnight_pct:.3f}%/Tag"
        )

        st.info(
            "ℹ️ Spread und Overnight werden automatisch als "
            "Planungswerte verwendet. Eine Eingabe von "
            "Echtzeitwerten ist für den einzelnen Trade nicht nötig."
        )

        fut_comm_rt_native = 0.0

    direction = st.radio(
        "Richtung", ["Long", "Short"], horizontal=True
    )

    entry_price = st.number_input(
        "Entry", value=16200.0, step=1.0
    )
    stop_price = st.number_input(
        "Stop Loss", value=15800.0, step=1.0
    )
    target_price = st.number_input(
        "Target", value=16800.0, step=1.0
    )
    atr_val = st.number_input(
        "ATR(14)",
        min_value=0.0, value=45.0, step=0.5,
        help="Bei 0: ATR-Filter deaktiviert."
    )


# ============================================================
# 5. GEAR ENGINE
# ============================================================

trend_points = sum(
    1.0 if t == "Impulse Wave" else (0.5 if t == "Correction" else 0.0)
    for t in [t240, t60, t15]
)

sent_points = sum(
    0.75 if s == "Supportive" else (0.25 if s == "Neutral" else 0.0)
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
    risk_mult = 1.00
    stop_min_atr = 1.0
    stop_max_atr = 2.0
    scale_out = "Nein – Gewinner voll ausreizen"
elif total_score >= 3.8:
    gear = 4
    min_rrr_req = 1.8
    risk_mult = 0.90
    stop_min_atr = 1.5
    stop_max_atr = 2.5
    scale_out = "Optional ab 2.0R"
elif total_score >= 2.5:
    gear = 3
    min_rrr_req = 1.5
    risk_mult = 0.75
    stop_min_atr = 1.5
    stop_max_atr = 4.0
    scale_out = "Ja – Teilgewinn ab 1.5R"
elif total_score >= 1.2:
    gear = 2
    min_rrr_req = 1.2
    risk_mult = 0.50
    stop_min_atr = 2.0
    stop_max_atr = 4.0
    scale_out = "Ja – frühzeitige Skalierung"
else:
    gear = 1
    min_rrr_req = 0.0
    risk_mult = 0.0
    stop_min_atr = None
    stop_max_atr = None
    scale_out = "N/A"


# ============================================================
# 6. PRE-CALCULATION
# ============================================================

if direction == "Long":
    is_valid_direction = stop_price < entry_price < target_price
else:
    is_valid_direction = stop_price > entry_price > target_price

risk_points = abs(entry_price - stop_price)
reward_points = abs(target_price - entry_price)

gross_rrr = reward_points / risk_points if risk_points > 0 else 0.0


# ============================================================
# 7. ATR ENGINE – ZERO SAFE
# ============================================================

stop_atr_ratio = (
    risk_points / atr_val
    if atr_val > 0
    else None
)

atr_ok = True

if (
    atr_val > 0
    and stop_min_atr is not None
    and stop_max_atr is not None
):
    atr_ok = stop_min_atr <= stop_atr_ratio <= stop_max_atr


# ============================================================
# 8. RISIKOBUDGET
# ============================================================

effective_risk_pct = base_risk_pct * risk_mult
risk_budget_eur = account_balance * effective_risk_pct / 100.0

daily_loss_limit_eur = account_balance * daily_loss_limit_pct / 100.0

total_daily_risk_used_eur = (
    daily_loss_realized_eur + daily_open_risk_eur
)

remaining_daily_loss_eur = max(
    0.0,
    daily_loss_limit_eur - total_daily_risk_used_eur
)

risk_budget_eur = min(
    risk_budget_eur,
    remaining_daily_loss_eur
)


# ============================================================
# 9. DUAL-LIMIT SIZING ENGINE
# ============================================================

def calculate_position_dual(
    p_type,
    m_key,
    budget_eur,
    free_marg_eur,
    is_overnight,
    nights,
    extra_units,
    fut_comm_override=None
):
    if (
        budget_eur <= 0
        or risk_points <= 0
        or free_marg_eur <= 0
    ):
        return {
            "units": 0.0 if p_type == "CFD" else 0,
            "max_risk_units": 0,
            "max_margin_units": 0,
            "limit_reason": "Kein Budget / Margin verfügbar",
            "act_stop_risk": 0.0,
            "act_reward": 0.0,
            "m_req": 0.0,
            "tot_spread": 0.0,
            "tot_overnight": 0.0,
            "tot_comm": 0.0,
            "pos_val": 0.0
        }

    # ========================================================
    # FUTURES
    # ========================================================
    if p_type == "Futures":
        f_spec = FUTURES[m_key]
        fx_conv = eurusd if f_spec["currency"] == "USD" else 1.0

        r_ticks = risk_points / f_spec["tick_size"]
        stop_risk_per_contract_eur = (
            r_ticks * f_spec["tick_value"] / fx_conv
        )

        comm_native = (
            fut_comm_override
            if fut_comm_override is not None
            else f_spec["default_comm_roundturn"]
        )
        comm_eur_per_contract = comm_native / fx_conv

        # Für Sizing: Stop-Risiko + Kosten.
        total_risk_per_contract = (
            stop_risk_per_contract_eur + comm_eur_per_contract
        )

        max_risk_units = (
            math.floor(budget_eur / total_risk_per_contract)
            if total_risk_per_contract > 0
            else 0
        )

        margin_per_contract_eur = (
            f_spec["margin_native"] / fx_conv
        )

        max_margin_units = (
            math.floor(free_marg_eur / margin_per_contract_eur)
            if margin_per_contract_eur > 0
            else 0
        )

        units = min(max_risk_units, max_margin_units)

        if max_risk_units == 0 and max_margin_units == 0:
            limit_reason = (
                "Sowohl Risikobudget als auch freie Margin unzureichend"
            )
        elif max_risk_units < max_margin_units:
            limit_reason = "Risikobudget"
        elif max_margin_units < max_risk_units:
            limit_reason = "Freie Planungs-Margin"
        else:
            limit_reason = "Risikobudget & Margin identisch"

        act_stop_risk = units * stop_risk_per_contract_eur

        rew_ticks = reward_points / f_spec["tick_size"]
        act_reward = (
            units * rew_ticks * f_spec["tick_value"] / fx_conv
        )

        tot_comm = units * comm_eur_per_contract
        m_req = units * margin_per_contract_eur

        return {
            "units": units,
            "max_risk_units": max_risk_units,
            "max_margin_units": max_margin_units,
            "limit_reason": limit_reason,
            "act_stop_risk": act_stop_risk,
            "act_reward": act_reward,
            "m_req": m_req,
            "tot_spread": 0.0,
            "tot_overnight": 0.0,
            "tot_comm": tot_comm,
            "pos_val": 0.0
        }

    # ========================================================
    # CFD
    # ========================================================
    c_spec = CFDS[m_key]
    fx_conv = eurusd if c_spec["currency"] == "USD" else 1.0

    stop_cost_per_unit = (
        risk_points
        * c_spec["point_value"]
        * c_spec["contract_size"]
        / fx_conv
    )

    spread_cost_per_unit = (
        spread_points
        * c_spec["point_value"]
        * c_spec["contract_size"]
        / fx_conv
    )

    overnight_cost_per_unit = 0.0

    if is_overnight:
        total_fee_days = nights + extra_units

        overnight_cost_per_unit = (
            entry_price
            * c_spec["point_value"]
            * c_spec["contract_size"]
            / fx_conv
            * (daily_overnight_pct / 100.0)
            * total_fee_days
        )

    total_costs_per_unit = (
        spread_cost_per_unit + overnight_cost_per_unit
    )

    # Kosten werden HIER für das Sizing berücksichtigt.
    # Sie werden NICHT in act_stop_risk eingerechnet.
    total_risk_per_unit_eur = (
        stop_cost_per_unit + total_costs_per_unit
    )

    nominal_per_unit_eur = (
        entry_price
        * c_spec["point_value"]
        * c_spec["contract_size"]
        / fx_conv
    )

    margin_per_unit_eur = (
        nominal_per_unit_eur / leverage
        if leverage > 0
        else 0.0
    )

    raw_risk_units = (
        budget_eur / total_risk_per_unit_eur
        if total_risk_per_unit_eur > 0
        else 0.0
    )

    raw_margin_units = (
        free_marg_eur / margin_per_unit_eur
        if margin_per_unit_eur > 0
        else 0.0
    )

    max_risk_units = (
        math.floor(raw_risk_units / c_spec["unit_step"])
        * c_spec["unit_step"]
    )

    max_margin_units = (
        math.floor(raw_margin_units / c_spec["unit_step"])
        * c_spec["unit_step"]
    )

    units = min(max_risk_units, max_margin_units)

    if units < c_spec["min_units"]:
        units = 0.0

    if (
        max_risk_units < c_spec["min_units"]
        and max_margin_units < c_spec["min_units"]
    ):
        limit_reason = (
            "Sowohl Risikobudget als auch freie Margin "
            "unter Mindestgröße"
        )
    elif max_risk_units < max_margin_units:
        limit_reason = "Risikobudget"
    elif max_margin_units < max_risk_units:
        limit_reason = "Freie Planungs-Margin"
    else:
        limit_reason = "Risikobudget & Margin identisch"

    # Eindeutige Trennung:
    # Stop-Risiko = ausschließlich der Verlust bis zum Stop.
    act_stop_risk = units * stop_cost_per_unit

    tot_spread = units * spread_cost_per_unit
    tot_overnight = units * overnight_cost_per_unit

    act_reward = (
        units
        * reward_points
        * c_spec["point_value"]
        * c_spec["contract_size"]
        / fx_conv
    )

    pos_val = (
        entry_price
        * units
        * c_spec["point_value"]
        * c_spec["contract_size"]
        / fx_conv
    )

    m_req = units * margin_per_unit_eur

    return {
        "units": units,
        "max_risk_units": max_risk_units,
        "max_margin_units": max_margin_units,
        "limit_reason": limit_reason,
        "act_stop_risk": act_stop_risk,
        "act_reward": act_reward,
        "m_req": m_req,
        "tot_spread": tot_spread,
        "tot_overnight": tot_overnight,
        "tot_comm": 0.0,
        "pos_val": pos_val
    }


# ============================================================
# 10. POSITION CALCULATION
# ============================================================

is_on = holding_period == "Overnight"

sizing_res = calculate_position_dual(
    product_type,
    market_key,
    risk_budget_eur,
    free_margin_eur,
    is_on,
    overnight_nights,
    extra_fee_units,
    fut_comm_rt_native
)

final_contracts = sizing_res["units"]
actual_stop_risk_eur = sizing_res["act_stop_risk"]
actual_reward_eur = sizing_res["act_reward"]
required_margin_eur = sizing_res["m_req"]
spread_cost_eur = sizing_res["tot_spread"]
overnight_cost_eur = sizing_res["tot_overnight"]
comm_cost_eur = sizing_res["tot_comm"]
position_value_eur = sizing_res["pos_val"]
sizing_limit_reason = sizing_res["limit_reason"]


# ============================================================
# 11. MICRO-FALLBACK
# ============================================================

micro_active = False
micro_key_found = None
micro_contracts = 0
macro_risk_needed_for_1_contract = 0.0
micro_comm_used_native = 0.0

if product_type == "Futures" and final_contracts == 0:
    macro_spec = FUTURES[market_key]
    fx_conv = eurusd if macro_spec["currency"] == "USD" else 1.0

    macro_stop = (
        (risk_points / macro_spec["tick_size"])
        * macro_spec["tick_value"]
        / fx_conv
    )

    macro_comm = fut_comm_rt_native / fx_conv

    macro_risk_needed_for_1_contract = macro_stop + macro_comm
    micro_key_found = macro_spec.get("micro_key")

    if micro_key_found:
        micro_spec = FUTURES[micro_key_found]

        micro_comm_used_native = (
            fut_comm_rt_native
            * (micro_spec["tick_value"] / macro_spec["tick_value"])
        )

        m_res = calculate_position_dual(
            "Futures",
            micro_key_found,
            risk_budget_eur,
            free_margin_eur,
            is_on,
            overnight_nights,
            extra_fee_units,
            micro_comm_used_native
        )

        m_cnt = m_res["units"]

        if m_cnt > 0:
            m_tot_cost = m_res["tot_comm"]
            m_net_risk = m_res["act_stop_risk"] + m_tot_cost
            m_net_rew = max(0.0, m_res["act_reward"] - m_tot_cost)

            m_net_rrr = (
                m_net_rew / m_net_risk
                if m_net_risk > 0
                else 0.0
            )

            if is_valid_direction and m_net_rrr >= min_rrr_req:
                micro_active = True
                micro_contracts = m_cnt
                final_contracts = m_cnt
                actual_stop_risk_eur = m_res["act_stop_risk"]
                actual_reward_eur = m_res["act_reward"]
                required_margin_eur = m_res["m_req"]
                comm_cost_eur = m_res["tot_comm"]
                sizing_limit_reason = m_res["limit_reason"]
                sizing_res = m_res


# ============================================================
# 12. FINAL COST & RISK ENGINE
# ============================================================

total_costs_eur = (
    spread_cost_eur + overnight_cost_eur + comm_cost_eur
)

stop_loss_risk_eur = actual_stop_risk_eur

# Netto-Risiko enthält Stop + Kosten.
net_risk_eur = stop_loss_risk_eur + total_costs_eur

net_reward_eur = max(
    0.0,
    actual_reward_eur - total_costs_eur
)

net_rrr = (
    net_reward_eur / net_risk_eur
    if net_risk_eur > 0
    else 0.0
)

risk_budget_exceeded = (
    net_risk_eur > risk_budget_eur + 0.01
)


# ============================================================
# 13. HIERARCHISCHES DECISION GATE
# ============================================================

primary_blockers = []
secondary_blockers = []

if not is_valid_direction:
    primary_blockers.append((
        "🔴 Ungültige Preisstruktur",
        "Stop Loss & Target-Order passen nicht zur Richtung."
    ))

if news_soon == "Ja":
    primary_blockers.append((
        "🔴 High-Impact News",
        "Macro-Event (<30 Min) blockiert die Ausführung."
    ))

if trader_stress == "Hoch":
    primary_blockers.append((
        "🔴 Trader Verfassung",
        "Stress-Level verlangt Trading-Pause."
    ))

if gear == 1:
    primary_blockers.append((
        "🔴 Gear 1 (Marktumfeld)",
        "Gesamt-Score unzureichend."
    ))

if remaining_daily_loss_eur <= 0:
    primary_blockers.append((
        "🔴 Tagesverlust-Limit",
        "Tages-Risikobudget vollständig verbraucht."
    ))

if not atr_ok and atr_val > 0:
    secondary_blockers.append((
        "🔴 ATR-Filter Verletzung",
        (
            f"Stop-Abstand ({stop_atr_ratio:.1f}x ATR) "
            f"liegt außerhalb des Korridors "
            f"({stop_min_atr:.1f}x - {stop_max_atr:.1f}x)."
        )
    ))

if final_contracts <= 0 and not micro_active:
    secondary_blockers.append((
        "🔴 Keine handelbare Positionsgröße",
        f"Limitierender Faktor: {sizing_limit_reason}."
    ))

if net_rrr < min_rrr_req and final_contracts > 0:
    secondary_blockers.append((
        "🔴 Netto-CRV zu gering",
        (
            f"Netto-CRV {net_rrr:.2f} untersteht "
            f"gefordertem Minimum von {min_rrr_req:.2f}."
        )
    ))

if risk_budget_exceeded:
    secondary_blockers.append((
        "🔴 Risikobudget überschritten",
        (
            f"Netto-Risiko {net_risk_eur:,.2f} € "
            f"> Budget {risk_budget_eur:,.2f} €."
        )
    ))

all_blockers = primary_blockers + secondary_blockers


# ============================================================
# 14. TRADE APPROVAL
# ============================================================

if not all_blockers:
    if micro_active:
        trade_approval = (
            "🟢 TRADE FREIGEGEBEN "
            f"(Micro-Fallback: {micro_contracts}x {micro_key_found})"
        )
    else:
        trade_approval = "🟢 TRADE FREIGEGEBEN"
else:
    trade_approval = (
        f"🔴 NO TRADE – {len(all_blockers)} Blocker aktiv"
    )


# ============================================================
# 15. COCKPIT METRIKEN
# ============================================================

st.markdown("---")

gcol1, gcol2, gcol3, gcol4 = st.columns(4)

gear_symbol = {
    1: "🔴", 2: "🟠", 3: "🟡", 4: "🟢", 5: "🟢"
}[gear]

gcol1.metric("GEAR", f"{gear} {gear_symbol}")
gcol2.metric("Score", f"{total_score:.2f}")
gcol3.metric(
    "Netto-CRV",
    f"{net_rrr:.2f}",
    delta=f"Brutto {gross_rrr:.2f}"
)
gcol4.metric(
    "Verfügbares Tagesrisiko",
    f"{remaining_daily_loss_eur:,.2f} €"
)


# ============================================================
# 16. DREI-EBENEN-CHECK
# ============================================================

st.markdown("---")

e1, e2, e3 = st.columns(3)

with e1:
    st.subheader("1️⃣ Umfeld")
    if primary_blockers:
        st.error("🔴 Umfeld blockiert")
    else:
        st.success("🟢 Umfeld handelbar")

with e2:
    st.subheader("2️⃣ Aggressivität")
    st.info(
        f"⚙️ Gear {gear} · Risiko {effective_risk_pct:.2f}%"
    )

with e3:
    st.subheader("3️⃣ Setup")
    if (
        is_valid_direction
        and atr_ok
        and net_rrr >= min_rrr_req
        and final_contracts > 0
        and not risk_budget_exceeded
    ):
        st.success(f"🟢 Valide · Netto-CRV {net_rrr:.2f}")
    else:
        st.error("🔴 Setup abgelehnt")

if atr_val == 0:
    st.warning(
        "⚠️ **ATR deaktiviert** – "
        "Volatilitätsbasierter Stop-Filter ist abgeschaltet."
    )


# ============================================================
# 17. DECISION CARD
# ============================================================

st.markdown("---")
st.subheader("📋 Trade Decision Card")

if not all_blockers:
    st.success(f"## {trade_approval}")
else:
    st.error(f"## {trade_approval}")


# ============================================================
# 18. BLOCKER DIAGNOSE
# ============================================================

if primary_blockers or secondary_blockers:
    st.markdown("### ❌ Blocker-Diagnose")

    if primary_blockers:
        st.markdown("**Primäre Struktur-Blocker (Hard Stops):**")
        for b_title, b_desc in primary_blockers:
            st.write(f"• **{b_title}**: {b_desc}")

    if secondary_blockers:
        st.markdown(
            "**Sekundäre Ausführungs-Blocker (Setup / Sizing):**"
        )
        for b_title, b_desc in secondary_blockers:
            st.write(f"• **{b_title}**: {b_desc}")


# ============================================================
# 19. DUAL-LIMIT MATRIX
# ============================================================

st.markdown("#### ⚖️ Dual-Limit Sizing Matrix")

limit_unit_label = (
    "Kontrakte" if product_type == "Futures" else "Einheiten"
)

matrix_data = {
    "Limit-Ebene": [
        "1. Risikobudget",
        "2. Freie Planungs-Margin",
        "Resultierende Position"
    ],
    "Max. Einheiten": [
        f"{sizing_res['max_risk_units']:,.2f} {limit_unit_label}",
        f"{sizing_res['max_margin_units']:,.2f} {limit_unit_label}",
        f"**{final_contracts:,.2f} {limit_unit_label}**"
    ],
    "Limitierender Faktor": [
        f"Max. Risikobudget: {risk_budget_eur:,.2f} €",
        f"Freie Margin: {free_margin_eur:,.2f} €",
        f"**{sizing_limit_reason}**"
    ]
}

st.table(matrix_data)


# ============================================================
# 20. PRODUKT / PREIS / KOSTEN
# ============================================================

dc1, dc2, dc3 = st.columns(3)

with dc1:
    st.markdown("**Produkt & Ausführung**")

    if micro_active:
        st.write(f"Original: **{market_key}**")
        st.write(
            f"1 Kontrakt benötigt: "
            f"**{macro_risk_needed_for_1_contract:,.2f} €**"
        )
        st.write(f"Ausweich-Instrument: **{micro_key_found}**")
        st.write(f"Handelsgröße: **{micro_contracts} Kontrakte**")
        st.write(
            f"Micro-Kommission (proportional): "
            f"**{micro_comm_used_native:.2f} USD R/T**"
        )
        st.write(
            f"Gebundene Planungs-Margin: "
            f"**{required_margin_eur:,.2f} €**"
        )
    else:
        st.write(f"Produktart: **{product_type}**")
        st.write(f"Instrument: **{market_key}**")
        st.write(f"Richtung: **{direction.upper()}**")

        if product_type == "Futures":
            st.write(
                f"Handelsgröße: **{final_contracts} Kontrakte**"
            )
            st.write(
                f"Gebundene Planungs-Margin: "
                f"**{required_margin_eur:,.2f} €**"
            )
        else:
            st.write(
                f"Handelsgröße: **{final_contracts:,.2f} Einheiten**"
            )
            st.write(f"Hebel: **1:{leverage}**")
            st.write(
                f"Nominaler Positionswert: "
                f"**{position_value_eur:,.2f} €**"
            )
            st.write(
                f"Gebundene Planungs-Margin: "
                f"**{required_margin_eur:,.2f} €**"
            )

with dc2:
    st.markdown("**Preis & Setup**")
    st.write(f"Entry: **{entry_price:,.2f}**")
    st.write(f"Stop Loss: **{stop_price:,.2f}**")
    st.write(f"Target: **{target_price:,.2f}**")
    st.write(
        f"Stop-Distanz: **{risk_points:,.2f} Punkte**"
    )

    if stop_atr_ratio is not None:
        st.write(f"Stop / ATR: **{stop_atr_ratio:.1f}x**")
    else:
        st.write("Stop / ATR: **deaktiviert**")

with dc3:
    st.markdown("**Kosten & Effektives Risiko**")
    st.write(
        f"Max. Risikobudget: **{risk_budget_eur:,.2f} €**"
    )
    st.write(
        f"Brutto Stop-Risiko: **{actual_stop_risk_eur:,.2f} €**"
    )

    if product_type == "Futures":
        st.write(
            f"Börsen-Kommission (Planung): "
            f"**{comm_cost_eur:,.2f} €**"
        )
    else:
        st.write(
            f"CFD Spread-Kosten (Planung): "
            f"**{spread_cost_eur:,.2f} €**"
        )
        st.write(
            f"CFD Overnight-Kosten (Planung): "
            f"**{overnight_cost_eur:,.2f} €**"
        )

    st.write(
        f"Gesamtkosten: **{total_costs_eur:,.2f} €**"
    )
    st.write(
        f"Netto-Risiko: **{net_risk_eur:,.2f} €**"
    )
    st.write(
        f"Netto-CRV: **{net_rrr:.2f}** "
        f"(Brutto: {gross_rrr:.2f})"
    )


# ============================================================
# 21. WAS-WÄRE-WENN ANALYSE
#    ROBUST: keine Division durch 0 und klare CFD/Futures-Trennung
# ============================================================

st.markdown("---")
st.subheader("🧭 Was-wäre-wenn-Analyse & Handlungsoptionen")

if all_blockers:
    st.write(
        "Um eine Handelsfreigabe für dieses Setup zu erreichen, "
        "stehen folgende Anpassungspfade bereit:"
    )

    # --------------------------------------------------------
    # PFAD A – TARGET
    # --------------------------------------------------------
    # Nur sinnvoll, wenn bereits eine handelbare Positionsgröße
    # vorhanden ist. Dadurch wird auch verhindert, dass bei einem
    # Grenzfall durch 0 geteilt wird.
    if net_rrr < min_rrr_req and final_contracts > 0:
        required_net_reward_eur = (
            min_rrr_req * net_risk_eur
        )

        required_gross_reward_eur = (
            required_net_reward_eur + total_costs_eur
        )

        if product_type == "CFD":
            # CFD-Datenbank ausschließlich im CFD-Pfad verwenden.
            c_spec_path = CFDS[market_key]

            fx_conv_path = (
                eurusd
                if c_spec_path["currency"] == "USD"
                else 1.0
            )

            reward_value_per_unit_eur = (
                c_spec_path["point_value"]
                * c_spec_path["contract_size"]
                / fx_conv_path
            )

            denom = (
                reward_value_per_unit_eur
                * final_contracts
            )

        else:
            active_future = (
                micro_key_found
                if micro_active
                else market_key
            )

            f_spec_path = FUTURES[active_future]

            fx_conv_path = (
                eurusd
                if f_spec_path["currency"] == "USD"
                else 1.0
            )

            value_per_point_native = (
                f_spec_path["tick_value"]
                / f_spec_path["tick_size"]
            )

            value_per_point_eur = (
                value_per_point_native
                / fx_conv_path
            )

            denom = (
                value_per_point_eur
                * final_contracts
            )

        # Zusätzliche Sicherheitsprüfung gegen ZeroDivisionError.
        reward_points_needed = (
            required_gross_reward_eur / denom
            if denom > 0
            else 0.0
        )

        if reward_points_needed > 0:
            target_needed = (
                entry_price + reward_points_needed
                if direction == "Long"
                else entry_price - reward_points_needed
            )

            st.write(
                f"• **Pfad A – Target verschieben:** "
                f"Target auf **{target_needed:,.2f}** anpassen, "
                f"um das geforderte Netto-CRV von "
                f"**{min_rrr_req:.2f}** zu erreichen."
            )

    # --------------------------------------------------------
    # PFAD B – STOP
    # --------------------------------------------------------
    # ATR=0 bedeutet bewusst deaktivierten ATR-Filter.
    # stop_max_atr kann bei Gear 1 None sein. Beides wird
    # deshalb explizit abgesichert.
    if (
        not atr_ok
        and atr_val > 0
        and stop_max_atr is not None
    ):
        max_stop_distance = (
            atr_val * stop_max_atr
        )

        s_suggest = (
            entry_price - max_stop_distance
            if direction == "Long"
            else entry_price + max_stop_distance
        )

        st.write(
            f"• **Pfad B – Stop anpassen:** "
            f"Stop-Abstand auf maximal "
            f"**{max_stop_distance:,.2f} Punkte** "
            f"({stop_max_atr:.1f}x ATR) reduzieren "
            f"(Stop bei **{s_suggest:,.2f}**)."
        )

    # --------------------------------------------------------
    # PFAD C – SIZING / KAPITAL
    # --------------------------------------------------------
    if final_contracts <= 0:
        if (
            product_type == "Futures"
            and FUTURES[market_key].get("micro_key")
        ):
            st.write(
                f"• **Pfad C – Instrumenten-Wechsel:** "
                f"Hauptkontrakt zu groß für Risikobudget "
                f"({risk_budget_eur:,.2f} €). "
                f"Auf **{FUTURES[market_key]['micro_key']}** ausweichen."
            )

        elif "Margin" in sizing_limit_reason:
            st.write(
                f"• **Pfad C – Kapital freigeben:** "
                f"Freie Planungs-Margin unzureichend "
                f"({free_margin_eur:,.2f} €). "
                f"Positionen schließen oder Margin-Bedarf verringern."
            )

        else:
            st.write(
                f"• **Pfad C – Risikobudget:** "
                f"Risikobudget ({risk_budget_eur:,.2f} €) "
                f"zu gering für die Mindestkontraktgröße."
            )

    # --------------------------------------------------------
    # PFAD D – TRADE VERWERFEN
    # --------------------------------------------------------
    st.write(
        "• **Pfad D – Trade verworfen:** "
        "Setup ablehnen und auf ein regelkonformes Umfeld warten."
    )

else:
    st.success(
        "🟢 Das Setup entspricht sämtlichen quantitativen Vorgaben. "
        "Keinerlei Anpassung notwendig."
    )


# 22. TRANSPARENTER RISIKO-BREAKDOWN
# ============================================================

st.markdown("---")
st.subheader("🔎 Risiko-Breakdown")

r1, r2, r3, r4 = st.columns(4)

r1.metric("Stop-Risiko", f"{stop_loss_risk_eur:,.2f} €")
r2.metric("Kosten", f"{total_costs_eur:,.2f} €")
r3.metric("Netto-Risiko", f"{net_risk_eur:,.2f} €")
r4.metric("Risiko-Budget", f"{risk_budget_eur:,.2f} €")

if risk_budget_exceeded:
    st.error(
        "⚠️ Das berechnete Netto-Risiko überschreitet "
        "das verfügbare Risikobudget."
    )
else:
    st.success(
        "🟢 Netto-Risiko liegt innerhalb des verfügbaren "
        "Risikobudgets."
    )


# ============================================================
# 23. PLANUNGSPARAMETER-TRANSPARENZ
# ============================================================

st.markdown("---")
st.subheader("ℹ️ Verwendete Planungsparameter")

if product_type == "CFD":
    p1, p2, p3 = st.columns(3)

    p1.metric("Planungs-Spread", f"{spread_points:g} Punkte")
    p2.metric(
        "Overnight / Tag",
        f"{daily_overnight_pct:.3f}%"
    )
    p3.metric("Planungs-Hebel", f"1:{leverage}")

    st.caption(
        "Diese Werte sind bewusst als stabile Planungsannahmen "
        "hinterlegt. Für das Decision Gate müssen nicht bei "
        "jedem Trade aktuelle Spread- oder Overnight-Werte "
        "manuell eingegeben werden."
    )
else:
    st.caption(
        f"Futures-Planung: Kommission "
        f"{fut_comm_rt_native:.2f} {spec['currency']} R/T · "
        f"Margin {spec['margin_native']:,.0f} "
        f"{spec['currency']} je Kontrakt."
    )


# ============================================================
# 24. DISCLOSURE
# ============================================================

st.markdown("---")
st.caption(
    "Hinweis: v2.8 Cockpit ist ein rein quantitatives Decision Gate. "
    "Spread-, Overnight-, Kommissions- und Marginwerte sind "
    "Planungsannahmen und keine Echtzeit-Brokerdaten. "
    "Sie müssen regelmäßig gegen die tatsächlichen Brokerbedingungen "
    "validiert werden. Keine Anlageberatung."
)
