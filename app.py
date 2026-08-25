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
    "(Risiko vs. Margin), richtungsabhängige MTF-/Sentimentbewertung, "
    "transparente Kostenplanung & Was-wäre-wenn-Analyse"
)

st.markdown("---")


# ============================================================
# 2. INSTRUMENTEN-DATENBANK
# ============================================================

FUTURES = {

    "NQ (Nasdaq 100)": {
        "tick_size": 0.25,
        "tick_value": 5.00,
        "currency": "USD",
        "margin_native": 18000,
        "default_comm_roundturn": 4.00,
        "micro_key": "MNQ (Micro Nasdaq)"
    },

    "MNQ (Micro Nasdaq)": {
        "tick_size": 0.25,
        "tick_value": 0.50,
        "currency": "USD",
        "margin_native": 1800,
        "default_comm_roundturn": 1.50,
        "micro_key": None
    },

    "ES (S&P 500)": {
        "tick_size": 0.25,
        "tick_value": 12.50,
        "currency": "USD",
        "margin_native": 12000,
        "default_comm_roundturn": 4.00,
        "micro_key": "MES (Micro S&P)"
    },

    "MES (Micro S&P)": {
        "tick_size": 0.25,
        "tick_value": 1.25,
        "currency": "USD",
        "margin_native": 1200,
        "default_comm_roundturn": 1.50,
        "micro_key": None
    },

    "GC (Gold)": {
        "tick_size": 0.10,
        "tick_value": 10.00,
        "currency": "USD",
        "margin_native": 10000,
        "default_comm_roundturn": 4.50,
        "micro_key": "MGC (Micro Gold)"
    },

    "MGC (Micro Gold)": {
        "tick_size": 0.10,
        "tick_value": 1.00,
        "currency": "USD",
        "margin_native": 1000,
        "default_comm_roundturn": 1.50,
        "micro_key": None
    },

    "CL (Crude Oil)": {
        "tick_size": 0.01,
        "tick_value": 10.00,
        "currency": "USD",
        "margin_native": 7000,
        "default_comm_roundturn": 4.50,
        "micro_key": "MCL (Micro Oil)"
    },

    "MCL (Micro Oil)": {
        "tick_size": 0.01,
        "tick_value": 1.00,
        "currency": "USD",
        "margin_native": 700,
        "default_comm_roundturn": 1.50,
        "micro_key": None
    },

    "FDAX (DAX Future)": {
        "tick_size": 0.50,
        "tick_value": 12.50,
        "currency": "EUR",
        "margin_native": 30000,
        "default_comm_roundturn": 3.00,
        "micro_key": "FDXM (Mini DAX)"
    },

    "FDXM (Mini DAX)": {
        "tick_size": 1.00,
        "tick_value": 5.00,
        "currency": "EUR",
        "margin_native": 6000,
        "default_comm_roundturn": 1.50,
        "micro_key": None
    },
}


CFDS = {

    "NASDAQ 100 CFD": {
        "contract_size": 1.0,
        "point_value": 1.0,
        "currency": "USD",
        "default_spread": 1.5,
        "reference_max_leverage": 20,
        "default_overnight_pct": 0.015,
        "min_units": 0.01,
        "unit_step": 0.01,
        "margin_model": "Leverage-Based"
    },

    "S&P 500 CFD": {
        "contract_size": 1.0,
        "point_value": 1.0,
        "currency": "USD",
        "default_spread": 0.5,
        "reference_max_leverage": 20,
        "default_overnight_pct": 0.015,
        "min_units": 0.01,
        "unit_step": 0.01,
        "margin_model": "Leverage-Based"
    },

    "GER40 CFD": {
        "contract_size": 1.0,
        "point_value": 1.0,
        "currency": "EUR",
        "default_spread": 1.0,
        "reference_max_leverage": 20,
        "default_overnight_pct": 0.015,
        "min_units": 0.01,
        "unit_step": 0.01,
        "margin_model": "Leverage-Based"
    },

    "Gold CFD": {
        "contract_size": 1.0,
        "point_value": 1.0,
        "currency": "USD",
        "default_spread": 0.30,
        "reference_max_leverage": 20,
        "default_overnight_pct": 0.020,
        "min_units": 0.01,
        "unit_step": 0.01,
        "margin_model": "Leverage-Based"
    },

    "Oil CFD": {
        "contract_size": 1.0,
        "point_value": 1.0,
        "currency": "USD",
        "default_spread": 0.04,
        "reference_max_leverage": 10,
        "default_overnight_pct": 0.025,
        "min_units": 0.01,
        "unit_step": 0.01,
        "margin_model": "Leverage-Based"
    },
}


# ============================================================
# 3. HILFSFUNKTIONEN
# ============================================================

def fx_rate_for_currency(currency, eurusd):
    """
    EUR/USD:
    USD -> EUR = / EURUSD
    EUR -> EUR = 1
    """
    if currency == "USD":
        return eurusd
    return 1.0


def safe_floor_to_step(value, step):
    """
    Robustes Abrunden auf eine definierte Schrittweite.
    """
    if value <= 0 or step <= 0:
        return 0.0

    return round(
        math.floor(
            (value + 1e-12) / step
        ) * step,
        10
    )


def direction_is_valid(direction, entry, stop, target):
    """
    Long:
        Stop < Entry < Target

    Short:
        Target < Entry < Stop
    """

    if direction == "Long":
        return stop < entry < target

    return target < entry < stop


def calculate_rrr(reward, risk):
    if risk <= 0:
        return 0.0

    return reward / risk


def calculate_weighted_direction_score(
    direction,
    d240,
    d60,
    d15
):
    """
    Richtungsbewertung:

    4H = 2.0
    1H = 1.5
    15M = 1.0

    Trade-Richtung:
        +1 = aligned
         0 = neutral
        -1 = opposite

    Ergebnis wird auf 0..1 normalisiert.
    """

    weights = {
        "4H": 2.0,
        "1H": 1.5,
        "15M": 1.0
    }

    directions = {
        "4H": d240,
        "1H": d60,
        "15M": d15
    }

    raw_score = 0.0
    total_weight = sum(weights.values())

    for timeframe, value in directions.items():

        weight = weights[timeframe]

        if value == "Neutral":
            contribution = 0.0

        elif value == direction:
            contribution = 1.0

        else:
            contribution = -1.0

        raw_score += weight * contribution

    normalized = (
        raw_score + total_weight
    ) / (
        2 * total_weight
    )

    return max(
        0.0,
        min(1.0, normalized)
    )


def calculate_direction_counts(
    d240,
    d60,
    d15
):
    directions = [d240, d60, d15]

    long_count = directions.count("Long")
    short_count = directions.count("Short")
    neutral_count = directions.count("Neutral")

    if long_count > short_count:
        dominant = "Long"

    elif short_count > long_count:
        dominant = "Short"

    else:
        dominant = "Neutral"

    return (
        long_count,
        short_count,
        neutral_count,
        dominant
    )


def calculate_sentiment_score(
    trade_direction,
    values
):
    """
    Richtungsabhängiges Sentiment:

    Für Long:
        Supportive       = 0.75
        Neutral          = 0.25
        Not supportive   = 0.00

    Für Short:
        Not supportive   = 0.75
        Neutral          = 0.25
        Supportive       = 0.00

    Maximal 3.00 Punkte.
    """

    points = 0.0

    for value in values:

        if value == "Neutral":

            points += 0.25

        elif value == "Supportive":

            if trade_direction == "Long":
                points += 0.75

        elif value == "Not supportive":

            if trade_direction == "Short":
                points += 0.75

    return points


def calculate_structure_points(
    t240,
    t60,
    t15
):
    """
    Trend       = 1.00
    Korrektur   = 0.50
    Seitwärts   = 0.00

    Maximal 3.00 Punkte.
    """

    mapping = {
        "Trend": 1.0,
        "Korrektur": 0.5,
        "Seitwärts": 0.0
    }

    return sum(
        mapping[t]
        for t in [t240, t60, t15]
    )


