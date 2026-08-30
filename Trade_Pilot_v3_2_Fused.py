import streamlit as st
import math
import io
import zipfile
import requests
import numpy as np
import pandas as pd

try:
    import yfinance as yf
except ImportError:
    yf = None

try:
    from fredapi import Fred
except ImportError:
    Fred = None

try:
    from pytrends.request import TrendReq
except ImportError:
    TrendReq = None

# ============================================================
# 1. STREAMLIT CONFIG & DESIGN
# ============================================================
st.set_page_config(
    page_title="Trade Manager & Decision Cockpit v3.4 Fused",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ Trade Manager & Decision Cockpit v3.4 Fused")
st.caption(
    "Systematisches Decision-Gate – Market-Regime-Engine + MTF + "
    "Price Context mit Yahoo-Automatik & eToro-Overrides + "
    "Dual-Limit Sizing & Was-wäre-wenn-Analyse"
)
st.markdown("---")


# ============================================================
# 2. GEMEINSAME MARKET-REGIME-LOGIK
# ============================================================
#
# Der Trade Pilot benutzt dieselbe quantitative Regime-Engine
# wie das Market Regime Dashboard.
#
# WICHTIG:
# - keine zweite/alte CFTC-Logik im Pilot
# - CFTC = Non-Commercials
# - 12-Tage-Freshness-Gate
# - DX-Y.NYB statt DX=F
# - identische FRED-/Liquidity-/Coverage-/MCI-Logik
# - PCR bleibt Zusatzinformation und ist kein Säulengewicht
#
# regime_engine.py muss im selben GitHub-Verzeichnis liegen.
# ============================================================

from regime_engine import (
    ASSET_CONFIGS,
    calculate_model_confidence,
    fetch_multi_asset_data,
    format_feed_date,
    get_regime_label,
)


TRADE_PILOT_ASSET_MAP = {
    "NQ (Nasdaq 100)": "Nasdaq 100",
    "MNQ (Micro Nasdaq)": "Nasdaq 100",
    "ES (S&P 500)": "S&P 500",
    "MES (Micro S&P)": "S&P 500",
    "GC (Gold)": "Gold (XAU/USD)",
    "MGC (Micro Gold)": "Gold (XAU/USD)",
    "CL (Crude Oil)": "WTI Crude Oil",
    "MCL (Micro Oil)": "WTI Crude Oil",

    "NASDAQ 100 CFD": "Nasdaq 100",
    "S&P 500 CFD": "S&P 500",
    "Gold CFD": "Gold (XAU/USD)",
    "Oil CFD": "WTI Crude Oil",

    # Das aktuelle Regime Dashboard besitzt noch kein eigenes DAX-Modell.
    "FDAX (DAX Future)": None,
    "FDXM (Mini DAX)": None,
    "GER40 CFD": None,
}


# ============================================================
# PRICE CONTEXT – AUTOMATISCHE REFERENZTICKER
# ============================================================
#
# Futures:
#   Levels werden möglichst aus dem entsprechenden Yahoo-Future
#   abgeleitet.
#
# CFDs:
#   Yahoo-Index/Future dient nur als Referenz. Broker-CFD-Kurse
#   können wegen Handelszeiten, Spread und Preisstellung abweichen.
# ============================================================

PRICE_CONTEXT_MAP = {
    "NQ (Nasdaq 100)": {
        "ticker": "NQ=F",
        "source_label": "Nasdaq-100 Future (Yahoo)",
        "proxy": False
    },
    "MNQ (Micro Nasdaq)": {
        "ticker": "NQ=F",
        "source_label": "Nasdaq-100 Future (Yahoo)",
        "proxy": True
    },
    "ES (S&P 500)": {
        "ticker": "ES=F",
        "source_label": "S&P-500 E-mini Future (Yahoo)",
        "proxy": False
    },
    "MES (Micro S&P)": {
        "ticker": "ES=F",
        "source_label": "S&P-500 E-mini Future (Yahoo)",
        "proxy": True
    },
    "GC (Gold)": {
        "ticker": "GC=F",
        "source_label": "Gold Future (Yahoo)",
        "proxy": False
    },
    "MGC (Micro Gold)": {
        "ticker": "GC=F",
        "source_label": "Gold Future (Yahoo)",
        "proxy": True
    },
    "CL (Crude Oil)": {
        "ticker": "CL=F",
        "source_label": "WTI Future (Yahoo)",
        "proxy": False
    },
    "MCL (Micro Oil)": {
        "ticker": "CL=F",
        "source_label": "WTI Future (Yahoo)",
        "proxy": True
    },
    "FDAX (DAX Future)": {
        "ticker": "^GDAXI",
        "source_label": "DAX Performance Index (Yahoo-Referenz)",
        "proxy": True
    },
    "FDXM (Mini DAX)": {
        "ticker": "^GDAXI",
        "source_label": "DAX Performance Index (Yahoo-Referenz)",
        "proxy": True
    },

    "NASDAQ 100 CFD": {
        "ticker": "^NDX",
        "source_label": "Nasdaq-100 Index (Yahoo-Referenz)",
        "proxy": True
    },
    "S&P 500 CFD": {
        "ticker": "^GSPC",
        "source_label": "S&P-500 Index (Yahoo-Referenz)",
        "proxy": True
    },
    "GER40 CFD": {
        "ticker": "^GDAXI",
        "source_label": "DAX Performance Index (Yahoo-Referenz)",
        "proxy": True
    },
    "Gold CFD": {
        "ticker": "GC=F",
        "source_label": "Gold Future (Yahoo-Referenz)",
        "proxy": True
    },
    "Oil CFD": {
        "ticker": "CL=F",
        "source_label": "WTI Future (Yahoo-Referenz)",
        "proxy": True
    },
}


def _normalize_market_history(frame):
    if (
        frame is None
        or not isinstance(frame, pd.DataFrame)
        or frame.empty
    ):
        return pd.DataFrame()

    d = frame.copy()

    if isinstance(d.columns, pd.MultiIndex):
        # yfinance kann auch bei einem Ticker MultiIndex-Spalten liefern.
        if len(d.columns.get_level_values(0).unique()) == 1:
            d.columns = d.columns.get_level_values(-1)
        elif len(d.columns.get_level_values(-1).unique()) == 1:
            d.columns = d.columns.get_level_values(0)

    required = [
        "Open",
        "High",
        "Low",
        "Close"
    ]

    if not all(
        c in d.columns
        for c in required
    ):
        return pd.DataFrame()

    d = d[
        [
            c
            for c in [
                "Open",
                "High",
                "Low",
                "Close",
                "Volume"
            ]
            if c in d.columns
        ]
    ].copy()

    for c in d.columns:
        d[c] = pd.to_numeric(
            d[c],
            errors="coerce"
        )

    idx = pd.to_datetime(
        d.index,
        errors="coerce"
    )

    if isinstance(
        idx,
        pd.DatetimeIndex
    ):
        if idx.tz is not None:
            idx = idx.tz_convert(
                None
            )

        d.index = idx.normalize()

    d = (
        d[
            ~d.index.isna()
        ]
        .sort_index()
    )

    d = d[
        ~d.index.duplicated(
            keep="last"
        )
    ]

    d = d.dropna(
        subset=[
            "High",
            "Low",
            "Close"
        ]
    )

    return d


def _previous_trading_week_window():
    """
    Bestimmt die letzte abgeschlossene Handelswoche.

    Montag bis Freitag:
        vorherige Kalenderwoche.

    Samstag/Sonntag:
        die gerade abgeschlossene Handelswoche gilt bereits
        als Vorwoche für die kommende Session.
    """
    now_berlin = (
        pd.Timestamp.now(
            tz="Europe/Berlin"
        )
        .tz_localize(None)
        .normalize()
    )

    weekday = (
        now_berlin.weekday()
    )

    if weekday >= 5:
        next_monday = (
            now_berlin
            + pd.Timedelta(
                days=7 - weekday
            )
        )

        current_week_start = (
            next_monday
        )

    else:
        current_week_start = (
            now_berlin
            - pd.Timedelta(
                days=weekday
            )
        )

    previous_week_start = (
        current_week_start
        - pd.Timedelta(
            days=7
        )
    )

    previous_week_end = (
        current_week_start
        - pd.Timedelta(
            days=1
        )
    )

    return (
        previous_week_start,
        previous_week_end
    )


@st.cache_data(
    ttl=900,
    show_spinner=False
)
def fetch_price_context(
    market_key
):
    """
    Automatischer Price Context aus Yahoo/yfinance.

    Enthält:
    - Previous Day Close / High / Low
    - Previous Week Close / High / Low
    - Daily EMA20 / EMA50 / EMA200
    - letzten verfügbaren Yahoo-Referenzkurs

    Heute noch laufende Tageskerzen werden NICHT als Vortag
    interpretiert.
    """
    cfg = PRICE_CONTEXT_MAP.get(
        market_key
    )

    if cfg is None:
        return {
            "ok": False,
            "reason": (
                "Kein Price-Context-Ticker "
                "für dieses Instrument definiert."
            ),
            "ticker": None,
            "source_label": "n/a",
            "proxy": True
        }

    if yf is None:
        return {
            "ok": False,
            "reason": "yfinance ist nicht installiert.",
            "ticker": cfg["ticker"],
            "source_label": cfg["source_label"],
            "proxy": cfg["proxy"]
        }

    ticker = (
        cfg["ticker"]
    )

    try:
        raw = yf.download(
            ticker,
            period="18mo",
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False
        )

        d = _normalize_market_history(
            raw
        )

        if len(d) < 50:
            return {
                "ok": False,
                "reason": (
                    "Zu wenige verwertbare "
                    "Yahoo-Tagesdaten."
                ),
                "ticker": ticker,
                "source_label": cfg["source_label"],
                "proxy": cfg["proxy"]
            }

        today_utc = (
            pd.Timestamp.now(
                tz="UTC"
            )
            .tz_localize(None)
            .normalize()
        )

        latest_market_date = (
            pd.Timestamp(
                d.index[-1]
            )
        )

        latest_reference_price = float(
            d["Close"].iloc[-1]
        )

        # Eine Tageskerze mit heutigem Datum kann intraday noch
        # unvollständig sein und darf nicht als "Vortag" gelten.
        completed = d[
            d.index < today_utc
        ].copy()

        if completed.empty:
            return {
                "ok": False,
                "reason": (
                    "Keine abgeschlossene Tageskerze verfügbar."
                ),
                "ticker": ticker,
                "source_label": cfg["source_label"],
                "proxy": cfg["proxy"]
            }

        previous_day = (
            completed.iloc[-1]
        )

        previous_day_date = (
            pd.Timestamp(
                completed.index[-1]
            )
        )

        # Daily EMAs nur auf abgeschlossenen Tageskerzen.
        close_completed = (
            completed["Close"]
            .astype(float)
        )

        ema20_series = (
            close_completed
            .ewm(
                span=20,
                adjust=False,
                min_periods=20
            )
            .mean()
        )

        ema50_series = (
            close_completed
            .ewm(
                span=50,
                adjust=False,
                min_periods=50
            )
            .mean()
        )

        ema200_series = (
            close_completed
            .ewm(
                span=200,
                adjust=False,
                min_periods=200
            )
            .mean()
        )

        ema20 = (
            float(
                ema20_series.iloc[-1]
            )
            if pd.notna(
                ema20_series.iloc[-1]
            )
            else None
        )

        ema50 = (
            float(
                ema50_series.iloc[-1]
            )
            if pd.notna(
                ema50_series.iloc[-1]
            )
            else None
        )

        ema200 = (
            float(
                ema200_series.iloc[-1]
            )
            if pd.notna(
                ema200_series.iloc[-1]
            )
            else None
        )

        (
            previous_week_start,
            previous_week_end
        ) = _previous_trading_week_window()

        week_data = completed[
            (
                completed.index
                >= previous_week_start
            )
            &
            (
                completed.index
                <= previous_week_end
            )
        ].copy()

        # Fallback, falls Feiertage/Indexierung dazu führen, dass
        # der berechnete Kalenderbereich leer bleibt.
        if week_data.empty:
            week_periods = (
                completed.index
                .to_period(
                    "W-SUN"
                )
            )

            unique_periods = list(
                pd.Index(
                    week_periods
                ).unique()
            )

            if len(unique_periods) >= 2:
                target_period = (
                    unique_periods[-2]
                )

                week_data = completed[
                    week_periods
                    == target_period
                ].copy()

            elif unique_periods:
                target_period = (
                    unique_periods[-1]
                )

                week_data = completed[
                    week_periods
                    == target_period
                ].copy()

        if week_data.empty:
            return {
                "ok": False,
                "reason": (
                    "Vorwochendaten konnten "
                    "nicht bestimmt werden."
                ),
                "ticker": ticker,
                "source_label": cfg["source_label"],
                "proxy": cfg["proxy"]
            }

        previous_week_close = float(
            week_data["Close"].iloc[-1]
        )

        previous_week_high = float(
            week_data["High"].max()
        )

        previous_week_low = float(
            week_data["Low"].min()
        )

        previous_week_last_date = (
            pd.Timestamp(
                week_data.index[-1]
            )
        )

        return {
            "ok": True,
            "reason": "",
            "ticker": ticker,
            "source_label": cfg["source_label"],
            "proxy": cfg["proxy"],

            "reference_price": (
                latest_reference_price
            ),
            "reference_date": (
                latest_market_date
            ),

            "pdc": float(
                previous_day["Close"]
            ),
            "pdh": float(
                previous_day["High"]
            ),
            "pdl": float(
                previous_day["Low"]
            ),
            "previous_day_date": (
                previous_day_date
            ),

            "pwc": (
                previous_week_close
            ),
            "pwh": (
                previous_week_high
            ),
            "pwl": (
                previous_week_low
            ),
            "previous_week_date": (
                previous_week_last_date
            ),

            "ema20": ema20,
            "ema50": ema50,
            "ema200": ema200,
            "ema_date": (
                previous_day_date
            )
        }

    except Exception as exc:
        return {
            "ok": False,
            "reason": (
                "Yahoo Price Context Fehler: "
                f"{str(exc)[:180]}"
            ),
            "ticker": ticker,
            "source_label": cfg["source_label"],
            "proxy": cfg["proxy"]
        }


def _resolve_manual_override(
    auto_value,
    use_override,
    manual_value
):
    """
    Liefert effektiven Wert + Quellenlabel.

    Standard:
        Yahoo / Automatik

    Bei aktiviertem Override:
        eToro / manuell
    """
    if use_override:
        try:
            manual = float(
                manual_value
            )

            if np.isfinite(
                manual
            ):
                return (
                    manual,
                    "eToro / manuell"
                )

        except Exception:
            pass

    return (
        auto_value,
        "Yahoo / automatisch"
    )


def _format_level(
    value
):
    if value is None:
        return "n/a"

    try:
        x = float(
            value
        )

        if not np.isfinite(
            x
        ):
            return "n/a"

        if abs(x) >= 1000:
            return f"{x:,.2f}"

        if abs(x) >= 100:
            return f"{x:,.2f}"

        return f"{x:,.3f}"

    except Exception:
        return "n/a"


def _format_context_date(
    value
):
    if value is None:
        return "n/a"

    try:
        return (
            pd.Timestamp(
                value
            )
            .strftime(
                "%d.%m.%Y"
            )
        )

    except Exception:
        return "n/a"


def _range_position(
    price,
    low,
    high
):
    try:
        price = float(
            price
        )

        low = float(
            low
        )

        high = float(
            high
        )

        if (
            not np.isfinite(price)
            or not np.isfinite(low)
            or not np.isfinite(high)
            or high <= low
        ):
            return None

        return (
            (price - low)
            / (high - low)
            * 100.0
        )

    except Exception:
        return None


def _safe_float(value, default=None):
    try:
        x = float(value)
        return x if np.isfinite(x) else default
    except Exception:
        return default


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_market_environment(asset_name):
    """
    Adapter vom gemeinsamen Regime-Modell zum Trade Pilot.

    Rückgabe enthält:
    - Final Regime Score
    - MCI
    - gewichtete Model Data Coverage
    - Model Confidence
    - sechs Säulenscores
    - Feed-Status und Datenstände
    """
    if asset_name is None:
        return {
            "status": "NOT_MAPPED",
            "asset": None,
            "reason": (
                "Für dieses Instrument existiert im aktuellen "
                "Market Regime Dashboard noch kein eigenes Asset-Modell."
            ),
            "feeds": {},
            "feed_dates": {},
            "feed_notes": {},
            "regime_score": None,
            "mci": None,
            "coverage": None,
            "confidence": None,
            "confidence_label": "n/a",
            "regime_label": "Nicht verfügbar",
            "macro_score": None,
            "positioning_score": None,
            "internals_score": None,
            "technical_score": None,
            "fundamental_score": None,
            "early_warning_score": None,
            "volatility": None,
            "asset_price": None,
            "data_date": None,
        }

    if asset_name not in ASSET_CONFIGS:
        return {
            "status": "UNAVAILABLE",
            "asset": asset_name,
            "reason": "Asset ist in der gemeinsamen Regime-Engine nicht definiert.",
            "feeds": {},
            "feed_dates": {},
            "feed_notes": {},
            "regime_score": None,
            "mci": None,
            "coverage": None,
            "confidence": None,
            "confidence_label": "n/a",
            "regime_label": "Nicht verfügbar",
            "macro_score": None,
            "positioning_score": None,
            "internals_score": None,
            "technical_score": None,
            "fundamental_score": None,
            "early_warning_score": None,
            "volatility": None,
            "asset_price": None,
            "data_date": None,
        }

    try:
        (
            df_dash,
            feed_status,
            feed_dates,
            feed_notes
        ) = fetch_multi_asset_data(
            asset_name
        )
    except Exception as exc:
        return {
            "status": "UNAVAILABLE",
            "asset": asset_name,
            "reason": f"Regime-Engine Fehler: {str(exc)[:180]}",
            "feeds": {},
            "feed_dates": {},
            "feed_notes": {},
            "regime_score": None,
            "mci": None,
            "coverage": None,
            "confidence": None,
            "confidence_label": "n/a",
            "regime_label": "Nicht verfügbar",
            "macro_score": None,
            "positioning_score": None,
            "internals_score": None,
            "technical_score": None,
            "fundamental_score": None,
            "early_warning_score": None,
            "volatility": None,
            "asset_price": None,
            "data_date": None,
        }

    if df_dash is None or df_dash.empty:
        return {
            "status": "UNAVAILABLE",
            "asset": asset_name,
            "reason": "Regime-Engine lieferte keine verwertbaren Modelldaten.",
            "feeds": feed_status or {},
            "feed_dates": feed_dates or {},
            "feed_notes": feed_notes or {},
            "regime_score": None,
            "mci": None,
            "coverage": None,
            "confidence": None,
            "confidence_label": "n/a",
            "regime_label": "Nicht verfügbar",
            "macro_score": None,
            "positioning_score": None,
            "internals_score": None,
            "technical_score": None,
            "fundamental_score": None,
            "early_warning_score": None,
            "volatility": None,
            "asset_price": None,
            "data_date": None,
        }

    model_confidence, confidence_label = (
        calculate_model_confidence(
            feed_status,
            asset_name,
            df_dash
        )
    )

    latest = df_dash.iloc[-1]

    regime_score = _safe_float(
        latest.get("Final_Regime_Score")
    )
    mci = _safe_float(
        latest.get("MCI")
    )
    coverage = _safe_float(
        latest.get("Model_Data_Coverage"),
        0.0
    )

    # Gleiche Qualitätsgrenzen wie das Dashboard-Execution-Gate:
    # >=65 Confidence und >=60 Coverage = grundsätzlich verwertbar.
    if (
        model_confidence >= 85
        and coverage >= 80
    ):
        status = "LIVE"
    elif (
        model_confidence >= 65
        and coverage >= 60
    ):
        status = "PARTIAL"
    else:
        status = "LOW_QUALITY"

    return {
        "status": status,
        "asset": asset_name,
        "reason": "",
        "feeds": feed_status,
        "feed_dates": feed_dates,
        "feed_notes": feed_notes,
        "regime_score": regime_score,
        "mci": mci,
        "coverage": coverage,
        "confidence": float(model_confidence),
        "confidence_label": confidence_label,
        "regime_label": (
            get_regime_label(regime_score)
            if regime_score is not None
            else "Nicht verfügbar"
        ),
        "macro_score": _safe_float(
            latest.get("Saeule_Makroökonomie")
        ),
        "positioning_score": _safe_float(
            latest.get("Saeule_Positionierung")
        ),
        "internals_score": _safe_float(
            latest.get("Saeule_Marktinterna")
        ),
        "technical_score": _safe_float(
            latest.get("Saeule_Technischer_Trend")
        ),
        "fundamental_score": _safe_float(
            latest.get("Saeule_Fundamentale_Faktoren")
        ),
        "early_warning_score": _safe_float(
            latest.get("Saeule_Fruehwarnindikatoren")
        ),
        "volatility": _safe_float(
            latest.get("Raw_Volatility")
        ),
        "asset_price": _safe_float(
            latest.get("Asset_Price")
        ),
        "data_date": (
            df_dash.index[-1]
            if len(df_dash.index) > 0
            else None
        ),
    }


# ============================================================
# 3. INSTRUMENTEN-DATENBANK
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

    st.markdown(
        "**Multi-Timeframe Marktstruktur & Richtung**"
    )

    # --------------------------------------------------------
    # 4H
    # --------------------------------------------------------

    st.markdown(
        "**4H – übergeordnete Struktur**"
    )

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

    st.markdown(
        "**1H – mittlere Struktur**"
    )

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

    st.markdown(
        "**15M – Entry-Struktur**"
    )

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

    directions_preview = [
        d240,
        d60,
        d15
    ]

    long_preview = (
        directions_preview.count(
            "Long"
        )
    )

    short_preview = (
        directions_preview.count(
            "Short"
        )
    )

    if long_preview > short_preview:
        dominant_preview = "Long"
    elif short_preview > long_preview:
        dominant_preview = "Short"
    else:
        dominant_preview = "Neutral"

    if (
        d240 == d60 == d15
        and d240 != "Neutral"
    ):
        st.success(
            f"🟢 MTF vollständig ausgerichtet: {d240}"
        )
    elif dominant_preview != "Neutral":
        st.warning(
            "🟡 MTF gemischt – dominante Richtung: "
            f"{dominant_preview}"
        )
    else:
        st.info(
            "⚪ Keine eindeutige MTF-Richtung"
        )

    st.markdown(
        "**🌐 Market Regime Dashboard – gemeinsame Logik**"
    )

    market_asset_preview = st.selectbox(
        "Regime-Asset",
        [
            "Automatisch nach Instrument"
        ]
        + list(
            ASSET_CONFIGS.keys()
        ),
        index=0,
        key="market_asset_override",
        help=(
            "Automatisch = Regime-Asset passend zum gewählten "
            "Futures-/CFD-Instrument. DAX besitzt derzeit kein "
            "eigenes Regime-Modell und kann hier bei Bedarf "
            "manuell überschrieben werden."
        )
    )

    st.caption(
        "Die frühere manuelle AAII-/Fear-&-Greed-/Notenbank-/"
        "Saisonalitätsbewertung entfällt. Der Pilot verwendet "
        "stattdessen die aktuelle sechs-Säulen-Regime-Engine."
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
# 5. AUTOMATISCHER MARKET-REGIME CHECK
# ============================================================

auto_asset = (
    TRADE_PILOT_ASSET_MAP.get(
        market_key
    )
)

if (
    market_asset_preview
    != "Automatisch nach Instrument"
):
    auto_asset = (
        market_asset_preview
    )

with st.spinner(
    "Lade gemeinsame Market-Regime-Daten …"
):
    market_env = (
        fetch_market_environment(
            auto_asset
        )
    )

st.markdown("---")
st.subheader(
    "🌐 Market Regime – gemeinsames Dashboard-Modell"
)

env1, env2, env3, env4 = (
    st.columns(4)
)

with env1:
    st.metric(
        "Asset",
        market_env.get(
            "asset"
        )
        or "n/a"
    )

with env2:
    regime_value = (
        market_env.get(
            "regime_score"
        )
    )

    st.metric(
        "Final Regime Score",
        (
            f"{regime_value:.1f} / 100"
            if regime_value is not None
            else "n/a"
        )
    )

with env3:
    mci_value = (
        market_env.get(
            "mci"
        )
    )

    st.metric(
        "MCI",
        (
            f"{mci_value:.1f}%"
            if mci_value is not None
            else "n/a"
        )
    )

with env4:
    coverage_value = (
        market_env.get(
            "coverage"
        )
    )

    st.metric(
        "Data Coverage",
        (
            f"{coverage_value:.0f}%"
            if coverage_value is not None
            else "n/a"
        )
    )

status = (
    market_env.get(
        "status"
    )
)

if status == "LIVE":
    st.success(
        "🟢 Market Regime: hohe Datenqualität · "
        f"{market_env.get('regime_label', '')}"
    )

elif status == "PARTIAL":
    st.warning(
        "🟡 Market Regime: ausreichend, aber nicht vollständig · "
        f"{market_env.get('regime_label', '')}"
    )

elif status == "LOW_QUALITY":
    st.error(
        "🔴 Market Regime: Datenqualität unter Execution-Schwelle."
    )

elif status == "NOT_MAPPED":
    st.warning(
        "🟠 Für dieses Instrument existiert noch kein eigenes "
        "Dashboard-Regime-Modell. Gear wird konservativ begrenzt."
    )

else:
    st.error(
        "🔴 Market Regime nicht verfügbar – "
        f"{market_env.get('reason', 'unbekannter Fehler')}"
    )

confidence_value = (
    market_env.get(
        "confidence"
    )
)

if confidence_value is not None:
    st.caption(
        "Model Confidence: "
        f"**{confidence_value:.1f}/100** "
        f"{market_env.get('confidence_label', '')}"
    )

with st.expander(
    "📡 Regime-Datenquellen & Datenstände",
    expanded=False
):
    feed_cols = (
        st.columns(2)
    )

    for i, (
        feed,
        live
    ) in enumerate(
        market_env.get(
            "feeds",
            {}
        ).items()
    ):
        date_text = format_feed_date(
            market_env.get(
                "feed_dates",
                {}
            ).get(
                feed
            )
        )

        note = (
            market_env.get(
                "feed_notes",
                {}
            ).get(
                feed,
                ""
            )
        )

        feed_cols[
            i % 2
        ].markdown(
            (
                f"{'🟢' if live else '⚠️'} "
                f"**{feed}** ({date_text})"
                + (
                    f"  \n_{note}_"
                    if note
                    else ""
                )
            )
        )

    st.caption(
        "Die Datenstände und Feed-Status stammen direkt aus "
        "derselben Regime-Engine wie im Market Regime Dashboard."
    )


# ============================================================
# 5A. PRICE CONTEXT & KEY LEVELS
# ============================================================

with st.spinner(
    "Lade Vortages-/Vorwochenlevels & Daily EMAs …"
):
    price_context = (
        fetch_price_context(
            market_key
        )
    )

st.markdown("---")
st.subheader(
    "📍 Price Context & Key Levels"
)

if price_context.get(
    "ok",
    False
):
    pdc = (
        price_context.get(
            "pdc"
        )
    )

    pdh = (
        price_context.get(
            "pdh"
        )
    )

    pdl = (
        price_context.get(
            "pdl"
        )
    )

    pwc = (
        price_context.get(
            "pwc"
        )
    )

    pwh = (
        price_context.get(
            "pwh"
        )
    )

    pwl = (
        price_context.get(
            "pwl"
        )
    )

    ema20 = (
        price_context.get(
            "ema20"
        )
    )

    ema50 = (
        price_context.get(
            "ema50"
        )
    )

    ema200 = (
        price_context.get(
            "ema200"
        )
    )

    # --------------------------------------------------------
    # OPTIONALE EINZEL-OVERRIDES – eToro / MANUELL
    # --------------------------------------------------------

    st.markdown(
        "**✍️ Optionale eToro-/manuelle Overrides**"
    )

    st.caption(
        "Yahoo bleibt Standard. Aktiviere nur die Werte, die du "
        "gezielt mit eToro-/Brokerdaten überschreiben möchtest. "
        "Nicht aktivierte Werte bleiben automatisch."
    )

    with st.expander(
        "eToro-/manuelle Werte eingeben",
        expanded=False
    ):
        st.markdown(
            "##### Vortag"
        )

        ov_pd1, ov_pd2, ov_pd3 = (
            st.columns(3)
        )

        with ov_pd1:
            use_pdc_override = st.checkbox(
                "PDC überschreiben",
                value=False,
                key="override_pdc"
            )

            pdc_manual = st.number_input(
                "PDC manuell",
                value=float(
                    pdc
                    if pdc is not None
                    else 0.0
                ),
                step=0.01,
                format="%.4f",
                key="manual_pdc",
                disabled=not use_pdc_override
            )

        with ov_pd2:
            use_pdh_override = st.checkbox(
                "PDH überschreiben",
                value=False,
                key="override_pdh"
            )

            pdh_manual = st.number_input(
                "PDH manuell",
                value=float(
                    pdh
                    if pdh is not None
                    else 0.0
                ),
                step=0.01,
                format="%.4f",
                key="manual_pdh",
                disabled=not use_pdh_override
            )

        with ov_pd3:
            use_pdl_override = st.checkbox(
                "PDL überschreiben",
                value=False,
                key="override_pdl"
            )

            pdl_manual = st.number_input(
                "PDL manuell",
                value=float(
                    pdl
                    if pdl is not None
                    else 0.0
                ),
                step=0.01,
                format="%.4f",
                key="manual_pdl",
                disabled=not use_pdl_override
            )

        st.markdown(
            "##### Vorwoche"
        )

        ov_pw1, ov_pw2, ov_pw3 = (
            st.columns(3)
        )

        with ov_pw1:
            use_pwc_override = st.checkbox(
                "PWC überschreiben",
                value=False,
                key="override_pwc"
            )

            pwc_manual = st.number_input(
                "PWC manuell",
                value=float(
                    pwc
                    if pwc is not None
                    else 0.0
                ),
                step=0.01,
                format="%.4f",
                key="manual_pwc",
                disabled=not use_pwc_override
            )

        with ov_pw2:
            use_pwh_override = st.checkbox(
                "PWH überschreiben",
                value=False,
                key="override_pwh"
            )

            pwh_manual = st.number_input(
                "PWH manuell",
                value=float(
                    pwh
                    if pwh is not None
                    else 0.0
                ),
                step=0.01,
                format="%.4f",
                key="manual_pwh",
                disabled=not use_pwh_override
            )

        with ov_pw3:
            use_pwl_override = st.checkbox(
                "PWL überschreiben",
                value=False,
                key="override_pwl"
            )

            pwl_manual = st.number_input(
                "PWL manuell",
                value=float(
                    pwl
                    if pwl is not None
                    else 0.0
                ),
                step=0.01,
                format="%.4f",
                key="manual_pwl",
                disabled=not use_pwl_override
            )

        st.markdown(
            "##### Daily EMAs"
        )

        st.caption(
            "Bitte bei manueller Eingabe die Daily-EMA-Werte aus "
            "dem eToro-Chart verwenden, damit sie mit dem automatischen "
            "Daily-Kontext vergleichbar bleiben."
        )

        ov_em1, ov_em2, ov_em3 = (
            st.columns(3)
        )

        with ov_em1:
            use_ema20_override = st.checkbox(
                "EMA20 überschreiben",
                value=False,
                key="override_ema20"
            )

            ema20_manual = st.number_input(
                "Daily EMA20 manuell",
                value=float(
                    ema20
                    if ema20 is not None
                    else 0.0
                ),
                step=0.01,
                format="%.4f",
                key="manual_ema20",
                disabled=not use_ema20_override
            )

        with ov_em2:
            use_ema50_override = st.checkbox(
                "EMA50 überschreiben",
                value=False,
                key="override_ema50"
            )

            ema50_manual = st.number_input(
                "Daily EMA50 manuell",
                value=float(
                    ema50
                    if ema50 is not None
                    else 0.0
                ),
                step=0.01,
                format="%.4f",
                key="manual_ema50",
                disabled=not use_ema50_override
            )

        with ov_em3:
            use_ema200_override = st.checkbox(
                "EMA200 überschreiben",
                value=False,
                key="override_ema200"
            )

            ema200_manual = st.number_input(
                "Daily EMA200 manuell",
                value=float(
                    ema200
                    if ema200 is not None
                    else 0.0
                ),
                step=0.01,
                format="%.4f",
                key="manual_ema200",
                disabled=not use_ema200_override
            )

    # Effektive Werte festlegen.
    pdc, pdc_source = _resolve_manual_override(
        pdc,
        use_pdc_override,
        pdc_manual
    )

    pdh, pdh_source = _resolve_manual_override(
        pdh,
        use_pdh_override,
        pdh_manual
    )

    pdl, pdl_source = _resolve_manual_override(
        pdl,
        use_pdl_override,
        pdl_manual
    )

    pwc, pwc_source = _resolve_manual_override(
        pwc,
        use_pwc_override,
        pwc_manual
    )

    pwh, pwh_source = _resolve_manual_override(
        pwh,
        use_pwh_override,
        pwh_manual
    )

    pwl, pwl_source = _resolve_manual_override(
        pwl,
        use_pwl_override,
        pwl_manual
    )

    ema20, ema20_source = _resolve_manual_override(
        ema20,
        use_ema20_override,
        ema20_manual
    )

    ema50, ema50_source = _resolve_manual_override(
        ema50,
        use_ema50_override,
        ema50_manual
    )

    ema200, ema200_source = _resolve_manual_override(
        ema200,
        use_ema200_override,
        ema200_manual
    )

    # --------------------------------------------------------
    # LEVELS – VORTAG
    # --------------------------------------------------------

    st.markdown(
        "**Vortag**"
    )

    pd1, pd2, pd3, pd4 = (
        st.columns(4)
    )

    pd1.metric(
        "PDC · Close",
        _format_level(
            pdc
        )
    )

    pd2.metric(
        "PDH · High",
        _format_level(
            pdh
        )
    )

    pd3.metric(
        "PDL · Low",
        _format_level(
            pdl
        )
    )

    day_position = (
        _range_position(
            entry_price,
            pdl,
            pdh
        )
    )

    pd4.metric(
        "Entry in Vortagesrange",
        (
            f"{day_position:.0f}%"
            if day_position is not None
            else "n/a"
        )
    )

    st.caption(
        "Vortages-Datenstand: "
        f"**{_format_context_date(price_context.get('previous_day_date'))}** · "
        f"PDC: **{pdc_source}** · "
        f"PDH: **{pdh_source}** · "
        f"PDL: **{pdl_source}**"
    )

    # --------------------------------------------------------
    # LEVELS – VORWOCHE
    # --------------------------------------------------------

    st.markdown(
        "**Vorwoche**"
    )

    pw1, pw2, pw3, pw4 = (
        st.columns(4)
    )

    pw1.metric(
        "PWC · Close",
        _format_level(
            pwc
        )
    )

    pw2.metric(
        "PWH · High",
        _format_level(
            pwh
        )
    )

    pw3.metric(
        "PWL · Low",
        _format_level(
            pwl
        )
    )

    week_position = (
        _range_position(
            entry_price,
            pwl,
            pwh
        )
    )

    pw4.metric(
        "Entry in Vorwochenrange",
        (
            f"{week_position:.0f}%"
            if week_position is not None
            else "n/a"
        )
    )

    st.caption(
        "Vorwochen-Datenstand: "
        f"**{_format_context_date(price_context.get('previous_week_date'))}** · "
        f"PWC: **{pwc_source}** · "
        f"PWH: **{pwh_source}** · "
        f"PWL: **{pwl_source}**"
    )

    # --------------------------------------------------------
    # DAILY EMAs
    # --------------------------------------------------------

    st.markdown(
        "**Daily EMA Context**"
    )

    em1, em2, em3, em4 = (
        st.columns(4)
    )

    em1.metric(
        "EMA 20",
        _format_level(
            ema20
        ),
        (
            f"Entry {entry_price - ema20:+,.2f}"
            if ema20 is not None
            else None
        )
    )

    em2.metric(
        "EMA 50",
        _format_level(
            ema50
        ),
        (
            f"Entry {entry_price - ema50:+,.2f}"
            if ema50 is not None
            else None
        )
    )

    em3.metric(
        "EMA 200",
        _format_level(
            ema200
        ),
        (
            f"Entry {entry_price - ema200:+,.2f}"
            if ema200 is not None
            else None
        )
    )

    if (
        ema20 is not None
        and ema50 is not None
        and ema200 is not None
    ):
        if (
            ema20
            > ema50
            > ema200
        ):
            ema_structure = (
                "🟢 Bullisch"
            )

        elif (
            ema20
            < ema50
            < ema200
        ):
            ema_structure = (
                "🔴 Bärisch"
            )

        else:
            ema_structure = (
                "🟡 Gemischt"
            )

    else:
        ema_structure = (
            "⚪ Unvollständig"
        )

    em4.metric(
        "EMA-Struktur",
        ema_structure
    )

    st.caption(
        "EMA-Datenstand der Yahoo-Automatik: "
        f"**{_format_context_date(price_context.get('ema_date'))}** · "
        f"EMA20: **{ema20_source}** · "
        f"EMA50: **{ema50_source}** · "
        f"EMA200: **{ema200_source}**"
    )

    # --------------------------------------------------------
    # ENTRY / STOP / TARGET – KONTEXT
    # --------------------------------------------------------

    st.markdown(
        "**Entry / Stop / Target Kontext**"
    )

    context_messages = []

    if (
        pdh is not None
        and pdl is not None
    ):
        if entry_price > pdh:
            context_messages.append(
                "Entry liegt **oberhalb des Vortageshochs (PDH)**."
            )

        elif entry_price < pdl:
            context_messages.append(
                "Entry liegt **unterhalb des Vortagestiefs (PDL)**."
            )

        elif entry_price >= pdc:
            context_messages.append(
                "Entry liegt innerhalb der Vortagesrange "
                "**oberhalb des Vortagesschlusses (PDC)**."
            )

        else:
            context_messages.append(
                "Entry liegt innerhalb der Vortagesrange "
                "**unterhalb des Vortagesschlusses (PDC)**."
            )

    if (
        pwh is not None
        and pwl is not None
    ):
        if entry_price > pwh:
            context_messages.append(
                "Entry liegt **oberhalb des Vorwochenhochs (PWH)**."
            )

        elif entry_price < pwl:
            context_messages.append(
                "Entry liegt **unterhalb des Vorwochentiefs (PWL)**."
            )

        else:
            context_messages.append(
                "Entry liegt **innerhalb der Vorwochenspanne**."
            )

    # Informative Cross-Level Checks – keine Blocker.
    crossed_levels = []

    levels_for_target = {
        "PDH": pdh,
        "PDL": pdl,
        "PWH": pwh,
        "PWL": pwl,
        "EMA20": ema20,
        "EMA50": ema50,
        "EMA200": ema200,
    }

    if direction == "Long":
        for level_name, level_value in (
            levels_for_target.items()
        ):
            if (
                level_value is not None
                and entry_price
                < level_value
                <= target_price
            ):
                crossed_levels.append(
                    level_name
                )

    else:
        for level_name, level_value in (
            levels_for_target.items()
        ):
            if (
                level_value is not None
                and target_price
                <= level_value
                < entry_price
            ):
                crossed_levels.append(
                    level_name
                )

    for msg in context_messages:
        st.write(
            f"• {msg}"
        )

    if crossed_levels:
        st.warning(
            "⚠️ Auf dem Weg vom Entry zum Target liegen folgende "
            "Referenzlevels: "
            f"**{', '.join(crossed_levels)}**. "
            "Das ist kein automatischer Blocker, sollte aber "
            "charttechnisch geprüft werden."
        )

    # Stop location relative to previous range.
    if direction == "Long":
        stop_refs = []

        if (
            pdl is not None
            and stop_price < pdl
        ):
            stop_refs.append(
                "unter PDL"
            )

        if (
            pwl is not None
            and stop_price < pwl
        ):
            stop_refs.append(
                "unter PWL"
            )

    else:
        stop_refs = []

        if (
            pdh is not None
            and stop_price > pdh
        ):
            stop_refs.append(
                "über PDH"
            )

        if (
            pwh is not None
            and stop_price > pwh
        ):
            stop_refs.append(
                "über PWH"
            )

    if stop_refs:
        st.info(
            "ℹ️ Stop-Lage: "
            f"**{', '.join(stop_refs)}**."
        )

    # --------------------------------------------------------
    # OVERRIDE-ZUSAMMENFASSUNG
    # --------------------------------------------------------

    active_overrides = []

    for override_name, override_source in [
        ("PDC", pdc_source),
        ("PDH", pdh_source),
        ("PDL", pdl_source),
        ("PWC", pwc_source),
        ("PWH", pwh_source),
        ("PWL", pwl_source),
        ("EMA20", ema20_source),
        ("EMA50", ema50_source),
        ("EMA200", ema200_source),
    ]:
        if override_source == "eToro / manuell":
            active_overrides.append(
                override_name
            )

    if active_overrides:
        st.info(
            "✍️ Aktive manuelle/eToro-Overrides: "
            f"**{', '.join(active_overrides)}**. "
            "Alle übrigen Werte bleiben Yahoo-automatisch."
        )
    else:
        st.caption(
            "Keine manuellen Overrides aktiv – "
            "alle Price-Context-Werte stammen aus der Yahoo-Automatik."
        )

    # --------------------------------------------------------
    # SOURCE / DATA QUALITY
    # --------------------------------------------------------

    source_text = (
        price_context.get(
            "source_label",
            "Yahoo"
        )
    )

    source_ticker = (
        price_context.get(
            "ticker",
            "n/a"
        )
    )

    reference_price = (
        price_context.get(
            "reference_price"
        )
    )

    reference_date = (
        price_context.get(
            "reference_date"
        )
    )

    st.caption(
        f"Quelle: **{source_text}** · Ticker `{source_ticker}` · "
        "letzter Yahoo-Referenzkurs: "
        f"**{_format_level(reference_price)}** "
        f"({_format_context_date(reference_date)})."
    )

    if price_context.get(
        "proxy",
        False
    ):
        st.caption(
            "⚠️ Referenzhinweis: Der Yahoo-Preis ist bei diesem "
            "Instrument ein Proxy. Broker-CFD-/Micro-/DAX-Future-"
            "Sessionlevels können geringfügig abweichen."
        )

else:
    st.warning(
        "⚠️ Price Context aktuell nicht verfügbar: "
        f"{price_context.get('reason', 'unbekannter Fehler')}"
    )

st.caption(
    "PDH/PDL/PDC sowie PWH/PWL/PWC und EMA20/50/200 sind "
    "reine Execution-/Kontextinformationen. Yahoo ist die automatische "
    "Standardquelle; einzelne Werte können optional durch eToro/manuell "
    "überschrieben werden. Sie verändern weder den Final Regime Score "
    "noch automatisch Gear oder Trade-Freigabe."
)


# ============================================================
# 6. GEAR ENGINE – MTF + GEMEINSAMES REGIME
# ============================================================

# ------------------------------------------------------------
# MTF STRUKTUR
# ------------------------------------------------------------

trend_points = sum(
    1.0
    if t == "Trend"
    else (
        0.5
        if t == "Korrektur"
        else 0.0
    )
    for t in [
        t240,
        t60,
        t15
    ]
)

directions = [
    d240,
    d60,
    d15
]

long_count = (
    directions.count(
        "Long"
    )
)

short_count = (
    directions.count(
        "Short"
    )
)

neutral_count = (
    directions.count(
        "Neutral"
    )
)

if long_count > short_count:
    dominant_direction = "Long"
elif short_count > long_count:
    dominant_direction = "Short"
else:
    dominant_direction = "Neutral"

dominant_count = max(
    long_count,
    short_count
)

if dominant_direction != "Neutral":
    if dominant_count == 3:
        direction_points = 1.0
    elif dominant_count == 2:
        direction_points = 0.5
    else:
        direction_points = 0.0
else:
    direction_points = 0.0

mtf_points = (
    trend_points
    + direction_points
)

# ------------------------------------------------------------
# DASHBOARD REGIME – RICHTUNGSABHÄNGIG
# ------------------------------------------------------------
#
# Final Regime Score:
#   hoch  -> unterstützt Long
#   niedrig -> unterstützt Short
#
# Deshalb darf ein starkes Risk-Off-Regime einen Short-Trade
# nicht bestrafen.

regime_score = (
    market_env.get(
        "regime_score"
    )
)

if regime_score is not None:
    if direction == "Long":
        supportive_regime_score = (
            regime_score
        )
    else:
        supportive_regime_score = (
            100.0
            - regime_score
        )

    market_env_points = (
        supportive_regime_score
        / 100.0
        * 3.0
    )
else:
    supportive_regime_score = None
    market_env_points = 0.0

# ------------------------------------------------------------
# TRADER PENALTIES
# ------------------------------------------------------------

penalties = 0.0

if trader_stress == "Mittel":
    penalties += 0.5
elif trader_stress == "Hoch":
    penalties += 1.5

if location != "Home Office":
    penalties += 0.5

total_score = max(
    0.0,
    mtf_points
    + market_env_points
    - penalties
)

# ------------------------------------------------------------
# KONFLIKTE
# ------------------------------------------------------------

mtf_direction_conflict = (
    d240 != "Neutral"
    and d60 != "Neutral"
    and d240 != d60
)

entry_direction_conflict = (
    (
        direction == "Long"
        and dominant_direction == "Short"
    )
    or
    (
        direction == "Short"
        and dominant_direction == "Long"
    )
)

regime_direction_conflict = False

if regime_score is not None:
    if (
        direction == "Long"
        and regime_score <= 40
    ):
        regime_direction_conflict = True

    elif (
        direction == "Short"
        and regime_score >= 60
    ):
        regime_direction_conflict = True


# ------------------------------------------------------------
# GEAR-KLASSIFIZIERUNG
# ------------------------------------------------------------

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
# 7. DATA QUALITY / GEAR SAFETY CAP
# ============================================================

env_status = (
    market_env.get(
        "status"
    )
)

if env_status == "LIVE":
    data_quality_cap = 5

elif env_status == "PARTIAL":
    data_quality_cap = 3

elif env_status == "NOT_MAPPED":
    # DAX usw.: kein erfundener neutraler Regime-Wert.
    # MTF darf weiterhin handeln, aber nicht aggressiv.
    data_quality_cap = 3

elif env_status == "LOW_QUALITY":
    data_quality_cap = 2

else:
    data_quality_cap = 1


def apply_gear_parameters(target_gear):
    if target_gear <= 1:
        return (
            1,
            0.0,
            0.0,
            None,
            None,
            "N/A"
        )

    if target_gear == 2:
        return (
            2,
            1.2,
            0.50,
            2.0,
            4.0,
            "Ja – frühzeitige Skalierung"
        )

    if target_gear == 3:
        return (
            3,
            1.5,
            0.75,
            1.5,
            4.0,
            "Ja – Teilgewinn ab 1.5R"
        )

    if target_gear == 4:
        return (
            4,
            1.8,
            0.90,
            1.5,
            2.5,
            "Optional ab 2.0R"
        )

    return (
        5,
        2.0,
        1.00,
        1.0,
        2.0,
        "Nein – Gewinner voll ausreizen"
    )


if gear > data_quality_cap:
    (
        gear,
        min_rrr_req,
        risk_mult,
        stop_min_atr,
        stop_max_atr,
        scale_out
    ) = apply_gear_parameters(
        data_quality_cap
    )


# ============================================================
# 8. PRE-CALCULATION
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

        # Micro-Kontrakte besitzen eigene Broker-/Börsengebühren.
        # Die Kommission darf nicht proportional zum Tickwert
        # des Hauptkontrakts heruntergerechnet werden.
        micro_comm_used_native = float(
            micro_spec["default_comm_roundturn"]
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

if entry_direction_conflict:
    primary_blockers.append((
        "🔴 MTF-Richtung widerspricht Trade",
        f"Trade {direction} widerspricht der dominanten MTF-Richtung {dominant_direction}."
    ))

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

if market_env["status"] in (
    "UNAVAILABLE",
    "LOW_QUALITY"
):
    primary_blockers.append((
        "🔴 Market-Regime Datenqualität unzureichend",
        (
            "Das gemeinsame Dashboard-Modell unterschreitet "
            "die Execution-Schwelle oder ist nicht verfügbar."
        )
    ))

if regime_direction_conflict:
    primary_blockers.append((
        "🔴 Trade widerspricht dem übergeordneten Regime",
        (
            f"Geplante Richtung {direction}; "
            f"Final Regime Score {regime_score:.1f}/100 "
            f"({market_env.get('regime_label', '')})."
        )
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
# 17. MARKET-REGIME / MTF BREAKDOWN
# ============================================================

st.markdown("---")
st.subheader(
    "📊 Market-Regime & MTF Breakdown"
)

b1, b2, b3 = (
    st.columns(3)
)

b1.metric(
    "Makroökonomie",
    (
        f"{market_env['macro_score']:.1f}"
        if market_env.get(
            "macro_score"
        ) is not None
        else "n/a"
    )
)

b2.metric(
    "Positionierung",
    (
        f"{market_env['positioning_score']:.1f}"
        if market_env.get(
            "positioning_score"
        ) is not None
        else "n/a"
    )
)

b3.metric(
    "Technischer Trend",
    (
        f"{market_env['technical_score']:.1f}"
        if market_env.get(
            "technical_score"
        ) is not None
        else "n/a"
    )
)

b4, b5, b6 = (
    st.columns(3)
)

b4.metric(
    "Marktinterna",
    (
        f"{market_env['internals_score']:.1f}"
        if market_env.get(
            "internals_score"
        ) is not None
        else "n/a"
    )
)

b5.metric(
    "Fundamental",
    (
        f"{market_env['fundamental_score']:.1f}"
        if market_env.get(
            "fundamental_score"
        ) is not None
        else "n/a"
    )
)

b6.metric(
    "Frühwarnindikatoren",
    (
        f"{market_env['early_warning_score']:.1f}"
        if market_env.get(
            "early_warning_score"
        ) is not None
        else "n/a"
    )
)

st.write(
    f"**MTF-Strukturpunkte:** "
    f"{trend_points:.2f} / 3.00"
)

st.write(
    f"**MTF-Richtungskonsistenz:** "
    f"{direction_points:.2f} / 1.00"
)

st.write(
    f"**MTF-Gesamtpunkte:** "
    f"{mtf_points:.2f} / 4.00"
)

st.write(
    "**Regime-Unterstützung für geplante "
    f"{direction}-Richtung:** "
    + (
        f"{supportive_regime_score:.1f}/100 "
        f"→ {market_env_points:.2f} / 3.00 Punkte"
        if supportive_regime_score is not None
        else "n/a"
    )
)

st.write(
    f"**Trader-Penalties:** "
    f"{penalties:.2f}"
)

if mtf_direction_conflict:
    st.warning(
        "⚠️ 4H und 1H zeigen unterschiedliche Richtungen. "
        "Das kann eine Korrekturphase darstellen und ist "
        "nicht automatisch ein Hard Stop."
    )


# ============================================================
# 18. DREI-EBENEN-CHECK
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
            f"Micro-Kommission: "
            f"**{micro_comm_used_native:.2f} "
            f"{FUTURES[micro_key_found]['currency']} R/T**"
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
    if net_rrr < min_rrr_req and final_contracts > 0:
        required_net_reward_eur = min_rrr_req * net_risk_eur
        required_gross_reward_eur = (
            required_net_reward_eur + total_costs_eur
        )

        # Sicherheitsprüfung: CFD-Datenbank nur im CFD-Pfad.
        if product_type == "CFD":
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

            reward_points_needed = (
                required_gross_reward_eur
                / (reward_value_per_unit_eur * final_contracts)
            )

        else:
            active_future = (
                micro_key_found if micro_active else market_key
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
                value_per_point_native / fx_conv_path
            )

            reward_points_needed = (
                required_gross_reward_eur
                / (value_per_point_eur * final_contracts)
            )

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
    # PFAD B – STOP / ATR
    # --------------------------------------------------------
    if (
        not atr_ok
        and atr_val > 0
        and stop_atr_ratio is not None
        and stop_min_atr is not None
        and stop_max_atr is not None
    ):
        if stop_atr_ratio < stop_min_atr:
            suggested_stop_distance = (
                atr_val
                * stop_min_atr
            )

            s_suggest = (
                entry_price
                - suggested_stop_distance
                if direction == "Long"
                else entry_price
                + suggested_stop_distance
            )

            st.write(
                f"• **Pfad B – Stop erweitern:** "
                f"Aktueller Stop {stop_atr_ratio:.2f}x ATR "
                f"liegt unter dem Minimum von "
                f"{stop_min_atr:.2f}x ATR. "
                f"Mindestens **{suggested_stop_distance:,.2f} Punkte** "
                f"(Stop bei **{s_suggest:,.2f}**)."
            )

        elif stop_atr_ratio > stop_max_atr:
            suggested_stop_distance = (
                atr_val
                * stop_max_atr
            )

            s_suggest = (
                entry_price
                - suggested_stop_distance
                if direction == "Long"
                else entry_price
                + suggested_stop_distance
            )

            st.write(
                f"• **Pfad B – Stop reduzieren:** "
                f"Aktueller Stop {stop_atr_ratio:.2f}x ATR "
                f"liegt über dem Maximum von "
                f"{stop_max_atr:.2f}x ATR. "
                f"Maximal **{suggested_stop_distance:,.2f} Punkte** "
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

    st.write(
        "• **Pfad D – Trade verworfen:** "
        "Setup ablehnen und auf ein regelkonformes Umfeld warten."
    )

else:
    st.success(
        "🟢 Das Setup entspricht sämtlichen quantitativen Vorgaben. "
        "Keinerlei Anpassung notwendig."
    )


# ============================================================
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
    "Hinweis: v3.1 Trade Pilot ist ein rein quantitatives Decision Gate. "
    "Spread-, Overnight-, Kommissions- und Marginwerte sind "
    "Planungsannahmen und keine Echtzeit-Brokerdaten. "
    "Sie müssen regelmäßig gegen die tatsächlichen Brokerbedingungen "
    "validiert werden. Keine Anlageberatung."
)
