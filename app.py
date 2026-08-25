import streamlit as st
import math
import io
import zipfile
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests
import yfinance as yf

try:
    from pytrends.request import TrendReq
except Exception:
    TrendReq = None


# ============================================================
# 1. STREAMLIT CONFIG & DESIGN
# ============================================================

st.set_page_config(
    page_title="Trade Manager & Decision Cockpit v2.10",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ Trade Manager & Decision Cockpit v2.10")
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
        "max_leverage": 20,
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
        "max_leverage": 20,
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
        "max_leverage": 20,
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
        "max_leverage": 20,
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
        "max_leverage": 10,
        "default_overnight_pct": 0.025,
        "min_units": 0.01,
        "unit_step": 0.01,
        "margin_model": "Leverage-Based"
    },
}


# ============================================================
# 3. SIDEBAR – KONTO & RISIKOPARAMETER
# ============================================================

with st.sidebar:

    st.header("⚙️ Konto & Umrechnung")

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
        help="Planungs-Margin bestehender offener Positionen."
    )

    free_margin_eur = max(
        0.0,
        account_balance - used_margin_eur
    )

    st.caption(
        f"Verfügbare freie Planungs-Margin: "
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
        step=0.01,
        help="Planungskurs – kein Echtzeitkurs erforderlich."
    )

    st.markdown("---")

    st.subheader("🛡️ Tagesrisiko-Monitore")

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
        "Offenes Risiko ANDERER Positionen (€)",
        min_value=0.0,
        value=0.0,
        step=50.0,
        help="Risiko sonstiger offener Trades."
    )


# ============================================================
# 4. HAUPT-INPUTS
# ============================================================

col_market, col_trader, col_setup = st.columns(
    [1.15, 1.0, 1.2]
)


# ============================================================
# 4A. MARKT
# ============================================================

with col_market:

    st.subheader("1. Markt-Umfeld")

    st.caption(
        "Automatische Marktdaten – kein manueller "
        "Sentiment-/Trend-Input."
    )

    st.markdown("**Automatischer Multi-Timeframe Trend**")

    st.info(
        "4H / 1H / 15M werden aus Kursdaten berechnet."
    )

    st.markdown(
        "**Automatisches Sentiment / Volatilität**"
    )

    st.caption(
        "Fear & Greed und Volatilität werden weiter "
        "unten nach Auswahl des Instruments geladen."
    )


# ============================================================
# 4B. TRADER CONDITION
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
                "Z.B. +2 für Wochenend-/Triple-Fee "
                "als Planungsannahme."
            )
        )


# ============================================================
# 4C. PRODUKT & SETUP
# ============================================================

with col_setup:

    st.subheader("3. Produkt & Setup")

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

        leverage = None

        fut_comm_rt_native = (
            spec["default_comm_roundturn"]
        )

        spread_points = 0.0
        daily_overnight_pct = 0.0

        st.caption(
            f"Planungs-Kommission: "
            f"{fut_comm_rt_native:.2f} "
            f"{spec['currency']} R/T"
        )

    else:

        market_key = st.selectbox(
            "CFD-Instrument",
            list(CFDS.keys())
        )

        spec = CFDS[market_key]

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
            if l <= spec["max_leverage"]
        ]

        leverage = st.select_slider(
            "CFD-Hebel",
            options=leverage_options,
            value=(
                spec["max_leverage"]
                if spec["max_leverage"]
                in leverage_options
                else leverage_options[-1]
            ),
            help=(
                "Planungshebel für die Margin-Berechnung. "
                "Kein Einfluss auf das Stop-Loss-Risiko."
            )
        )

        spread_points = spec["default_spread"]
        daily_overnight_pct = (
            spec["default_overnight_pct"]
        )

        st.caption(
            f"Automatische Planungsannahmen: "
            f"Spread {spread_points:g} Punkte · "
            f"Overnight {daily_overnight_pct:.3f}%/Tag"
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
        help="Bei 0: ATR-Filter deaktiviert."
    )


# ============================================================
# 4D. AUTOMATED MARKET-ENVIRONMENT ENGINE
# ============================================================

MARKET_ENV_CONFIG = {

    "NQ (Nasdaq 100)": {
        "price_ticker": "NQ=F",
        "vol_ticker": "^VIX",
        "trend_keyword": "Nasdaq 100",
        "geo": "US",
        "cot_keyword": "NASDAQ-100"
    },

    "MNQ (Micro Nasdaq)": {
        "price_ticker": "NQ=F",
        "vol_ticker": "^VIX",
        "trend_keyword": "Nasdaq 100",
        "geo": "US",
        "cot_keyword": "NASDAQ-100"
    },

    "ES (S&P 500)": {
        "price_ticker": "ES=F",
        "vol_ticker": "^VIX",
        "trend_keyword": "S&P 500",
        "geo": "US",
        "cot_keyword": "S&P 500"
    },

    "MES (Micro S&P)": {
        "price_ticker": "ES=F",
        "vol_ticker": "^VIX",
        "trend_keyword": "S&P 500",
        "geo": "US",
        "cot_keyword": "S&P 500"
    },

    "GC (Gold)": {
        "price_ticker": "GC=F",
        "vol_ticker": "^GVZ",
        "trend_keyword": "Gold",
        "geo": "DE",
        "cot_keyword": "GOLD"
    },

    "MGC (Micro Gold)": {
        "price_ticker": "GC=F",
        "vol_ticker": "^GVZ",
        "trend_keyword": "Gold",
        "geo": "DE",
        "cot_keyword": "GOLD"
    },

    "CL (Crude Oil)": {
        "price_ticker": "CL=F",
        "vol_ticker": "^OVX",
        "trend_keyword": "Crude Oil",
        "geo": "DE",
        "cot_keyword": "CRUDE OIL"
    },

    "MCL (Micro Oil)": {
        "price_ticker": "CL=F",
        "vol_ticker": "^OVX",
        "trend_keyword": "Crude Oil",
        "geo": "DE",
        "cot_keyword": "CRUDE OIL"
    },

    "FDAX (DAX Future)": {
        "price_ticker": "^GDAXI",
        "vol_ticker": "^V2TX",
        "trend_keyword": "DAX",
        "geo": "DE",
        "cot_keyword": "EURO STOXX 50"
    },

    "FDXM (Mini DAX)": {
        "price_ticker": "^GDAXI",
        "vol_ticker": "^V2TX",
        "trend_keyword": "DAX",
        "geo": "DE",
        "cot_keyword": "EURO STOXX 50"
    },

    "NASDAQ 100 CFD": {
        "price_ticker": "NQ=F",
        "vol_ticker": "^VIX",
        "trend_keyword": "Nasdaq 100",
        "geo": "US",
        "cot_keyword": "NASDAQ-100"
    },

    "S&P 500 CFD": {
        "price_ticker": "ES=F",
        "vol_ticker": "^VIX",
        "trend_keyword": "S&P 500",
        "geo": "US",
        "cot_keyword": "S&P 500"
    },

    "GER40 CFD": {
        "price_ticker": "^GDAXI",
        "vol_ticker": "^V2TX",
        "trend_keyword": "DAX",
        "geo": "DE",
        "cot_keyword": "EURO STOXX 50"
    },

    "Gold CFD": {
        "price_ticker": "GC=F",
        "vol_ticker": "^GVZ",
        "trend_keyword": "Gold",
        "geo": "DE",
        "cot_keyword": "GOLD"
    },

    "Oil CFD": {
        "price_ticker": "CL=F",
        "vol_ticker": "^OVX",
        "trend_keyword": "Crude Oil",
        "geo": "DE",
        "cot_keyword": "CRUDE OIL"
    },
}