def calculate_atr_status(
    risk_points,
    atr_val,
    stop_min_atr,
    stop_max_atr
):
    """
    Rückgabe:
        ratio
        status
        valid
    """

    if atr_val <= 0:
        return None, "Deaktiviert", True

    ratio = risk_points / atr_val

    if stop_min_atr is None or stop_max_atr is None:
        return ratio, "Nicht bewertet", True

    if ratio < stop_min_atr:
        return ratio, "Zu eng", False

    if ratio > stop_max_atr:
        return ratio, "Zu weit", False

    return ratio, "OK", True


def calculate_futures_position(
    market_key,
    budget_eur,
    free_margin_eur,
    risk_points,
    reward_points,
    eurusd,
    commission_native
):
    """
    Futures-Berechnung.

    WICHTIG:
    Die Kommission wird beim Sizing berücksichtigt,
    aber später NICHT erneut in act_stop_risk eingerechnet.

    Dadurch wird die Doppelzählung aus v2.7 vermieden.
    """

    spec = FUTURES[market_key]

    fx_conv = fx_rate_for_currency(
        spec["currency"],
        eurusd
    )

    risk_ticks = (
        risk_points
        / spec["tick_size"]
    )

    reward_ticks = (
        reward_points
        / spec["tick_size"]
    )

    stop_risk_per_contract_eur = (
        risk_ticks
        * spec["tick_value"]
        / fx_conv
    )

    commission_per_contract_eur = (
        commission_native
        / fx_conv
    )

    total_risk_per_contract_eur = (
        stop_risk_per_contract_eur
        + commission_per_contract_eur
    )

    max_risk_units = (
        math.floor(
            budget_eur
            / total_risk_per_contract_eur
        )
        if total_risk_per_contract_eur > 0
        else 0
    )

    margin_per_contract_eur = (
        spec["margin_native"]
        / fx_conv
    )

    max_margin_units = (
        math.floor(
            free_margin_eur
            / margin_per_contract_eur
        )
        if margin_per_contract_eur > 0
        else 0
    )

    units = min(
        max_risk_units,
        max_margin_units
    )

    if (
        max_risk_units == 0
        and max_margin_units == 0
    ):
        limit_reason = (
            "Risikobudget & freie Margin"
        )

    elif max_risk_units < max_margin_units:
        limit_reason = "Risikobudget"

    elif max_margin_units < max_risk_units:
        limit_reason = "Freie Planungs-Margin"

    else:
        limit_reason = (
            "Risikobudget & Margin identisch"
        )

    stop_risk = (
        units
        * stop_risk_per_contract_eur
    )

    commission = (
        units
        * commission_per_contract_eur
    )

    reward = (
        units
        * reward_ticks
        * spec["tick_value"]
        / fx_conv
    )

    margin_required = (
        units
        * margin_per_contract_eur
    )

    # Futures-Nominalexposure
    # Näherung über Entry * Kontrakt-Multiplikator.
    if market_key in [
        "NQ (Nasdaq 100)",
        "MNQ (Micro Nasdaq)"
    ]:
        multiplier = (
            spec["tick_value"]
            / spec["tick_size"]
        )

    elif market_key in [
        "ES (S&P 500)",
        "MES (Micro S&P)"
    ]:
        multiplier = (
            spec["tick_value"]
            / spec["tick_size"]
        )

    elif market_key in [
        "GC (Gold)",
        "MGC (Micro Gold)"
    ]:
        multiplier = (
            spec["tick_value"]
            / spec["tick_size"]
        )

    elif market_key in [
        "CL (Crude Oil)",
        "MCL (Micro Oil)"
    ]:
        multiplier = (
            spec["tick_value"]
            / spec["tick_size"]
        )

    else:
        multiplier = (
            spec["tick_value"]
            / spec["tick_size"]
        )

    position_value_eur = (
        units
        * multiplier
        / fx_conv
    )

    return {
        "units": units,
        "max_risk_units": max_risk_units,
        "max_margin_units": max_margin_units,
        "limit_reason": limit_reason,
        "stop_risk": stop_risk,
        "reward": reward,
        "commission": commission,
        "margin_required": margin_required,
        "position_value": position_value_eur,
        "stop_risk_per_unit": stop_risk_per_contract_eur,
        "commission_per_unit": commission_per_contract_eur
    }


def calculate_cfd_position(
    market_key,
    budget_eur,
    free_margin_eur,
    risk_points,
    reward_points,
    eurusd,
    leverage,
    spread_points,
    overnight_enabled,
    overnight_nights,
    extra_fee_units,
    overnight_pct
):
    """
    CFD-Berechnung.

    Spread und Overnight werden als
    Planungsannahmen behandelt.
    """

    spec = CFDS[market_key]

    fx_conv = fx_rate_for_currency(
        spec["currency"],
        eurusd
    )

    value_per_point_eur = (
        spec["point_value"]
        * spec["contract_size"]
        / fx_conv
    )

    stop_cost_per_unit = (
        risk_points
        * value_per_point_eur
    )

    spread_cost_per_unit = (
        spread_points
        * value_per_point_eur
    )

    overnight_cost_per_unit = 0.0

    if overnight_enabled:

        total_fee_days = (
            overnight_nights
            + extra_fee_units
        )

        nominal_per_unit_eur = (
            1.0
            * value_per_point_eur
            * entry_price
        )

        overnight_cost_per_unit = (
            nominal_per_unit_eur
            * (overnight_pct / 100.0)
            * total_fee_days
        )

    total_costs_per_unit = (
        spread_cost_per_unit
        + overnight_cost_per_unit
    )

    total_risk_per_unit = (
        stop_cost_per_unit
        + total_costs_per_unit
    )

    nominal_per_unit_eur = (
        entry_price
        * value_per_point_eur
    )

    margin_per_unit_eur = (
        nominal_per_unit_eur / leverage
        if leverage > 0
        else 0.0
    )

    raw_risk_units = (
        budget_eur / total_risk_per_unit
        if total_risk_per_unit > 0
        else 0.0
    )

    raw_margin_units = (
        free_margin_eur / margin_per_unit_eur
        if margin_per_unit_eur > 0
        else 0.0
    )

    max_risk_units = safe_floor_to_step(
        raw_risk_units,
        spec["unit_step"]
    )

    max_margin_units = safe_floor_to_step(
        raw_margin_units,
        spec["unit_step"]
    )

    units = min(
        max_risk_units,
        max_margin_units
    )

    if units < spec["min_units"]:
        units = 0.0

    if (
        max_risk_units < spec["min_units"]
        and max_margin_units < spec["min_units"]
    ):
        limit_reason = (
            "Risikobudget & freie Margin"
        )

    elif max_risk_units < max_margin_units:
        limit_reason = "Risikobudget"

    elif max_margin_units < max_risk_units:
        limit_reason = "Freie Planungs-Margin"

    else:
        limit_reason = (
            "Risikobudget & Margin identisch"
        )

    stop_risk = (
        units * stop_cost_per_unit
    )

    spread_cost = (
        units * spread_cost_per_unit
    )

    overnight_cost = (
        units * overnight_cost_per_unit
    )

    reward = (
        units
        * reward_points
        * value_per_point_eur
    )

    margin_required = (
        units
        * margin_per_unit_eur
    )

    position_value = (
        units
        * nominal_per_unit_eur
    )

    return {
        "units": units,
        "max_risk_units": max_risk_units,
        "max_margin_units": max_margin_units,
        "limit_reason": limit_reason,
        "stop_risk": stop_risk,
        "reward": reward,
        "spread": spread_cost,
        "overnight": overnight_cost,
        "commission": 0.0,
        "margin_required": margin_required,
        "position_value": position_value,
        "stop_risk_per_unit": stop_cost_per_unit,
        "total_costs_per_unit": total_costs_per_unit
    }