def _safe_float(value):

    try:
        return float(value)

    except (TypeError, ValueError):
        return None


def _signal_from_score(score):

    if score is None:
        return "Nicht verfügbar"

    if score >= 0.66:
        return "Supportive"

    if score >= 0.33:
        return "Neutral"

    return "Not supportive"


@st.cache_data(
    ttl=900,
    show_spinner=False
)
def fetch_cnn_fear_greed():

    url = (
        "https://production.dataviz.cnn.io/"
        "index/fearandgreed/graphdata"
    )

    try:

        r = requests.get(
            url,
            timeout=8,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        r.raise_for_status()

        data = r.json().get(
            "fear_and_greed",
            {}
        )

        score = _safe_float(
            data.get("score")
        )

        return {
            "score": score,
            "rating": data.get("rating"),
            "timestamp": data.get("timestamp")
        }

    except Exception as exc:

        return {
            "score": None,
            "rating": None,
            "timestamp": None,
            "error": str(exc)
        }


@st.cache_data(
    ttl=900,
    show_spinner=False
)
def fetch_volatility(ticker):

    try:

        df = yf.download(
            ticker,
            period="1y",
            interval="1d",
            auto_adjust=False,
            progress=False
        )

        if df is None or df.empty:
            return None

        close = df["Close"]

        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]

        close = pd.to_numeric(
            close,
            errors="coerce"
        ).dropna()

        if close.empty:
            return None

        current = float(
            close.iloc[-1]
        )

        ma20 = float(
            close.tail(20).mean()
        )

        pct = (
            float(
                (current / ma20 - 1.0) * 100.0
            )
            if ma20
            else None
        )

        return {
            "current": current,
            "ma20": ma20,
            "pct_vs_ma20": pct
        }

    except Exception:
        return None


# ============================================================
# TREND ENGINE
# 1H = 60 Tage
# 15M = 30 Tage
# ============================================================

@st.cache_data(
    ttl=900,
    show_spinner=False
)
def fetch_trends(ticker):

    result = {
        "4H": None,
        "1H": None,
        "15M": None
    }

    try:

        df1h = yf.download(
            ticker,
            period="60d",
            interval="1h",
            auto_adjust=False,
            progress=False
        )

        df15 = yf.download(
            ticker,
            period="30d",
            interval="15m",
            auto_adjust=False,
            progress=False
        )

        def _prep(df):

            if df is None or df.empty:
                return None

            close = df["Close"]

            if isinstance(
                close,
                pd.DataFrame
            ):
                close = close.iloc[:, 0]

            close = pd.to_numeric(
                close,
                errors="coerce"
            ).dropna()

            return close

        def _trend(close):

            if close is None or len(close) < 55:
                return None

            ema20 = close.ewm(
                span=20,
                adjust=False
            ).mean()

            ema50 = close.ewm(
                span=50,
                adjust=False
            ).mean()

            spread = float(
                (
                    ema20.iloc[-1]
                    - ema50.iloc[-1]
                )
                / close.iloc[-1]
            )

            slope = float(
                (
                    ema20.iloc[-1]
                    / ema20.iloc[-6]
                    - 1.0
                )
                * 100.0
            )

            if abs(spread) < 0.0015:

                label = (
                    "Choppy / Sideways"
                )

            elif (
                spread > 0
                and slope > 0
            ):

                label = "Impulse Wave"

            else:

                label = "Correction"

            return {
                "label": label,
                "spread": spread,
                "slope_pct": slope
            }

        c1 = _prep(df1h)
        c15 = _prep(df15)

        result["1H"] = _trend(c1)
        result["15M"] = _trend(c15)

        if c1 is not None:

            c4h = (
                c1
                .resample("4h")
                .last()
                .dropna()
            )

            result["4H"] = _trend(c4h)

        return result

    except Exception:

        return result