def get_micro_commission(
    macro_spec,
    micro_spec,
    macro_commission
):
    """
    Abgeleitete Planungs-Kommission.

    NICHT als tatsächliche Brokerkommission verstehen.
    """

    if macro_spec["tick_value"] <= 0:
        return micro_spec["default_comm_roundturn"]

    ratio = (
        micro_spec["tick_value"]
        / macro_spec["tick_value"]
    )

    proportional = (
        macro_commission * ratio
    )

    # Konservativ: mindestens die bekannte
    # Standard-Micro-Kommission verwenden.
    return max(
        proportional,
        micro_spec["default_comm_roundturn"]
    )


def calculate_risk_sequence(
    account_balance,
    risk_pct,
    consecutive_losses
):
    """
    Einfacher Verlustserien-Monitor.

    Keine echte statistische Risk-of-Ruin-Berechnung.
    Zeigt lediglich die Wirkung einer Serie gleich
    großer Verluste.
    """

    if account_balance <= 0:
        return 0.0, 0.0

    equity = account_balance

    loss_per_trade = (
        account_balance
        * risk_pct
        / 100.0
    )

    for _ in range(
        max(0, int(consecutive_losses))
    ):

        equity -= loss_per_trade

    total_loss = (
        account_balance - equity
    )

    loss_pct = (
        total_loss
        / account_balance
        * 100.0
    )

    return equity, loss_pct


# ============================================================
# 4. SIDEBAR – KONTO & RISIKOPARAMETER
# ============================================================

with st.sidebar:

    st.header("⚙️ Konto & Risiko")

    account_balance = st.number_input(
        "Kontostand / Equity (€)",
        min_value=0.0,
        value=100000.0,
        step=1000.0
    )

    used_margin_eur = st.number_input(
        "Bereits gebundene Margin (€)",
        min_value=0.0,
        value=0.0,
        step=500.0,
        help=(
            "Planungs-Margin bestehender "
            "offener Positionen."
        )
    )

    free_margin_eur = max(
        0.0,
        account_balance - used_margin_eur
    )

    st.caption(
        f"Freie Planungs-Margin: "
        f"**{free_margin_eur:,.2f} €**"
    )

    base_risk_pct = st.select_slider(
        "Basis-Risikoklasse (%)",
        options=[
            0.25,
            0.50,
            0.75,
            1.00,
            1.50,
            2.00
        ],
        value=1.00
    )

    eurusd = st.number_input(
        "EUR/USD Planungskurs",
        min_value=0.01,
        value=1.17,
        step=0.01
    )

    st.markdown("---")

    st.subheader("🛡️ Tagesrisiko")

    daily_loss_limit_pct = st.select_slider(
        "Tagesverlust-Limit (%)",
        options=[
            0.5,
            1.0,
            1.5,
            2.0,
            3.0
        ],
        value=2.0
    )

    daily_loss_realized_eur = st.number_input(
        "Heute bereits realisiert (€)",
        min_value=0.0,
        value=0.0,
        step=50.0
    )

    daily_open_risk_eur = st.number_input(
        "Offenes Stop-Risiko anderer Positionen (€)",
        min_value=0.0,
        value=0.0,
        step=50.0
    )

    daily_unrealized_pnl_eur = st.number_input(
        "Unrealisiertes P&L anderer Positionen (€)",
        value=0.0,
        step=50.0,
        help=(
            "Optionaler Planungswert. "
            "Positive Werte = Gewinn, negative Werte = Verlust."
        )
    )

    st.markdown("---")

    st.subheader("📉 Verlustserien-Monitor")

    consecutive_losses = st.number_input(
        "Simulierte Verlustserie",
        min_value=0,
        max_value=20,
        value=5,
        step=1
    )


# ============================================================
# 5. HAUPT-INPUTS
# ============================================================

col_market, col_trader, col_setup = st.columns(
    [1.1, 1.0, 1.2]
)


# ============================================================
# 5A. MARKT
# ============================================================

with col_market:

    st.subheader("1. Markt-Umfeld")

    st.markdown(
        "**Multi-Timeframe Marktstruktur & Richtung**"
    )

    # --------------------------------------------------------
    # 4H
    # --------------------------------------------------------

    st.markdown("**4H – übergeordnete Struktur**")

    c_4h_1, c_4h_2 = st.columns(2)

    t240 = c_4h_1.selectbox(
        "4H Struktur",
        [
            "Trend",
            "Korrektur",
            "Seitwärts"
        ],
        index=0,
        key="structure_4h"
    )

    d240 = c_4h_2.selectbox(
        "4H Richtung",
        [
            "Long",
            "Short",
            "Neutral"
        ],
        index=0,
        key="direction_4h"
    )

    # --------------------------------------------------------
    # 1H
    # --------------------------------------------------------

    st.markdown("**1H – mittlere Struktur**")

    c_1h_1, c_1h_2 = st.columns(2)

    t60 = c_1h_1.selectbox(
        "1H Struktur",
        [
            "Trend",
            "Korrektur",
            "Seitwärts"
        ],
        index=0,
        key="structure_1h"
    )

    d60 = c_1h_2.selectbox(
        "1H Richtung",
        [
            "Long",
            "Short",
            "Neutral"
        ],
        index=0,
        key="direction_1h"
    )

    # --------------------------------------------------------
    # 15M
    # --------------------------------------------------------

    st.markdown("**15M – Entry-Struktur**")

    c_15m_1, c_15m_2 = st.columns(2)

    t15 = c_15m_1.selectbox(
        "15M Struktur",
        [
            "Trend",
            "Korrektur",
            "Seitwärts"
        ],
        index=0,
        key="structure_15m"
    )

    d15 = c_15m_2.selectbox(
        "15M Richtung",
        [
            "Long",
            "Short",
            "Neutral"
        ],
        index=0,
        key="direction_15m"
    )

    # --------------------------------------------------------
    # MACRO & SENTIMENT
    # --------------------------------------------------------

    st.markdown("**Macro & Sentiment**")

    aaii = st.selectbox(
        "AAII Sentiment",
        [
            "Supportive",
            "Neutral",
            "Not supportive"
        ],
        index=0
    )

    fg_index = st.selectbox(
        "Fear & Greed Index",
        [
            "Supportive",
            "Neutral",
            "Not supportive"
        ],
        index=1
    )

    central_bank = st.selectbox(
        "Notenbank-Politik",
        [
            "Supportive",
            "Neutral",
            "Not supportive"
        ],
        index=1
    )

    seasonals = st.selectbox(
        "Saisonalität",
        [
            "Supportive",
            "Neutral",
            "Not supportive"
        ],
        index=0
    )


# ============================================================
# 5B. TRADER CONDITION
# ============================================================

with col_trader:

    st.subheader("2. Trader Condition")

    st.markdown("**Verfassungs-Check**")

    trader_stress = st.select_slider(
        "Stress / Müdigkeit / Zeitdruck",
        options=[
            "Niedrig",
            "Mittel",
            "Hoch"
        ],
        value="Niedrig"
    )

    location = st.selectbox(
        "Standort",
        [
            "Home Office",
            "Mobil / Unterwegs",
            "Fremdes Büro"
        ]
    )

    st.markdown("**News & Haltedauer**")

    news_soon = st.radio(
        "High-Impact News < 30 Min?",
        [
            "Nein",
            "Ja"
        ],
        horizontal=True
    )

    news_mode = st.radio(
        "News-Regel",
        [
            "Hard Block",
            "Risiko reduzieren",
            "Nur nach News"
        ],
        help=(
            "Hard Block = keine Ausführung. "
            "Risiko reduzieren = Warnung und reduziertes Risiko. "
            "Nur nach News = Setup bleibt bis nach dem Event blockiert."
        )
    )

    holding_period = st.radio(
        "Haltedauer",
        [
            "Intraday",
            "Overnight"
        ],
        horizontal=True
    )

    overnight_nights = 0
    extra_fee_units = 0

    if holding_period == "Overnight":

        c_n1, c_n2 = st.columns(2)

        overnight_nights = c_n1.number_input(
            "Haltedauer (Nächte)",
            min_value=1,
            max_value=30,
            value=1
        )

        extra_fee_units = c_n2.number_input(
            "Zusätzl. Gebühreneinheiten",
            min_value=0,
            max_value=10,
            value=0,
            help=(
                "Z.B. zusätzliche Wochenend-/Triple-Fee-Einheiten "
                "laut tatsächlicher Brokerregel."
            )
        )