@st.cache_data(
    ttl=1800,
    show_spinner=False
)
def fetch_fred_macro():

    series = (
        "DGS10,DGS2,DFF,CPIAUCSL,"
        "CPILFESL,UNRATE"
    )

    url = (
        "https://fred.stlouisfed.org/"
        "graph/fredgraph.csv"
    )

    try:

        r = requests.get(
            url,
            params={
                "id": series
            },
            timeout=10,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        r.raise_for_status()

        df = pd.read_csv(
            io.StringIO(r.text),
            parse_dates=[
                "observation_date"
            ]
        )

        df = (
            df
            .set_index(
                "observation_date"
            )
            .replace(".", np.nan)
            .apply(
                pd.to_numeric,
                errors="coerce"
            )
        )

        out = {}

        for col in df.columns:

            s = df[col].dropna()

            if not s.empty:

                out[col] = {
                    "current": float(
                        s.iloc[-1]
                    ),
                    "prev": (
                        float(s.iloc[-2])
                        if len(s) > 1
                        else None
                    ),
                    "series": s
                }

        return out

    except Exception as exc:

        return {
            "error": str(exc)
        }


# ============================================================
# CFTC COT
# ============================================================

@st.cache_data(
    ttl=3600,
    show_spinner=False
)
def fetch_cot_legacy(keyword):

    """
    Best-effort CFTC COT lookup via the
    official Public Reporting Environment.
    """

    url = (
        "https://publicreportinghub.cftc.gov/"
        "api/v3/views/6dca-aqww/query.json"
    )

    try:

        q = (
            "SELECT "
            "market_and_exchange_names,"
            "report_date_as_yyyy_mm_dd,"
            "noncomm_positions_long_all,"
            "noncomm_positions_short_all "
            "WHERE upper("
            "market_and_exchange_names"
            ") like '%"
            + keyword.upper()
            + "%' "
            "ORDER BY "
            "report_date_as_yyyy_mm_dd "
            "DESC LIMIT 20"
        )

        r = requests.get(
            url,
            params={
                "pageNumber": 1,
                "pageSize": 20,
                "query": q
            },
            timeout=10,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        r.raise_for_status()

        rows = r.json().get(
            "data",
            []
        )

        if not rows:
            return None

        df = pd.DataFrame(rows)

        cols = {
            c.lower(): c
            for c in df.columns
        }

        date_col = cols.get(
            "report_date_as_yyyy_mm_dd"
        )

        long_col = cols.get(
            "noncomm_positions_long_all"
        )

        short_col = cols.get(
            "noncomm_positions_short_all"
        )

        if not all([
            date_col,
            long_col,
            short_col
        ]):
            return None

        df[date_col] = pd.to_datetime(
            df[date_col],
            errors="coerce"
        )

        df[long_col] = pd.to_numeric(
            df[long_col],
            errors="coerce"
        )

        df[short_col] = pd.to_numeric(
            df[short_col],
            errors="coerce"
        )

        df = (
            df
            .dropna(
                subset=[
                    date_col,
                    long_col,
                    short_col
                ]
            )
            .sort_values(
                date_col,
                ascending=False
            )
        )

        if df.empty:
            return None

        latest = df.iloc[0]

        net = float(
            latest[long_col]
            - latest[short_col]
        )

        prev_net = None

        if len(df) > 1:

            prev = df.iloc[1]

            prev_net = float(
                prev[long_col]
                - prev[short_col]
            )

        return {
            "date": (
                latest[date_col]
                .date()
                .isoformat()
            ),
            "net": net,
            "change": (
                net - prev_net
                if prev_net is not None
                else None
            ),
            "long": float(
                latest[long_col]
            ),
            "short": float(
                latest[short_col]
            ),
        }

    except Exception:

        return None


@st.cache_data(
    ttl=86400,
    show_spinner=False
)
def fetch_google_trends(
    keyword,
    geo
):

    if TrendReq is None:
        return None

    try:

        pytrends = TrendReq(
            hl="en-US",
            tz=0,
            timeout=(5, 10)
        )

        pytrends.build_payload(
            [keyword],
            timeframe="today 12-m",
            geo=geo
        )

        df = (
            pytrends
            .interest_over_time()
        )

        if (
            df is None
            or df.empty
            or keyword not in df.columns
        ):
            return None

        s = pd.to_numeric(
            df[keyword],
            errors="coerce"
        ).dropna()

        if len(s) < 30:
            return None

        current = float(
            s.iloc[-1]
        )

        avg90 = float(
            s.tail(90).mean()
        )

        change = (
            float(
                (current / avg90 - 1.0)
                * 100.0
            )
            if avg90
            else None
        )

        return {
            "current": current,
            "avg90": avg90,
            "change_pct": change
        }

    except Exception:

        return None


@st.cache_data(
    ttl=86400,
    show_spinner=False
)
def calculate_seasonality(ticker):

    try:

        df = yf.download(
            ticker,
            period="15y",
            interval="1d",
            auto_adjust=False,
            progress=False
        )

        if df is None or df.empty:
            return None

        close = df["Close"]

        if isinstance(
            close,
            pd.DataFrame
        ):
            close = close.iloc[:, 0]

        close = pd.to_numeric(
            close,
            errors="coerce"
        ).dropna()

        if len(close) < 1000:
            return None

        ret = (
            close
            .pct_change()
            .dropna()
        )

        # ====================================================
        # MODERNISIERTE UTC-ZEIT
        # ====================================================

        current_month = (
            datetime.now(
                timezone.utc
            ).month
        )

        month_ret = ret[
            ret.index.month
            == current_month
        ]

        if month_ret.empty:
            return None

        avg_daily = float(
            month_ret.mean()
        )

        positive_share = float(
            (
                month_ret > 0
            ).mean()
            * 100.0
        )

        annualized_month = float(
            (
                (1.0 + avg_daily) ** 21
                - 1.0
            )
            * 100.0
        )

        if (
            positive_share >= 58
            and annualized_month > 0
        ):

            signal = "Supportive"

        elif (
            positive_share <= 42
            and annualized_month < 0
        ):

            signal = "Not supportive"

        else:

            signal = "Neutral"

        return {
            "month": current_month,
            "avg_daily": avg_daily,
            "positive_share": positive_share,
            "annualized_month_proxy": (
                annualized_month
            ),
            "signal": signal
        }

    except Exception:

        return None


# ============================================================
# CLASSIFICATION FUNCTIONS
# ============================================================

def classify_fear_greed(score):

    if score is None:
        return None, None

    if score >= 75:
        return "Not supportive", 0.0

    if score >= 55:
        return "Supportive", 0.75

    if score >= 45:
        return "Neutral", 0.375

    if score >= 25:
        return "Supportive", 0.75

    return "Supportive", 0.75


def classify_volatility(vol):

    if not vol:
        return None, None

    cur = vol["current"]
    ma20 = vol["ma20"]

    if (
        cur <= 20
        and cur <= ma20 * 1.05
    ):
        return "Supportive", 0.75

    if (
        cur <= 28
        and cur <= ma20 * 1.20
    ):
        return "Neutral", 0.375

    return "Not supportive", 0.0


def classify_rates(macro):

    dgs10 = macro.get(
        "DGS10",
        {}
    )

    dgs2 = macro.get(
        "DGS2",
        {}
    )

    if not dgs10 or not dgs2:
        return None, None

    y10 = dgs10.get("current")
    p10 = dgs10.get("prev")
    y2 = dgs2.get("current")

    spread = (
        y10 - y2
        if y10 is not None
        and y2 is not None
        else None
    )

    delta10 = (
        y10 - p10
        if y10 is not None
        and p10 is not None
        else None
    )

    if delta10 is None:
        return "Neutral", 0.375

    if delta10 <= -0.05:
        return "Supportive", 0.75

    if delta10 >= 0.05:
        return "Not supportive", 0.0

    return "Neutral", 0.375


def classify_fed(macro):

    dff = macro.get(
        "DFF",
        {}
    )

    s = (
        dff.get("series")
        if dff
        else None
    )

    if s is None or len(s) < 30:
        return None, None

    delta = float(
        s.iloc[-1]
        - s.iloc[-22]
    )

    if delta <= -0.10:
        return "Supportive", 0.75

    if delta >= 0.10:
        return "Not supportive", 0.0

    return "Neutral", 0.375


def classify_macro(macro):

    cpi = macro.get(
        "CPIAUCSL",
        {}
    ).get("series")

    unemp = macro.get(
        "UNRATE",
        {}
    ).get("series")

    if (
        cpi is None
        or unemp is None
        or len(cpi) < 13
        or len(unemp) < 4
    ):
        return None, None

    cpi_yoy = float(
        (
            cpi.iloc[-1]
            / cpi.iloc[-13]
            - 1.0
        )
        * 100.0
    )

    cpi_prev = float(
        (
            cpi.iloc[-2]
            / cpi.iloc[-14]
            - 1.0
        )
        * 100.0
    ) if len(cpi) >= 14 else cpi_yoy

    unemp_change = float(
        unemp.iloc[-1]
        - unemp.iloc[-4]
    )

    if (
        cpi_yoy < cpi_prev
        and unemp_change <= 0
    ):
        return "Supportive", 0.75

    if (
        cpi_yoy > cpi_prev
        and unemp_change > 0
    ):
        return "Not supportive", 0.0

    return "Neutral", 0.375


# ============================================================
# LOAD MARKET ENVIRONMENT DATA
# ============================================================

env_cfg = MARKET_ENV_CONFIG.get(
    market_key,
    MARKET_ENV_CONFIG["S&P 500 CFD"]
)

trend_data = fetch_trends(
    env_cfg["price_ticker"]
)

vol_data = fetch_volatility(
    env_cfg["vol_ticker"]
)

fng_data = fetch_cnn_fear_greed()

fred_data = fetch_fred_macro()


# ============================================================
# COT
# EINHEITLICHER AUFRUF FÜR FUTURES UND CFDs
# ============================================================

cot_data = fetch_cot_legacy(
    env_cfg["cot_keyword"]
)


gtrends_data = fetch_google_trends(
    env_cfg["trend_keyword"],
    env_cfg["geo"]
)

seasonality_data = calculate_seasonality(
    env_cfg["price_ticker"]
)


# ============================================================
# TREND SCORING
# ============================================================

trend_labels = {
    tf: (
        trend_data.get(tf, {})
        or {}
    ).get("label")
    for tf in [
        "4H",
        "1H",
        "15M"
    ]
}

trend_available = sum(
    1
    for tf in trend_labels
    if trend_labels[tf] is not None
)

trend_points = (
    None
    if trend_available == 0
    else sum(
        1.0
        if trend_labels[tf]
        == "Impulse Wave"
        else (
            0.5
            if trend_labels[tf]
            == "Correction"
            else 0.0
        )
        for tf in trend_labels
        if trend_labels[tf]
        is not None
    )
)

trend_max = float(
    trend_available
)


# ============================================================
# OTHER CORE FACTORS
# ============================================================

fg_signal, fg_points = classify_fear_greed(
    fng_data.get("score")
)

vol_signal, vol_points = classify_volatility(
    vol_data
)

rates_signal, rates_points = classify_rates(
    fred_data
)

fed_signal, fed_points = classify_fed(
    fred_data
)

macro_signal, macro_points = classify_macro(
    fred_data
)


# ============================================================
# CFTC COT – OPTIONALER CORE-FAKTOR
#
# WICHTIG:
# Fehlende COT-Daten werden NICHT als 0 Punkte
# gewertet.
#
# Daten vorhanden:
#     Faktor wird bewertet.
#
# Daten nicht vorhanden:
#     Faktor wird aus core_max entfernt.
# ============================================================

cot_points = None
cot_signal = None

if (
    cot_data
    and cot_data.get("net") is not None
):

    net = cot_data["net"]

    change = (
        cot_data.get("change")
        if cot_data.get("change")
        is not None
        else 0.0
    )

    if (
        net > 0
        and change >= 0
    ):

        cot_signal = "Supportive"
        cot_points = 0.75

    elif (
        net < 0
        and change <= 0
    ):

        cot_signal = "Not supportive"
        cot_points = 0.0

    else:

        cot_signal = "Neutral"
        cot_points = 0.375


# ============================================================
# CORE SCORE
# ============================================================

core_components = [

    (
        "Trend",
        trend_points,
        trend_max
    ),

    (
        "Fear & Greed",
        fg_points,
        0.75
    ),

    (
        "Volatilität",
        vol_points,
        0.75
    ),

    (
        "Zinsen",
        rates_points,
        0.75
    ),

    (
        "Fed",
        fed_points,
        0.75
    ),

    (
        "Makro",
        macro_points,
        0.75
    ),

    (
        "CFTC COT",
        cot_points,
        0.75
    ),
]


core_raw = sum(
    points
    for _, points, maximum
    in core_components
    if points is not None
)

core_max = sum(
    maximum
    for _, points, maximum
    in core_components
    if points is not None
)

core_score = (
    core_raw
    / core_max
    * 6.0
    if core_max > 0
    else 0.0
)


# ============================================================
# MARKET ENVIRONMENT DISPLAY
# ============================================================

with st.expander(
    "📡 Automatisiertes Market Environment",
    expanded=True
):

    m1, m2, m3, m4 = st.columns(4)

    m1.metric(
        "Fear & Greed",
        (
            f"{fng_data['score']:.0f}"
            if fng_data.get("score")
            is not None
            else "N/A"
        )
    )

    m2.metric(
        "Volatilität",
        (
            f"{vol_data['current']:.1f}"
            if vol_data
            else "N/A"
        )
    )

    m3.metric(
        "US 10Y",
        (
            f"{fred_data.get('DGS10', {}).get('current', float('nan')):.2f}%"
            if fred_data.get("DGS10")
            else "N/A"
        )
    )

    m4.metric(
        "Fed Funds",
        (
            f"{fred_data.get('DFF', {}).get('current', float('nan')):.2f}%"
            if fred_data.get("DFF")
            else "N/A"
        )
    )

    st.markdown(
        "**Core Market Environment – "
        "bestimmt den Gear-Score**"
    )

    rows = []

    for tf in [
        "4H",
        "1H",
        "15M"
    ]:

        rows.append([
            tf,
            trend_labels[tf]
            or "Nicht verfügbar",
            "Core"
        ])

    rows.extend([

        [
            "Fear & Greed",
            fg_signal
            or "Nicht verfügbar",
            "Core"
        ],

        [
            "Volatilität",
            vol_signal
            or "Nicht verfügbar",
            "Core"
        ],

        [
            "Zinsen",
            rates_signal
            or "Nicht verfügbar",
            "Core"
        ],

        [
            "Fed Funds",
            fed_signal
            or "Nicht verfügbar",
            "Core"
        ],

        [
            "Makro",
            macro_signal
            or "Nicht verfügbar",
            "Core"
        ],

        [
            "CFTC COT",
            cot_signal
            or "Nicht verfügbar",
            "Core"
        ],
    ])

    st.dataframe(
        pd.DataFrame(
            rows,
            columns=[
                "Faktor",
                "Signal",
                "Einfluss"
            ]
        ),
        hide_index=True,
        use_container_width=True
    )

    available_components = len([
        1
        for _, p, _
        in core_components
        if p is not None
    ])

    st.caption(
        f"Core Score: **{core_score:.2f} / 6.00** · "
        f"Datenabdeckung: "
        f"{available_components}/"
        f"{len(core_components)} Komponenten"
    )


    # ========================================================
    # ZUSATZFAKTOREN
    # ========================================================

    st.markdown(
        "**🔎 Zusatzfaktoren – separat, "
        "nicht Bestandteil des Core-Gear-Scores**"
    )

    z1, z2 = st.columns(2)

    with z1:

        st.markdown(
            "**Google Trends**"
        )

        if gtrends_data:

            gt_signal = (
                "Supportive"
                if gtrends_data[
                    "change_pct"
                ] > 10
                else (
                    "Not supportive"
                    if gtrends_data[
                        "change_pct"
                    ] < -10
                    else "Neutral"
                )
            )

            st.write(
                f"Suchinteresse: "
                f"**{gtrends_data['current']:.0f}** "
                f"· 90T-Mittel: "
                f"**{gtrends_data['avg90']:.1f}**"
            )

            st.write(
                f"Veränderung: "
                f"**{gtrends_data['change_pct']:+.1f}%** "
                f"→ **{gt_signal}**"
            )

        else:

            st.warning(
                "Google Trends nicht verfügbar."
            )

        st.caption(
            "Gewicht im Core-Gear-Score: 0 %"
        )


    with z2:

        st.markdown(
            "**Saisonalität**"
        )

        if seasonality_data:

            st.write(
                f"Aktueller Monat: "
                f"**{seasonality_data['month']}**"
            )

            st.write(
                f"Positive Tage: "
                f"**{seasonality_data['positive_share']:.1f}%**"
            )

            st.write(
                f"Monats-Proxy: "
                f"**{seasonality_data['annualized_month_proxy']:+.1f}%** "
                f"→ **{seasonality_data['signal']}**"
            )

        else:

            st.warning(
                "Saisonalität nicht verfügbar."
            )

        st.caption(
            "Gewicht im Core-Gear-Score: 0 %"
        )


    # ========================================================
    # FRED DETAIL
    # ========================================================

    with st.expander(
        "📊 FRED-Detaildaten",
        expanded=False
    ):

        if fred_data.get("error"):

            st.warning(
                "FRED-Daten momentan nicht verfügbar."
            )

        else:

            fred_rows = []

            labels = {
                "DGS10": "US 10Y Yield",
                "DGS2": "US 2Y Yield",
                "DFF": "Fed Funds Effective",
                "CPIAUCSL": "CPI",
                "CPILFESL": "Core CPI",
                "UNRATE": "Arbeitslosenquote"
            }

            for key, label in labels.items():

                if key in fred_data:

                    fred_rows.append([
                        label,
                        fred_data[key][
                            "current"
                        ]
                    ])

            st.dataframe(
                pd.DataFrame(
                    fred_rows,
                    columns=[
                        "Reihe",
                        "Aktuell"
                    ]
                ),
                hide_index=True,
                use_container_width=True
            )


    # ========================================================
    # COT DISPLAY
    # ========================================================

    if cot_data:

        cot_change = (
            cot_data["change"]
            if cot_data.get("change")
            is not None
            else 0.0
        )

        st.caption(
            f"CFTC COT: Report "
            f"{cot_data['date']} · "
            f"Net Non-Commercial "
            f"{cot_data['net']:,.0f} · "
            f"Wochenänderung "
            f"{cot_change:+,.0f}"
        )

    else:

        st.caption(
            "CFTC COT: keine passende/"
            "abrufbare Positionierungsreihe "
            "für dieses Instrument. "
            "Der Faktor wurde aus dem "
            "Core-Score entfernt."
        )


# ============================================================
# 5. GEAR ENGINE
# ============================================================

penalties = 0.0

if trader_stress == "Mittel":
    penalties += 0.5

elif trader_stress == "Hoch":
    penalties += 1.5

if location != "Home Office":
    penalties += 0.5


total_score = max(
    0.0,
    core_score - penalties
)


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
    risk_mult = 0.0
    stop_min_atr = None
    stop_max_atr = None
    scale_out = "N/A"


# ============================================================
# 6. PRE-CALCULATION
# ============================================================

if direction == "Long":

    is_valid_direction = (
        stop_price
        < entry_price
        < target_price
    )

else:

    is_valid_direction = (
        stop_price
        > entry_price
        > target_price
    )


risk_points = abs(
    entry_price - stop_price
)

reward_points = abs(
    target_price - entry_price
)

gross_rrr = (
    reward_points / risk_points
    if risk_points > 0
    else 0.0
)


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

    atr_ok = (
        stop_min_atr
        <= stop_atr_ratio
        <= stop_max_atr
    )


# ============================================================
# 8. RISIKOBUDGET
# ============================================================

effective_risk_pct = (
    base_risk_pct
    * risk_mult
)

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

total_daily_risk_used_eur = (
    daily_loss_realized_eur
    + daily_open_risk_eur
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

            "units": (
                0.0
                if p_type == "CFD"
                else 0
            ),

            "max_risk_units": 0,

            "max_margin_units": 0,

            "limit_reason":
                "Kein Budget / Margin verfügbar",

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

        fx_conv = (
            eurusd
            if f_spec["currency"] == "USD"
            else 1.0
        )

        r_ticks = (
            risk_points
            / f_spec["tick_size"]
        )

        stop_risk_per_contract_eur = (
            r_ticks
            * f_spec["tick_value"]
            / fx_conv
        )

        comm_native = (
            fut_comm_override
            if fut_comm_override
            is not None
            else f_spec[
                "default_comm_roundturn"
            ]
        )

        comm_eur_per_contract = (
            comm_native
            / fx_conv
        )

        total_risk_per_contract = (
            stop_risk_per_contract_eur
            + comm_eur_per_contract
        )

        max_risk_units = (
            math.floor(
                budget_eur
                / total_risk_per_contract
            )
            if total_risk_per_contract > 0
            else 0
        )

        margin_per_contract_eur = (
            f_spec["margin_native"]
            / fx_conv
        )

        max_margin_units = (
            math.floor(
                free_marg_eur
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
                "Sowohl Risikobudget als auch "
                "freie Margin unzureichend"
            )

        elif (
            max_risk_units
            < max_margin_units
        ):

            limit_reason = (
                "Risikobudget"
            )

        elif (
            max_margin_units
            < max_risk_units
        ):

            limit_reason = (
                "Freie Planungs-Margin"
            )

        else:

            limit_reason = (
                "Risikobudget & Margin identisch"
            )

        act_stop_risk = (
            units
            * stop_risk_per_contract_eur
        )

        rew_ticks = (
            reward_points
            / f_spec["tick_size"]
        )

        act_reward = (
            units
            * rew_ticks
            * f_spec["tick_value"]
            / fx_conv
        )

        tot_comm = (
            units
            * comm_eur_per_contract
        )

        m_req = (
            units
            * margin_per_contract_eur
        )

        return {

            "units": units,

            "max_risk_units":
                max_risk_units,

            "max_margin_units":
                max_margin_units,

            "limit_reason":
                limit_reason,

            "act_stop_risk":
                act_stop_risk,

            "act_reward":
                act_reward,

            "m_req":
                m_req,

            "tot_spread": 0.0,

            "tot_overnight": 0.0,

            "tot_comm":
                tot_comm,

            "pos_val": 0.0
        }


    # ========================================================
    # CFD
    # ========================================================

    c_spec = CFDS[m_key]

    fx_conv = (
        eurusd
        if c_spec["currency"] == "USD"
        else 1.0
    )

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

        total_fee_days = (
            nights
            + extra_units
        )

        overnight_cost_per_unit = (
            entry_price
            * c_spec["point_value"]
            * c_spec["contract_size"]
            / fx_conv
            * (
                daily_overnight_pct
                / 100.0
            )
            * total_fee_days
        )

    total_costs_per_unit = (
        spread_cost_per_unit
        + overnight_cost_per_unit
    )

    total_risk_per_unit_eur = (
        stop_cost_per_unit
        + total_costs_per_unit
    )

    nominal_per_unit_eur = (
        entry_price
        * c_spec["point_value"]
        * c_spec["contract_size"]
        / fx_conv
    )

    margin_per_unit_eur = (
        nominal_per_unit_eur
        / leverage
        if leverage > 0
        else 0.0
    )

    raw_risk_units = (
        budget_eur
        / total_risk_per_unit_eur
        if total_risk_per_unit_eur > 0
        else 0.0
    )

    raw_margin_units = (
        free_marg_eur
        / margin_per_unit_eur
        if margin_per_unit_eur > 0
        else 0.0
    )

    max_risk_units = (
        math.floor(
            raw_risk_units
            / c_spec["unit_step"]
        )
        * c_spec["unit_step"]
    )

    max_margin_units = (
        math.floor(
            raw_margin_units
            / c_spec["unit_step"]
        )
        * c_spec["unit_step"]
    )

    units = min(
        max_risk_units,
        max_margin_units
    )

    if units < c_spec["min_units"]:
        units = 0.0

    if (
        max_risk_units
        < c_spec["min_units"]
        and max_margin_units
        < c_spec["min_units"]
    ):

        limit_reason = (
            "Sowohl Risikobudget als auch "
            "freie Margin unter Mindestgröße"
        )

    elif (
        max_risk_units
        < max_margin_units
    ):

        limit_reason = (
            "Risikobudget"
        )

    elif (
        max_margin_units
        < max_risk_units
    ):

        limit_reason = (
            "Freie Planungs-Margin"
        )

    else:

        limit_reason = (
            "Risikobudget & Margin identisch"
        )

    # Stop-Risiko ausschließlich Verlust bis Stop.
    act_stop_risk = (
        units
        * stop_cost_per_unit
    )

    tot_spread = (
        units
        * spread_cost_per_unit
    )

    tot_overnight = (
        units
        * overnight_cost_per_unit
    )

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

    m_req = (
        units
        * margin_per_unit_eur
    )

    return {

        "units": units,

        "max_risk_units":
            max_risk_units,

        "max_margin_units":
            max_margin_units,

        "limit_reason":
            limit_reason,

        "act_stop_risk":
            act_stop_risk,

        "act_reward":
            act_reward,

        "m_req":
            m_req,

        "tot_spread":
            tot_spread,

        "tot_overnight":
            tot_overnight,

        "tot_comm": 0.0,

        "pos_val":
            pos_val
    }


# ============================================================
# 10. POSITION CALCULATION
# ============================================================

is_on = (
    holding_period
    == "Overnight"
)

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

final_contracts = (
    sizing_res["units"]
)

actual_stop_risk_eur = (
    sizing_res["act_stop_risk"]
)

actual_reward_eur = (
    sizing_res["act_reward"]
)

required_margin_eur = (
    sizing_res["m_req"]
)

spread_cost_eur = (
    sizing_res["tot_spread"]
)

overnight_cost_eur = (
    sizing_res["tot_overnight"]
)

comm_cost_eur = (
    sizing_res["tot_comm"]
)

position_value_eur = (
    sizing_res["pos_val"]
)

sizing_limit_reason = (
    sizing_res["limit_reason"]
)


# ============================================================
# 11. MICRO-FALLBACK
# ============================================================

micro_active = False
micro_key_found = None
micro_contracts = 0
macro_risk_needed_for_1_contract = 0.0
micro_comm_used_native = 0.0

if (
    product_type == "Futures"
    and final_contracts == 0
):

    macro_spec = FUTURES[
        market_key
    ]

    fx_conv = (
        eurusd
        if macro_spec["currency"]
        == "USD"
        else 1.0
    )

    macro_stop = (
        (
            risk_points
            / macro_spec["tick_size"]
        )
        * macro_spec["tick_value"]
        / fx_conv
    )

    macro_comm = (
        fut_comm_rt_native
        / fx_conv
    )

    macro_risk_needed_for_1_contract = (
        macro_stop
        + macro_comm
    )

    micro_key_found = (
        macro_spec.get(
            "micro_key"
        )
    )

    if micro_key_found:

        micro_spec = FUTURES[
            micro_key_found
        ]

        micro_comm_used_native = (
            fut_comm_rt_native
            * (
                micro_spec[
                    "tick_value"
                ]
                / macro_spec[
                    "tick_value"
                ]
            )
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

            m_tot_cost = (
                m_res["tot_comm"]
            )

            m_net_risk = (
                m_res["act_stop_risk"]
                + m_tot_cost
            )

            m_net_rew = max(
                0.0,
                m_res["act_reward"]
                - m_tot_cost
            )

            m_net_rrr = (
                m_net_rew
                / m_net_risk
                if m_net_risk > 0
                else 0.0
            )

            if (
                is_valid_direction
                and m_net_rrr
                >= min_rrr_req
            ):

                micro_active = True

                micro_contracts = (
                    m_cnt
                )

                final_contracts = (
                    m_cnt
                )

                actual_stop_risk_eur = (
                    m_res["act_stop_risk"]
                )

                actual_reward_eur = (
                    m_res["act_reward"]
                )

                required_margin_eur = (
                    m_res["m_req"]
                )

                comm_cost_eur = (
                    m_res["tot_comm"]
                )

                sizing_limit_reason = (
                    m_res["limit_reason"]
                )

                sizing_res = m_res


# ============================================================
# 12. FINAL COST & RISK ENGINE
# ============================================================

total_costs_eur = (
    spread_cost_eur
    + overnight_cost_eur
    + comm_cost_eur
)

stop_loss_risk_eur = (
    actual_stop_risk_eur
)

net_risk_eur = (
    stop_loss_risk_eur
    + total_costs_eur
)

net_reward_eur = max(
    0.0,
    actual_reward_eur
    - total_costs_eur
)

net_rrr = (
    net_reward_eur
    / net_risk_eur
    if net_risk_eur > 0
    else 0.0
)

risk_budget_exceeded = (
    net_risk_eur
    > risk_budget_eur + 0.01
)


# ============================================================
# 13. HIERARCHISCHES DECISION GATE
# ============================================================

primary_blockers = []
secondary_blockers = []


if not is_valid_direction:

    primary_blockers.append((
        "🔴 Ungültige Preisstruktur",
        "Stop Loss & Target-Order passen "
        "nicht zur Richtung."
    ))


if news_soon == "Ja":

    primary_blockers.append((
        "🔴 High-Impact News",
        "Macro-Event (<30 Min) blockiert "
        "die Ausführung."
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
        "Tages-Risikobudget vollständig "
        "verbraucht."
    ))


if (
    not atr_ok
    and atr_val > 0
):

    secondary_blockers.append((
        "🔴 ATR-Filter Verletzung",
        (
            f"Stop-Abstand "
            f"({stop_atr_ratio:.1f}x ATR) "
            f"liegt außerhalb des Korridors "
            f"({stop_min_atr:.1f}x - "
            f"{stop_max_atr:.1f}x)."
        )
    ))


if (
    final_contracts <= 0
    and not micro_active
):

    secondary_blockers.append((
        "🔴 Keine handelbare Positionsgröße",
        (
            f"Limitierender Faktor: "
            f"{sizing_limit_reason}."
        )
    ))


if (
    net_rrr < min_rrr_req
    and final_contracts > 0
):

    secondary_blockers.append((
        "🔴 Netto-CRV zu gering",
        (
            f"Netto-CRV {net_rrr:.2f} "
            f"untersteht gefordertem "
            f"Minimum von "
            f"{min_rrr_req:.2f}."
        )
    ))


if risk_budget_exceeded:

    secondary_blockers.append((
        "🔴 Risikobudget überschritten",
        (
            f"Netto-Risiko "
            f"{net_risk_eur:,.2f} € "
            f"> Budget "
            f"{risk_budget_eur:,.2f} €."
        )
    ))


all_blockers = (
    primary_blockers
    + secondary_blockers
)


# ============================================================
# 14. TRADE APPROVAL
# ============================================================

if not all_blockers:

    if micro_active:

        trade_approval = (
            "🟢 TRADE FREIGEGEBEN "
            f"(Micro-Fallback: "
            f"{micro_contracts}x "
            f"{micro_key_found})"
        )

    else:

        trade_approval = (
            "🟢 TRADE FREIGEGEBEN"
        )

else:

    trade_approval = (
        f"🔴 NO TRADE – "
        f"{len(all_blockers)} Blocker aktiv"
    )


# ============================================================
# 15. COCKPIT METRIKEN
# ============================================================

st.markdown("---")

gcol1, gcol2, gcol3, gcol4 = (
    st.columns(4)
)


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
    f"{total_score:.2f}"
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
# 16. DREI-EBENEN-CHECK
# ============================================================

st.markdown("---")

e1, e2, e3 = st.columns(3)


with e1:

    st.subheader("1️⃣ Umfeld")

    if primary_blockers:

        st.error(
            "🔴 Umfeld blockiert"
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
        is_valid_direction
        and atr_ok
        and net_rrr >= min_rrr_req
        and final_contracts > 0
        and not risk_budget_exceeded
    ):

        st.success(
            f"🟢 Valide · "
            f"Netto-CRV {net_rrr:.2f}"
        )

    else:

        st.error(
            "🔴 Setup abgelehnt"
        )


if atr_val == 0:

    st.warning(
        "⚠️ **ATR deaktiviert** – "
        "Volatilitätsbasierter Stop-Filter "
        "ist abgeschaltet."
    )


# ============================================================
# 17. DECISION CARD
# ============================================================

st.markdown("---")

st.subheader(
    "📋 Trade Decision Card"
)


if not all_blockers:

    st.success(
        f"## {trade_approval}"
    )

else:

    st.error(
        f"## {trade_approval}"
    )


# ============================================================
# 18. BLOCKER DIAGNOSE
# ============================================================

if (
    primary_blockers
    or secondary_blockers
):

    st.markdown(
        "### ❌ Blocker-Diagnose"
    )

    if primary_blockers:

        st.markdown(
            "**Primäre Struktur-Blocker "
            "(Hard Stops):**"
        )

        for b_title, b_desc in (
            primary_blockers
        ):

            st.write(
                f"• **{b_title}**: "
                f"{b_desc}"
            )

    if secondary_blockers:

        st.markdown(
            "**Sekundäre Ausführungs-Blocker "
            "(Setup / Sizing):**"
        )

        for b_title, b_desc in (
            secondary_blockers
        ):

            st.write(
                f"• **{b_title}**: "
                f"{b_desc}"
            )


# ============================================================
# 19. DUAL-LIMIT MATRIX
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

        "2. Freie "
        "Planungs-Margin",

        "Resultierende Position"
    ],

    "Max. Einheiten": [

        f"{sizing_res['max_risk_units']:,.2f} "
        f"{limit_unit_label}",

        f"{sizing_res['max_margin_units']:,.2f} "
        f"{limit_unit_label}",

        f"**{final_contracts:,.2f} "
        f"{limit_unit_label}**"
    ],

    "Limitierender Faktor": [

        f"Max. Risikobudget: "
        f"{risk_budget_eur:,.2f} €",

        f"Freie Margin: "
        f"{free_margin_eur:,.2f} €",

        f"**{sizing_limit_reason}**"
    ]
}


st.table(
    matrix_data
)


# ============================================================
# 20. PRODUKT / PREIS / KOSTEN
# ============================================================

dc1, dc2, dc3 = (
    st.columns(3)
)


with dc1:

    st.markdown(
        "**Produkt & Ausführung**"
    )

    if micro_active:

        st.write(
            f"Original: **{market_key}**"
        )

        st.write(
            f"1 Kontrakt benötigt: "
            f"**{macro_risk_needed_for_1_contract:,.2f} €**"
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
            f"Micro-Kommission "
            f"(proportional): "
            f"**{micro_comm_used_native:.2f} "
            f"USD R/T**"
        )

        st.write(
            f"Gebundene Planungs-Margin: "
            f"**{required_margin_eur:,.2f} €**"
        )

    else:

        st.write(
            f"Produktart: "
            f"**{product_type}**"
        )

        st.write(
            f"Instrument: "
            f"**{market_key}**"
        )

        st.write(
            f"Richtung: "
            f"**{direction.upper()}**"
        )

        if product_type == "Futures":

            st.write(
                f"Handelsgröße: "
                f"**{final_contracts} Kontrakte**"
            )

            st.write(
                f"Gebundene Planungs-Margin: "
                f"**{required_margin_eur:,.2f} €**"
            )

        else:

            st.write(
                f"Handelsgröße: "
                f"**{final_contracts:,.2f} Einheiten**"
            )

            st.write(
                f"Hebel: "
                f"**1:{leverage}**"
            )

            st.write(
                f"Nominaler Positionswert: "
                f"**{position_value_eur:,.2f} €**"
            )

            st.write(
                f"Gebundene Planungs-Margin: "
                f"**{required_margin_eur:,.2f} €**"
            )


with dc2:

    st.markdown(
        "**Preis & Setup**"
    )

    st.write(
        f"Entry: "
        f"**{entry_price:,.2f}**"
    )

    st.write(
        f"Stop Loss: "
        f"**{stop_price:,.2f}**"
    )

    st.write(
        f"Target: "
        f"**{target_price:,.2f}**"
    )

    st.write(
        f"Stop-Distanz: "
        f"**{risk_points:,.2f} Punkte**"
    )

    if stop_atr_ratio is not None:

        st.write(
            f"Stop / ATR: "
            f"**{stop_atr_ratio:.1f}x**"
        )

    else:

        st.write(
            "Stop / ATR: **deaktiviert**"
        )


with dc3:

    st.markdown(
        "**Kosten & Effektives Risiko**"
    )

    st.write(
        f"Max. Risikobudget: "
        f"**{risk_budget_eur:,.2f} €**"
    )

    st.write(
        f"Brutto Stop-Risiko: "
        f"**{actual_stop_risk_eur:,.2f} €**"
    )

    if product_type == "Futures":

        st.write(
            f"Börsen-Kommission "
            f"(Planung): "
            f"**{comm_cost_eur:,.2f} €**"
        )

    else:

        st.write(
            f"CFD Spread-Kosten "
            f"(Planung): "
            f"**{spread_cost_eur:,.2f} €**"
        )

        st.write(
            f"CFD Overnight-Kosten "
            f"(Planung): "
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
# 21. WAS-WÄRE-WENN ANALYSE
# ============================================================

st.markdown("---")

st.subheader(
    "🧭 Was-wäre-wenn-Analyse & Handlungsoptionen"
)


if all_blockers:

    st.write(
        "Um eine Handelsfreigabe für dieses "
        "Setup zu erreichen, stehen folgende "
        "Anpassungspfade bereit:"
    )


    # ========================================================
    # PFAD A – TARGET
    # ========================================================

    if (
        net_rrr < min_rrr_req
        and final_contracts > 0
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

            fx_conv_path = (
                eurusd
                if c_spec_path[
                    "currency"
                ] == "USD"
                else 1.0
            )

            reward_value_per_unit_eur = (
                c_spec_path[
                    "point_value"
                ]
                * c_spec_path[
                    "contract_size"
                ]
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

            f_spec_path = FUTURES[
                active_future
            ]

            fx_conv_path = (
                eurusd
                if f_spec_path[
                    "currency"
                ] == "USD"
                else 1.0
            )

            value_per_point_native = (
                f_spec_path[
                    "tick_value"
                ]
                / f_spec_path[
                    "tick_size"
                ]
            )

            value_per_point_eur = (
                value_per_point_native
                / fx_conv_path
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

        if reward_points_needed > 0:

            target_needed = (
                entry_price
                + reward_points_needed
                if direction == "Long"
                else
                entry_price
                - reward_points_needed
            )

            st.write(
                f"• **Pfad A – Target verschieben:** "
                f"Target auf "
                f"**{target_needed:,.2f}** "
                f"anpassen, um das geforderte "
                f"Netto-CRV von "
                f"**{min_rrr_req:.2f}** "
                f"zu erreichen."
            )


    # ========================================================
    # PFAD B – STOP
    # ========================================================

    if (
        not atr_ok
        and atr_val > 0
        and stop_max_atr is not None
    ):

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
            f"• **Pfad B – Stop anpassen:** "
            f"Stop-Abstand auf maximal "
            f"**{max_stop_distance:,.2f} Punkte** "
            f"({stop_max_atr:.1f}x ATR) "
            f"reduzieren "
            f"(Stop bei "
            f"**{s_suggest:,.2f}**)."
        )


    # ========================================================
    # PFAD C – SIZING / KAPITAL
    # ========================================================

    if final_contracts <= 0:

        if (
            product_type == "Futures"
            and FUTURES[
                market_key
            ].get("micro_key")
        ):

            st.write(
                f"• **Pfad C – "
                f"Instrumenten-Wechsel:** "
                f"Hauptkontrakt zu groß für "
                f"Risikobudget "
                f"({risk_budget_eur:,.2f} €). "
                f"Auf **"
                f"{FUTURES[market_key]['micro_key']}"
                f"** ausweichen."
            )

        elif "Margin" in (
            sizing_limit_reason
        ):

            st.write(
                f"• **Pfad C – "
                f"Kapital freigeben:** "
                f"Freie Planungs-Margin "
                f"unzureichend "
                f"({free_margin_eur:,.2f} €). "
                f"Positionen schließen oder "
                f"Margin-Bedarf verringern."
            )

        else:

            st.write(
                f"• **Pfad C – Risikobudget:** "
                f"Risikobudget "
                f"({risk_budget_eur:,.2f} €) "
                f"zu gering für die "
                f"Mindestkontraktgröße."
            )


    # ========================================================
    # PFAD D
    # ========================================================

    st.write(
        "• **Pfad D – Trade verworfen:** "
        "Setup ablehnen und auf ein "
        "regelkonformes Umfeld warten."
    )


else:

    st.success(
        "🟢 Das Setup entspricht sämtlichen "
        "quantitativen Vorgaben. "
        "Keinerlei Anpassung notwendig."
    )


# ============================================================
# 22. TRANSPARENTER RISIKO-BREAKDOWN
# ============================================================

st.markdown("---")

st.subheader(
    "🔎 Risiko-Breakdown"
)

r1, r2, r3, r4 = (
    st.columns(4)
)

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
# 23. PLANUNGSPARAMETER-TRANSPARENZ
# ============================================================

st.markdown("---")

st.subheader(
    "ℹ️ Verwendete Planungsparameter"
)


if product_type == "CFD":

    p1, p2, p3 = (
        st.columns(3)
    )

    p1.metric(
        "Planungs-Spread",
        f"{spread_points:g} Punkte"
    )

    p2.metric(
        "Overnight / Tag",
        f"{daily_overnight_pct:.3f}%"
    )

    p3.metric(
        "Planungs-Hebel",
        f"1:{leverage}"
    )

    st.caption(
        "Diese Werte sind bewusst als stabile "
        "Planungsannahmen hinterlegt. "
        "Für das Decision Gate müssen nicht "
        "bei jedem Trade aktuelle Spread- oder "
        "Overnight-Werte manuell eingegeben "
        "werden."
    )

else:

    st.caption(
        f"Futures-Planung: Kommission "
        f"{fut_comm_rt_native:.2f} "
        f"{spec['currency']} R/T · "
        f"Margin "
        f"{spec['margin_native']:,.0f} "
        f"{spec['currency']} je Kontrakt."
    )


# ============================================================
# 24. DISCLOSURE
# ============================================================

st.markdown("---")

st.caption(
    "Hinweis: v2.10 Cockpit ist ein rein "
    "quantitatives Decision Gate. "
    "Spread-, Overnight-, Kommissions- "
    "und Marginwerte sind "
    "Planungsannahmen und keine "
    "Echtzeit-Brokerdaten. "
    "Sie müssen regelmäßig gegen die "
    "tatsächlichen Brokerbedingungen "
    "validiert werden. Keine Anlageberatung."
)