# ============================================================
# 5C. PRODUKT & SETUP
# ============================================================

with col_setup:

    st.subheader("3. Produkt & Kostenplanung")

    product_type = st.radio(
        "Produktart",
        [
            "Futures",
            "CFD"
        ],
        horizontal=True
    )

    if product_type == "Futures":

        market_key = st.selectbox(
            "Futures-Instrument",
            list(FUTURES.keys())
        )

        spec = FUTURES[market_key]

        margin_native = spec["margin_native"]

        margin_per_contract_eur = (
            margin_native
            / fx_rate_for_currency(
                spec["currency"],
                eurusd
            )
        )

        leverage = None

        fut_comm_rt_native = st.number_input(
            f"Kommission R/T ({spec['currency']}/Kontrakt)",
            min_value=0.0,
            value=float(
                spec["default_comm_roundturn"]
            ),
            step=0.5,
            help=(
                "Planungsannahme inklusive "
                "Broker-/Börsengebühren."
            )
        )

        spread_points = 0.0
        daily_overnight_pct = 0.0

    else:

        market_key = st.selectbox(
            "CFD-Instrument",
            list(CFDS.keys())
        )

        spec = CFDS[market_key]

        reference_lev = spec[
            "reference_max_leverage"
        ]

        leverage_options = [
            l
            for l in [
                1,
                2,
                5,
                10,
                20,
                30
            ]
            if l <= reference_lev
        ]

        leverage = st.select_slider(
            "Planungs-Hebel",
            options=leverage_options,
            value=(
                reference_lev
                if reference_lev in leverage_options
                else leverage_options[-1]
            ),
            help=(
                "Planungshebel für die Marginberechnung. "
                "Der tatsächliche Broker-Marginbedarf kann abweichen."
            )
        )

        st.markdown(
            "**CFD-Broker-Planungskosten**"
        )

        spread_points = st.number_input(
            "Gesamt-Spread Bid/Ask (Punkte)",
            min_value=0.0,
            value=float(
                spec["default_spread"]
            ),
            step=0.1,
            help=(
                "Planungsannahme für die Roundtrip-Kosten."
            )
        )

        daily_overnight_pct = st.number_input(
            "Angenommene Overnight-Gebühr "
            "(% Nominalwert/Tag)",
            min_value=0.0,
            value=float(
                spec["default_overnight_pct"]
            ),
            step=0.005,
            format="%.3f",
            help=(
                "Planungsannahme. Keine automatische "
                "Abbildung der tatsächlichen Brokergebühr."
            )
        )

        fut_comm_rt_native = 0.0

    direction = st.radio(
        "Richtung",
        [
            "Long",
            "Short"
        ],
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
        help="Bei 0 wird der ATR-Filter deaktiviert."
    )


# ============================================================
# 6. PRE-CALCULATION
# ============================================================

is_valid_direction = direction_is_valid(
    direction,
    entry_price,
    stop_price,
    target_price
)

risk_points = abs(
    entry_price - stop_price
)

reward_points = abs(
    target_price - entry_price
)

gross_rrr = calculate_rrr(
    reward_points,
    risk_points
)


# ============================================================
# 7. MTF ENGINE
# ============================================================

(
    long_count,
    short_count,
    neutral_count,
    dominant_direction
) = calculate_direction_counts(
    d240,
    d60,
    d15
)

structure_points = calculate_structure_points(
    t240,
    t60,
    t15
)

direction_alignment_score = (
    calculate_weighted_direction_score(
        direction,
        d240,
        d60,
        d15
    )
)

direction_points = direction_alignment_score


# ============================================================
# 8. SENTIMENT ENGINE
# ============================================================

sentiment_points = calculate_sentiment_score(
    direction,
    [
        aaii,
        fg_index,
        central_bank,
        seasonals
    ]
)


# ============================================================
# 9. TRADER PENALTIES
# ============================================================

penalties = 0.0

if trader_stress == "Mittel":
    penalties += 0.5

elif trader_stress == "Hoch":
    penalties += 1.5

if location != "Home Office":
    penalties += 0.5


# ============================================================
# 10. GESAMTSCORE
# ============================================================

mtf_points = (
    structure_points
    + direction_points
)

total_score = max(
    0.0,
    mtf_points
    + sentiment_points
    - penalties
)


# ============================================================
# 11. RICHTUNGS-KONFLIKTE
# ============================================================

mtf_direction_conflict = (
    d240 != "Neutral"
    and d60 != "Neutral"
    and d240 != d60
)

aligned_count = sum(
    1
    for d in [d240, d60, d15]
    if d == direction
)

opposite_count = sum(
    1
    for d in [d240, d60, d15]
    if (
        d != "Neutral"
        and d != direction
    )
)

entry_direction_conflict = (
    opposite_count >= 2
)


full_mtf_alignment = (
    d240 == direction
    and d60 == direction
    and d15 == direction
)

partial_mtf_alignment = (
    aligned_count == 2
    and opposite_count <= 1
)


# ============================================================
# 12. GEAR KLASSIFIZIERUNG
# ============================================================

if total_score >= 5.0:

    gear = 5
    min_rrr_req = 2.0
    risk_mult = 1.00
    stop_min_atr = 1.0
    stop_max_atr = 2.0
    scale_out = (
        "Nein – Gewinner voll ausreizen"
    )

elif total_score >= 3.8:

    gear = 4
    min_rrr_req = 1.8
    risk_mult = 0.90
    stop_min_atr = 1.5
    stop_max_atr = 2.5
    scale_out = (
        "Optional ab 2.0R"
    )

elif total_score >= 2.5:

    gear = 3
    min_rrr_req = 1.5
    risk_mult = 0.75
    stop_min_atr = 1.5
    stop_max_atr = 4.0
    scale_out = (
        "Ja – Teilgewinn ab 1.5R"
    )

elif total_score >= 1.2:

    gear = 2
    min_rrr_req = 1.2
    risk_mult = 0.50
    stop_min_atr = 2.0
    stop_max_atr = 4.0
    scale_out = (
        "Ja – frühzeitige Skalierung"
    )

else:

    gear = 1
    min_rrr_req = 0.0

    # Nicht mehr 0.0:
    # Gear 1 bleibt Hard Stop, aber das System
    # zeigt trotzdem das theoretische Risikobudget.
    risk_mult = 0.25

    stop_min_atr = None
    stop_max_atr = None

    scale_out = "N/A"


# ============================================================
# 13. ATR ENGINE
# ============================================================

(
    stop_atr_ratio,
    atr_status,
    atr_ok
) = calculate_atr_status(
    risk_points,
    atr_val,
    stop_min_atr,
    stop_max_atr
)


# ============================================================
# 14. RISIKOBUDGET
# ============================================================

effective_risk_pct = (
    base_risk_pct
    * risk_mult
)

# News-Modus "Risiko reduzieren"
# reduziert ausschließlich das neue Trade-Budget.
if news_soon == "Ja" and news_mode == "Risiko reduzieren":
    effective_risk_pct *= 0.50

risk_budget_eur = (
    account_balance
    * effective_risk_pct
    / 100.0
)

daily_loss_limit_eur = (
    account_balance
    * daily_loss_limit_pct
    / 100.0
)

# Unrealisiertes P&L:
# Nur Verluste reduzieren die verfügbare Tageskapazität.
unrealized_loss_for_daily_limit = max(
    0.0,
    -daily_unrealized_pnl_eur
)

total_daily_risk_used_eur = (
    daily_loss_realized_eur
    + daily_open_risk_eur
    + unrealized_loss_for_daily_limit
)

remaining_daily_loss_eur = max(
    0.0,
    daily_loss_limit_eur
    - total_daily_risk_used_eur
)

risk_budget_eur = min(
    risk_budget_eur,
    remaining_daily_loss_eur
)


# ============================================================
# 15. POSITION SIZING
# ============================================================

is_overnight = (
    holding_period == "Overnight"
)

micro_active = False
micro_key_found = None
micro_contracts = 0
macro_risk_needed_for_1_contract = 0.0
micro_comm_used_native = 0.0
original_market_key = market_key


if product_type == "Futures":

    sizing_res = calculate_futures_position(
        market_key,
        risk_budget_eur,
        free_margin_eur,
        risk_points,
        reward_points,
        eurusd,
        fut_comm_rt_native
    )

else:

    sizing_res = calculate_cfd_position(
        market_key,
        risk_budget_eur,
        free_margin_eur,
        risk_points,
        reward_points,
        eurusd,
        leverage,
        spread_points,
        is_overnight,
        overnight_nights,
        extra_fee_units,
        daily_overnight_pct
    )


# ============================================================
# 16. MICRO-FALLBACK
# ============================================================

if (
    product_type == "Futures"
    and sizing_res["units"] == 0
):

    macro_spec = FUTURES[market_key]

    micro_key_found = (
        macro_spec.get("micro_key")
    )

    if micro_key_found:

        micro_spec = FUTURES[
            micro_key_found
        ]

        macro_fx = fx_rate_for_currency(
            macro_spec["currency"],
            eurusd
        )

        macro_stop = (
            (
                risk_points
                / macro_spec["tick_size"]
            )
            * macro_spec["tick_value"]
            / macro_fx
        )

        macro_comm_eur = (
            fut_comm_rt_native
            / macro_fx
        )

        macro_risk_needed_for_1_contract = (
            macro_stop
            + macro_comm_eur
        )

        micro_comm_used_native = (
            get_micro_commission(
                macro_spec,
                micro_spec,
                fut_comm_rt_native
            )
        )

        micro_res = calculate_futures_position(
            micro_key_found,
            risk_budget_eur,
            free_margin_eur,
            risk_points,
            reward_points,
            eurusd,
            micro_comm_used_native
        )

        micro_cnt = micro_res["units"]

        if micro_cnt > 0:

            micro_active = True
            micro_contracts = micro_cnt
            market_key = micro_key_found
            sizing_res = micro_res


# ============================================================
# 17. FINALE KOSTEN / RISIKO
# ============================================================

final_contracts = sizing_res["units"]

actual_stop_risk_eur = (
    sizing_res["stop_risk"]
)

actual_reward_eur = (
    sizing_res["reward"]
)

required_margin_eur = (
    sizing_res["margin_required"]
)

spread_cost_eur = (
    sizing_res.get("spread", 0.0)
)

overnight_cost_eur = (
    sizing_res.get("overnight", 0.0)
)

comm_cost_eur = (
    sizing_res.get("commission", 0.0)
)

position_value_eur = (
    sizing_res["position_value"]
)

sizing_limit_reason = (
    sizing_res["limit_reason"]
)

total_costs_eur = (
    spread_cost_eur
    + overnight_cost_eur
    + comm_cost_eur
)

# WICHTIG:
# Stop-Risiko enthält ausschließlich den
# Preisverlust bis zum Stop.
stop_loss_risk_eur = (
    actual_stop_risk_eur
)

# Kosten werden exakt EINMAL addiert.
net_risk_eur = (
    stop_loss_risk_eur
    + total_costs_eur
)

net_reward_eur = max(
    0.0,
    actual_reward_eur
    - total_costs_eur
)

net_rrr = calculate_rrr(
    net_reward_eur,
    net_risk_eur
)

risk_budget_exceeded = (
    net_risk_eur
    > risk_budget_eur + 0.01
)


# ============================================================
# 18. DECISION GATE
# ============================================================

hard_stops = []
soft_blocks = []
warnings = []


# ------------------------------------------------------------
# HARD STOP – PREISSTRUKTUR
# ------------------------------------------------------------

if not is_valid_direction:

    hard_stops.append(
        (
            "🔴 Ungültige Preisstruktur",
            "Stop und Target liegen nicht korrekt "
            "relativ zum Entry."
        )
    )


# ------------------------------------------------------------
# HARD STOP – 2/3 MTF GEGEN TRADE
# ------------------------------------------------------------

if entry_direction_conflict:

    hard_stops.append(
        (
            "🔴 MTF-Richtung widerspricht Trade",
            (
                f"{opposite_count}/3 nicht-neutrale "
                f"Zeitebenen stehen gegen {direction}."
            )
        )
    )


# ------------------------------------------------------------
# NEWS
# ------------------------------------------------------------

if news_soon == "Ja":

    if news_mode == "Hard Block":

        hard_stops.append(
            (
                "🔴 High-Impact News",
                "Macro-Event <30 Min – Ausführung blockiert."
            )
        )

    elif news_mode == "Nur nach News":

        hard_stops.append(
            (
                "🔴 News-Wartephase",
                "Trade erst nach dem High-Impact-Event zulässig."
            )
        )

    else:

        warnings.append(
            (
                "🟡 News – Risiko reduziert",
                (
                    "Risikobudget wurde für das Event "
                    "automatisch um 50 % reduziert."
                )
            )
        )


# ------------------------------------------------------------
# HARD STOP – TRADER CONDITION
# ------------------------------------------------------------

if trader_stress == "Hoch":

    hard_stops.append(
        (
            "🔴 Trader-Verfassung",
            "Stress-Level verlangt Trading-Pause."
        )
    )


# ------------------------------------------------------------
# HARD STOP – GEAR 1
# ------------------------------------------------------------

if gear == 1:

    hard_stops.append(
        (
            "🔴 Gear 1",
            "Gesamtscore liegt unter dem handelbaren Mindestniveau."
        )
    )


# ------------------------------------------------------------
# HARD STOP – TAGESVERLUST
# ------------------------------------------------------------

if remaining_daily_loss_eur <= 0:

    hard_stops.append(
        (
            "🔴 Tagesverlust-Limit",
            "Das verfügbare Tagesrisikobudget ist vollständig verbraucht."
        )
    )


# ------------------------------------------------------------
# SOFT BLOCK – ATR
# ------------------------------------------------------------

if not atr_ok and atr_val > 0:

    if atr_status == "Zu eng":

        soft_blocks.append(
            (
                "🟠 ATR-Stop zu eng",
                (
                    f"{stop_atr_ratio:.2f}x ATR liegt unter "
                    f"dem Mindestwert von {stop_min_atr:.2f}x."
                )
            )
        )

    elif atr_status == "Zu weit":

        soft_blocks.append(
            (
                "🟠 ATR-Stop zu weit",
                (
                    f"{stop_atr_ratio:.2f}x ATR liegt über "
                    f"dem Maximum von {stop_max_atr:.2f}x."
                )
            )
        )


# ------------------------------------------------------------
# SOFT BLOCK – SIZING
# ------------------------------------------------------------

if final_contracts <= 0:

    soft_blocks.append(
        (
            "🟠 Keine handelbare Positionsgröße",
            (
                f"Limitierender Faktor: "
                f"{sizing_limit_reason}."
            )
        )
    )


# ------------------------------------------------------------
# SOFT BLOCK – CRV
# ------------------------------------------------------------

if (
    final_contracts > 0
    and net_rrr < min_rrr_req
):

    soft_blocks.append(
        (
            "🟠 Netto-CRV zu gering",
            (
                f"Netto-CRV {net_rrr:.2f} liegt unter "
                f"dem geforderten Minimum von {min_rrr_req:.2f}."
            )
        )
    )


# ------------------------------------------------------------
# SOFT BLOCK – RISIKOBUDGET
# ------------------------------------------------------------

if risk_budget_exceeded:

    soft_blocks.append(
        (
            "🟠 Risikobudget überschritten",
            (
                f"Netto-Risiko {net_risk_eur:,.2f} € > "
                f"Budget {risk_budget_eur:,.2f} €."
            )
        )
    )


# ------------------------------------------------------------
# WARNINGS
# ------------------------------------------------------------

if mtf_direction_conflict:

    warnings.append(
        (
            "🟡 4H/1H-Richtungskonflikt",
            (
                "4H und 1H zeigen unterschiedliche Richtungen. "
                "Dies kann eine Korrekturphase darstellen."
            )
        )
    )


if partial_mtf_alignment:

    warnings.append(
        (
            "🟡 MTF nur teilweise ausgerichtet",
            (
                f"{aligned_count}/3 Zeitebenen stimmen mit "
                f"dem geplanten Trade überein."
            )
        )
    )


if location != "Home Office":

    warnings.append(
        (
            "🟡 Standort",
            "Der Trade wird nicht aus dem Home Office geplant."
        )
    )


if trader_stress == "Mittel":

    warnings.append(
        (
            "🟡 Trader-Verfassung",
            "Mittleres Stress-/Müdigkeitsniveau."
        )
    )


if atr_val == 0:

    warnings.append(
        (
            "🟡 ATR deaktiviert",
            "Der volatilitätsbasierte Stop-Filter ist abgeschaltet."
        )
    )


if product_type == "CFD":

    warnings.append(
        (
            "🟡 CFD-Kostenmodell",
            (
                "Spread, Hebel und Overnight-Kosten sind "
                "Planungsannahmen und keine Live-Brokerwerte."
            )
        )
    )


if product_type == "Futures" and micro_active:

    warnings.append(
        (
            "🟡 Micro-Fallback",
            (
                "Die Micro-Kommission wurde aus dem Hauptkontrakt "
                "abgeleitet und sollte mit dem Broker geprüft werden."
            )
        )
    )


# ============================================================
# 19. TRADE APPROVAL
# ============================================================

if not hard_stops and not soft_blocks:

    if micro_active:

        trade_approval = (
            "🟢 TRADE FREIGEGEBEN "
            f"(Micro-Fallback: "
            f"{micro_contracts}x {micro_key_found})"
        )

    else:

        trade_approval = (
            "🟢 TRADE FREIGEGEBEN"
        )

elif hard_stops:

    trade_approval = (
        f"🔴 NO TRADE – "
        f"{len(hard_stops)} Hard Stop(s)"
    )

else:

    trade_approval = (
        f"🟠 SETUP BLOCKIERT – "
        f"{len(soft_blocks)} Soft Block(s)"
    )


# ============================================================
# 20. VERLUSTSERIEN-MONITOR
# ============================================================

simulated_equity, simulated_loss_pct = (
    calculate_risk_sequence(
        account_balance,
        effective_risk_pct,
        consecutive_losses
    )
)


# ============================================================
# 21. COCKPIT METRIKEN
# ============================================================

st.markdown("---")

gcol1, gcol2, gcol3, gcol4 = st.columns(4)

gear_symbol = {
    1: "🔴",
    2: "🟠",
    3: "🟡",
    4: "🟢",
    5: "🟢"
}[gear]

gcol1.metric(
    "GEAR",
    f"{gear} {gear_symbol}"
)

gcol2.metric(
    "Score",
    f"{total_score:.2f} / 7.00"
)

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
# 22. MTF ANALYSE
# ============================================================

st.markdown("---")

st.subheader(
    "📊 Multi-Timeframe Analyse"
)

m1, m2, m3, m4 = st.columns(4)

m1.metric(
    "4H",
    t240,
    d240
)

m2.metric(
    "1H",
    t60,
    d60
)

m3.metric(
    "15M",
    t15,
    d15
)

m4.metric(
    "Trade-Richtung",
    direction,
    (
        f"{aligned_count}/3 aligned"
    )
)

st.write(
    f"**MTF-Strukturpunkte:** "
    f"{structure_points:.2f} / 3.00"
)

st.write(
    f"**Richtungs-Alignment:** "
    f"{direction_points:.2f} / 1.00"
)

st.write(
    f"**MTF-Gesamtpunkte:** "
    f"{mtf_points:.2f} / 4.00"
)

st.write(
    f"**Sentimentpunkte:** "
    f"{sentiment_points:.2f} / 3.00"
)


if full_mtf_alignment:

    st.success(
        f"🟢 Alle drei Zeitebenen sind "
        f"auf {direction} ausgerichtet."
    )

elif aligned_count == 2:

    st.warning(
        f"🟡 2/3 Zeitebenen stimmen mit "
        f"{direction} überein."
    )

elif opposite_count >= 2:

    st.error(
        f"🔴 {opposite_count}/3 nicht-neutrale "
        f"Zeitebenen stehen gegen {direction}."
    )

else:

    st.info(
        "⚪ Kein klares MTF-Alignment."
    )


if mtf_direction_conflict:

    st.warning(
        "⚠️ 4H und 1H zeigen unterschiedliche "
        "Richtungen. Dies ist ein Warnsignal, "
        "aber nicht automatisch ein Hard Stop."
    )


# ============================================================
# 23. DREI-EBENEN-CHECK
# ============================================================

st.markdown("---")

e1, e2, e3 = st.columns(3)

with e1:

    st.subheader("1️⃣ Umfeld")

    if hard_stops:

        st.error(
            "🔴 Umfeld blockiert"
        )

    elif warnings:

        st.warning(
            "🟡 Umfeld mit Warnungen"
        )

    else:

        st.success(
            "🟢 Umfeld handelbar"
        )


with e2:

    st.subheader("2️⃣ Aggressivität")

    st.info(
        f"⚙️ Gear {gear} · "
        f"Risiko {effective_risk_pct:.2f}%"
    )


with e3:

    st.subheader("3️⃣ Setup")

    if (
        not hard_stops
        and not soft_blocks
    ):

        st.success(
            f"🟢 Valide · Netto-CRV "
            f"{net_rrr:.2f}"
        )

    elif hard_stops:

        st.error(
            "🔴 Hard Stop"
        )

    else:

        st.warning(
            "🟠 Soft Block"
        )


# ============================================================
# 24. DECISION CARD
# ============================================================

st.markdown("---")

st.subheader(
    "📋 Trade Decision Card"
)

if not hard_stops and not soft_blocks:

    st.success(
        f"## {trade_approval}"
    )

elif hard_stops:

    st.error(
        f"## {trade_approval}"
    )

else:

    st.warning(
        f"## {trade_approval}"
    )


# ============================================================
# 25. BLOCKER / WARNING DIAGNOSE
# ============================================================

if (
    hard_stops
    or soft_blocks
    or warnings
):

    st.markdown(
        "### 🔎 Decision-Diagnose"
    )

    if hard_stops:

        st.markdown(
            "**🔴 Hard Stops:**"
        )

        for title, desc in hard_stops:

            st.write(
                f"• **{title}**: {desc}"
            )

    if soft_blocks:

        st.markdown(
            "**🟠 Soft Blocks:**"
        )

        for title, desc in soft_blocks:

            st.write(
                f"• **{title}**: {desc}"
            )

    if warnings:

        st.markdown(
            "**🟡 Warnungen:**"
        )

        for title, desc in warnings:

            st.write(
                f"• **{title}**: {desc}"
            )


# ============================================================
# 26. DUAL-LIMIT MATRIX
# ============================================================

st.markdown(
    "#### ⚖️ Dual-Limit Sizing Matrix"
)

limit_unit_label = (
    "Kontrakte"
    if product_type == "Futures"
    else "Einheiten"
)

matrix_data = {

    "Limit-Ebene": [
        "1. Risikobudget",
        "2. Freie Planungs-Margin",
        "Resultierende Position"
    ],

    "Max. Einheiten": [

        (
            f"{sizing_res['max_risk_units']:,.2f} "
            f"{limit_unit_label}"
        ),

        (
            f"{sizing_res['max_margin_units']:,.2f} "
            f"{limit_unit_label}"
        ),

        (
            f"{final_contracts:,.2f} "
            f"{limit_unit_label}"
        )
    ],

    "Limitierender Faktor": [

        (
            f"Budget: "
            f"{risk_budget_eur:,.2f} €"
        ),

        (
            f"Freie Margin: "
            f"{free_margin_eur:,.2f} €"
        ),

        (
            sizing_limit_reason
        )
    ]
}

st.table(
    matrix_data
)

if (
    sizing_res["max_risk_units"]
    < sizing_res["max_margin_units"]
):

    st.success(
        "🛡️ Risikobudget ist der limitierende Faktor."
    )

elif (
    sizing_res["max_margin_units"]
    < sizing_res["max_risk_units"]
):

    st.warning(
        "💰 Freie Planungs-Margin ist der limitierende Faktor."
    )

else:

    st.info(
        "⚖️ Risiko- und Margin-Limit sind identisch."
    )


# ============================================================
# 27. PRODUKT / PREIS / KOSTEN
# ============================================================

dc1, dc2, dc3 = st.columns(3)


# ------------------------------------------------------------
# PRODUKT
# ------------------------------------------------------------

with dc1:

    st.markdown(
        "**Produkt & Ausführung**"
    )

    if micro_active:

        st.write(
            f"Original: **{original_market_key}**"
        )

        st.write(
            f"Ausweich-Instrument: "
            f"**{micro_key_found}**"
        )

        st.write(
            f"Handelsgröße: "
            f"**{micro_contracts} Kontrakte**"
        )

        st.write(
            f"Abgeleitete Micro-Kommission: "
            f"**{micro_comm_used_native:.2f} "
            f"{FUTURES[micro_key_found]['currency']} R/T**"
        )

        st.write(
            f"Margin: "
            f"**{required_margin_eur:,.2f} €**"
        )

    else:

        st.write(
            f"Produktart: **{product_type}**"
        )

        st.write(
            f"Instrument: **{market_key}**"
        )

        st.write(
            f"Richtung: **{direction.upper()}**"
        )

        if product_type == "Futures":

            st.write(
                f"Handelsgröße: "
                f"**{final_contracts} Kontrakte**"
            )

            st.write(
                f"Nominalexposure: "
                f"**{position_value_eur:,.2f} €**"
            )

            st.write(
                f"Planungs-Margin: "
                f"**{required_margin_eur:,.2f} €**"
            )

        else:

            st.write(
                f"Handelsgröße: "
                f"**{final_contracts:,.2f} Einheiten**"
            )

            st.write(
                f"Planungs-Hebel: **1:{leverage}**"
            )

            st.write(
                f"Nominaler Positionswert: "
                f"**{position_value_eur:,.2f} €**"
            )

            st.write(
                f"Planungs-Margin: "
                f"**{required_margin_eur:,.2f} €**"
            )


# ------------------------------------------------------------
# PREIS
# ------------------------------------------------------------

with dc2:

    st.markdown(
        "**Preis & Setup**"
    )

    st.write(
        f"Entry: **{entry_price:,.2f}**"
    )

    st.write(
        f"Stop Loss: **{stop_price:,.2f}**"
    )

    st.write(
        f"Target: **{target_price:,.2f}**"
    )

    st.write(
        f"Stop-Distanz: "
        f"**{risk_points:,.2f} Punkte**"
    )

    st.write(
        f"Target-Distanz: "
        f"**{reward_points:,.2f} Punkte**"
    )

    if stop_atr_ratio is not None:

        st.write(
            f"Stop / ATR: "
            f"**{stop_atr_ratio:.2f}x**"
        )

        st.write(
            f"ATR-Status: **{atr_status}**"
        )

    else:

        st.write(
            "Stop / ATR: **deaktiviert**"
        )

    if not is_valid_direction:

        st.error(
            "🔴 Preisstruktur ungültig."
        )


# ------------------------------------------------------------
# KOSTEN
# ------------------------------------------------------------

with dc3:

    st.markdown(
        "**Kosten & Effektives Risiko**"
    )

    st.write(
        f"Risikobudget: "
        f"**{risk_budget_eur:,.2f} €**"
    )

    st.write(
        f"Stop-Risiko: "
        f"**{actual_stop_risk_eur:,.2f} €**"
    )

    if product_type == "Futures":

        st.write(
            f"Kommission R/T: "
            f"**{comm_cost_eur:,.2f} €**"
        )

    else:

        st.write(
            f"Spread – Planungsannahme: "
            f"**{spread_cost_eur:,.2f} €**"
        )

        st.write(
            f"Overnight – Planungsannahme: "
            f"**{overnight_cost_eur:,.2f} €**"
        )

    st.write(
        f"Gesamtkosten: "
        f"**{total_costs_eur:,.2f} €**"
    )

    st.write(
        f"Netto-Risiko: "
        f"**{net_risk_eur:,.2f} €**"
    )

    st.write(
        f"Netto-CRV: "
        f"**{net_rrr:.2f}** "
        f"(Brutto: {gross_rrr:.2f})"
    )


# ============================================================
# 28. WAS-WÄRE-WENN ANALYSE
# ============================================================

st.markdown("---")

st.subheader(
    "🧭 Was-wäre-wenn-Analyse & Handlungsoptionen"
)


if (
    hard_stops
    or soft_blocks
):

    st.write(
        "Mögliche regelkonforme Anpassungspfade:"
    )


    # ========================================================
    # PFAD A – TARGET
    # ========================================================

    if (
        net_rrr < min_rrr_req
        and final_contracts > 0
        and net_risk_eur > 0
    ):

        required_net_reward_eur = (
            min_rrr_req
            * net_risk_eur
        )

        required_gross_reward_eur = (
            required_net_reward_eur
            + total_costs_eur
        )

        if product_type == "CFD":

            c_spec_path = CFDS[
                market_key
            ]

            fx_path = fx_rate_for_currency(
                c_spec_path["currency"],
                eurusd
            )

            reward_value_per_unit_eur = (
                c_spec_path["point_value"]
                * c_spec_path["contract_size"]
                / fx_path
            )

            denom = (
                reward_value_per_unit_eur
                * final_contracts
            )

        else:

            active_future = (
                market_key
            )

            f_spec_path = FUTURES[
                active_future
            ]

            fx_path = fx_rate_for_currency(
                f_spec_path["currency"],
                eurusd
            )

            value_per_point_eur = (
                (
                    f_spec_path["tick_value"]
                    / f_spec_path["tick_size"]
                )
                / fx_path
            )

            denom = (
                value_per_point_eur
                * final_contracts
            )

        reward_points_needed = (
            required_gross_reward_eur
            / denom
            if denom > 0
            else 0.0
        )

        target_needed = (
            entry_price
            + reward_points_needed
            if direction == "Long"
            else
            entry_price
            - reward_points_needed
        )

        st.write(
            f"• **Pfad A – Target anpassen:** "
            f"Target auf mindestens "
            f"**{target_needed:,.2f}** verschieben, "
            f"um das geforderte Netto-CRV von "
            f"**{min_rrr_req:.2f}** zu erreichen."
        )


    # ========================================================
    # PFAD B – STOP
    # ========================================================

    if (
        not atr_ok
        and atr_val > 0
        and stop_min_atr is not None
        and stop_max_atr is not None
    ):

        if atr_status == "Zu weit":

            max_stop_distance = (
                atr_val
                * stop_max_atr
            )

            s_suggest = (
                entry_price
                - max_stop_distance
                if direction == "Long"
                else
                entry_price
                + max_stop_distance
            )

            st.write(
                f"• **Pfad B – Stop enger setzen:** "
                f"Maximal **{max_stop_distance:,.2f} Punkte** "
                f"bzw. Stop bei **{s_suggest:,.2f}**."
            )

        elif atr_status == "Zu eng":

            min_stop_distance = (
                atr_val
                * stop_min_atr
            )

            s_suggest = (
                entry_price
                - min_stop_distance
                if direction == "Long"
                else
                entry_price
                + min_stop_distance
            )

            st.write(
                f"• **Pfad B – Stop weiter setzen:** "
                f"Mindestens **{min_stop_distance:,.2f} Punkte** "
                f"bzw. Stop bei **{s_suggest:,.2f}**."
            )


    # ========================================================
    # PFAD C – SIZING / KAPITAL
    # ========================================================

    if final_contracts <= 0:

        if product_type == "Futures":

            original_spec = FUTURES[
                original_market_key
            ]

            if original_spec.get("micro_key"):

                st.write(
                    f"• **Pfad C – Micro-Instrument:** "
                    f"Auf **{original_spec['micro_key']}** "
                    f"ausweichen."
                )

        if "Margin" in sizing_limit_reason:

            st.write(
                f"• **Pfad C – Margin reduzieren:** "
                f"Freie Planungs-Margin "
                f"({free_margin_eur:,.2f} €) "
                f"erhöhen oder Positionsgröße reduzieren."
            )

        else:

            st.write(
                f"• **Pfad C – Risikobudget:** "
                f"Risikobudget "
                f"({risk_budget_eur:,.2f} €) "
                f"reicht nicht für die Mindestgröße."
            )


    # ========================================================
    # PFAD D – MTF
    # ========================================================

    if entry_direction_conflict:

        st.write(
            f"• **Pfad D – MTF-Bestätigung abwarten:** "
            f"{opposite_count}/3 relevante Zeitebenen "
            f"stehen gegen {direction}."
        )


    # ========================================================
    # PFAD E – NEWS
    # ========================================================

    if news_soon == "Ja":

        st.write(
            "• **Pfad E – News abwarten:** "
            "Trade erst nach dem High-Impact-Event "
            "erneut bewerten."
        )


    # ========================================================
    # PFAD F – TRADE VERWERFEN
    # ========================================================

    st.write(
        "• **Pfad F – Trade verwerfen:** "
        "Setup ablehnen und auf ein regelkonformes "
        "Umfeld warten."
    )

else:

    st.success(
        "🟢 Das Setup entspricht sämtlichen "
        "quantitativen Vorgaben."
    )


# ============================================================
# 29. RISIKO-BREAKDOWN
# ============================================================

st.markdown("---")

st.subheader(
    "🔎 Risiko-Breakdown"
)

r1, r2, r3, r4 = st.columns(4)

r1.metric(
    "Stop-Risiko",
    f"{stop_loss_risk_eur:,.2f} €"
)

r2.metric(
    "Kosten",
    f"{total_costs_eur:,.2f} €"
)

r3.metric(
    "Netto-Risiko",
    f"{net_risk_eur:,.2f} €"
)

r4.metric(
    "Risiko-Budget",
    f"{risk_budget_eur:,.2f} €"
)


if risk_budget_exceeded:

    st.error(
        "⚠️ Das berechnete Netto-Risiko "
        "überschreitet das verfügbare "
        "Risikobudget."
    )

else:

    st.success(
        "🟢 Netto-Risiko liegt innerhalb "
        "des verfügbaren Risikobudgets."
    )


# ============================================================
# 30. RISK / LOSS-SEQUENCE MONITOR
# ============================================================

st.markdown("---")

st.subheader(
    "📉 Verlustserien- & Risiko-Monitor"
)

l1, l2, l3 = st.columns(3)

l1.metric(
    "Risiko pro Trade",
    f"{effective_risk_pct:.2f}%"
)

l2.metric(
    f"Equity nach {consecutive_losses} Verlusten",
    f"{simulated_equity:,.2f} €"
)

l3.metric(
    "Kumulierte Verlustquote",
    f"{simulated_loss_pct:.2f}%"
)

st.caption(
    "Der Verlustserien-Monitor ist eine einfache "
    "Szenarioanalyse bei gleichbleibendem Risiko "
    "pro Trade und keine statistische Risk-of-Ruin-Berechnung."
)


# ============================================================
# 31. EXPOSURE MONITOR
# ============================================================

st.markdown("---")

st.subheader(
    "💼 Exposure & Kapitalbindung"
)

x1, x2, x3 = st.columns(3)

x1.metric(
    "Nominalexposure",
    f"{position_value_eur:,.2f} €"
)

x2.metric(
    "Planungs-Margin",
    f"{required_margin_eur:,.2f} €"
)

if account_balance > 0:

    exposure_pct = (
        position_value_eur
        / account_balance
        * 100.0
    )

else:

    exposure_pct = 0.0

x3.metric(
    "Nominalexposure / Equity",
    f"{exposure_pct:.1f}%"
)


# ============================================================
# 32. KOSTEN-TRANSPARENZ
# ============================================================

st.markdown("---")

st.subheader(
    "💶 Kosten-Transparenz"
)

if product_type == "Futures":

    st.info(
        "Futures: Kommission wird beim Sizing "
        "als Risikokosten berücksichtigt und "
        "im Netto-Risiko exakt einmal addiert."
    )

else:

    st.info(
        "CFD: Spread und Overnight-Gebühr sind "
        "Planungsannahmen. Vor Live-Handel müssen "
        "die tatsächlichen Brokerbedingungen "
        "geprüft werden."
    )


# ============================================================
# 33. FINAL DECISION SUMMARY
# ============================================================

st.markdown("---")

st.subheader(
    "🛡️ Final Decision Summary"
)

summary_col1, summary_col2 = st.columns(2)

with summary_col1:

    st.write(
        f"**Trade:** {direction}"
    )

    st.write(
        f"**Instrument:** {market_key}"
    )

    st.write(
        f"**Gear:** {gear}"
    )

    st.write(
        f"**Score:** {total_score:.2f} / 7.00"
    )

    st.write(
        f"**Netto-CRV:** {net_rrr:.2f}"
    )


with summary_col2:

    st.write(
        f"**Position:** "
        f"{final_contracts:,.2f} {limit_unit_label}"
    )

    st.write(
        f"**Netto-Risiko:** "
        f"{net_risk_eur:,.2f} €"
    )

    st.write(
        f"**Tagesrisiko verfügbar:** "
        f"{remaining_daily_loss_eur:,.2f} €"
    )

    st.write(
        f"**Hard Stops:** "
        f"{len(hard_stops)}"
    )

    st.write(
        f"**Soft Blocks:** "
        f"{len(soft_blocks)}"
    )

    st.write(
        f"**Warnings:** "
        f"{len(warnings)}"
    )


# ============================================================
# 34. DISCLOSURE
# ============================================================

st.markdown("---")

st.caption(
    "Hinweis: Trade Manager & Decision Cockpit v2.8 "
    "ist ein quantitatives Planungs- und Decision-Gate. "
    "Margin-, Spread-, Hebel-, Kommissions- und "
    "Overnight-Werte sind teilweise Planungsannahmen "
    "und müssen vor dem Live-Handel mit den tatsächlichen "
    "Brokerbedingungen abgeglichen werden. "
    "Das Tool ersetzt keine Anlageberatung und keine "
    "Broker-/Börsenprüfung."
)