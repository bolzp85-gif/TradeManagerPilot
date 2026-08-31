import streamlit as st
import math
import io
import zipfile
import requests
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

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
    page_title="Trade Manager & Decision Cockpit v3.5.4 Fused Checked",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ Trade Manager & Decision Cockpit v3.5.4 Fused Checked")
st.caption(
    "Systematisches Decision-Gate – Market-Regime-Engine + MTF + "
    "Price Context + offizieller Economic-News-Warnfilter + "
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
    FRED_API_KEY,
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



# ============================================================
# OFFICIAL ECONOMIC EVENT RISK ENGINE
# ============================================================
#
# Kostenfreie offizielle Quellen:
# - BLS      : CPI, PPI, NFP / Employment Situation, JOLTS, ECI
# - BEA      : PCE / Personal Income & Outlays, GDP
# - Federal Reserve : FOMC-Zinsentscheid + Pressekonferenz
# - EIA      : Weekly Petroleum Status Report / Crude Inventories
# - ECB      : Geldpolitischer Beschluss + Pressekonferenz
# - Destatis : deutscher CPI (vorläufig) + deutsches BIP
#
# Ziel:
# - Termin + Uhrzeit anzeigen
# - auf Europe/Berlin umrechnen
# - automatische Execution-Sperre im definierten Zeitfenster
#
# WICHTIG:
# Dies ist bewusst KEIN vollständiger weltweiter Wirtschaftskalender.
# Investing.com / baha bleiben als manueller Kontrollcheck sinnvoll.
# ============================================================

BERLIN_TZ = ZoneInfo(
    "Europe/Berlin"
)

NEW_YORK_TZ = ZoneInfo(
    "America/New_York"
)

UTC_TZ = ZoneInfo(
    "UTC"
)

NEWS_BLOCK_BEFORE_MIN = 30
NEWS_BLOCK_AFTER_MIN = 15
NEWS_LOOKAHEAD_DAYS = 7

OFFICIAL_NEWS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/131 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml,"
        "text/calendar;q=0.9,*/*;q=0.8"
    )
}

OFFICIAL_NEWS_URLS = {
    "BLS": (
        "https://www.bls.gov/schedule/news_release/bls.ics"
    ),
    "BLS_EMPSIT": (
        "https://www.bls.gov/schedule/news_release/empsit.htm"
    ),
    "BLS_CPI": (
        "https://www.bls.gov/schedule/news_release/cpi.htm"
    ),
    "BLS_PPI": (
        "https://www.bls.gov/schedule/news_release/ppi.htm"
    ),
    "BLS_JOLTS": (
        "https://www.bls.gov/schedule/news_release/jolts.htm"
    ),
    "BLS_ECI": (
        "https://www.bls.gov/schedule/news_release/eci.htm"
    ),
    "FRED_RELEASE_DATES_API": (
        "https://api.stlouisfed.org/fred/release/dates"
    ),
    "FRED_RELEASE_CALENDAR": (
        "https://fred.stlouisfed.org/releases/calendar"
    ),
    "BEA": (
        "https://www.bea.gov/news/schedule"
    ),
    "FED": (
        "https://www.federalreserve.gov/monetarypolicy/"
        "fomccalendars.htm"
    ),
    "EIA": (
        "https://www.eia.gov/petroleum/supply/weekly/"
        "schedule.php"
    ),
    "ECB": (
        "https://www.ecb.europa.eu/press/calendars/"
        "mgcgc/html/index.en.html"
    ),
    "DESTATIS_CPI": (
        "https://www.destatis.de/SiteGlobals/Forms/Suche/"
        "Termine/DE/Terminsuche_Formular.html"
        "?templateQueryString=verbraucherpreisindex"
    ),
    "DESTATIS_GDP": (
        "https://www.destatis.de/SiteGlobals/Forms/Suche/"
        "Termine/DE/Terminsuche_Formular.html"
        "?templateQueryString=bruttoinlandsprodukt"
    ),
    "INVESTING": (
        "https://de.investing.com/economic-calendar"
    ),
    "BAHA": (
        "https://www.baha.com/economic-calendar"
    ),
}


def _news_market_is_oil(
    market_key
):
    return market_key in {
        "CL (Crude Oil)",
        "MCL (Micro Oil)",
        "Oil CFD",
    }


def _news_market_is_dax(
    market_key
):
    return market_key in {
        "FDAX (DAX Future)",
        "FDXM (Mini DAX)",
        "GER40 CFD",
    }


def _event_dict(
    title,
    event_dt,
    source,
    url,
    region,
    category
):
    if event_dt.tzinfo is None:
        raise ValueError(
            "event_dt must be timezone-aware"
        )

    event_berlin = (
        event_dt.astimezone(
            BERLIN_TZ
        )
    )

    return {
        "title": str(
            title
        ).strip(),
        "time": event_berlin,
        "source": str(
            source
        ),
        "url": str(
            url
        ),
        "region": str(
            region
        ),
        "category": str(
            category
        ),
        "impact": "High",
    }


def _clean_ics_value(
    value
):
    return (
        str(value)
        .replace(
            r"\,",
            ","
        )
        .replace(
            r"\;",
            ";"
        )
        .replace(
            r"\n",
            " "
        )
        .replace(
            r"\\",
            "\\"
        )
        .strip()
    )


def _unfold_ics_lines(
    text_value
):
    raw_lines = (
        str(text_value)
        .replace(
            "\r\n",
            "\n"
        )
        .replace(
            "\r",
            "\n"
        )
        .split(
            "\n"
        )
    )

    lines = []

    for line in raw_lines:
        if (
            lines
            and line.startswith(
                (
                    " ",
                    "\t"
                )
            )
        ):
            lines[-1] += (
                line[1:]
            )
        else:
            lines.append(
                line
            )

    return lines


def _parse_ics_dtstart(
    key,
    value
):
    """
    Unterstützt u.a.
    DTSTART;TZID=America/New_York:20260904T083000
    DTSTART:20260904T123000Z
    DTSTART;VALUE=DATE:20260904
    """
    value = (
        str(value)
        .strip()
    )

    key_parts = (
        str(key)
        .split(
            ";"
        )
    )

    params = {}

    for part in key_parts[1:]:
        if "=" in part:
            p_key, p_val = (
                part.split(
                    "=",
                    1
                )
            )

            params[
                p_key.upper()
            ] = p_val

    if (
        params.get(
            "VALUE",
            ""
        ).upper()
        == "DATE"
    ):
        dt = datetime.strptime(
            value,
            "%Y%m%d"
        )

        # Ganztagstermine sind für unsere BLS-High-Impact-
        # Releases normalerweise nicht relevant.
        return dt.replace(
            tzinfo=NEW_YORK_TZ
        )

    if value.endswith(
        "Z"
    ):
        dt = datetime.strptime(
            value,
            "%Y%m%dT%H%M%SZ"
        )

        return dt.replace(
            tzinfo=UTC_TZ
        )

    fmt = (
        "%Y%m%dT%H%M%S"
        if len(value) >= 15
        else "%Y%m%dT%H%M"
    )

    dt = datetime.strptime(
        value,
        fmt
    )

    tz_name = params.get(
        "TZID"
    )

    if tz_name:
        try:
            tz = ZoneInfo(
                tz_name
            )
        except Exception:
            tz = NEW_YORK_TZ
    else:
        tz = NEW_YORK_TZ

    return dt.replace(
        tzinfo=tz
    )


def _dedupe_events(
    events
):
    unique = {}
    for event in events:
        key = (
            event[
                "title"
            ].lower(),
            event[
                "time"
            ].isoformat()
        )
        unique[
            key
        ] = event

    return sorted(
        unique.values(),
        key=lambda x: x[
            "time"
        ]
    )


def _event_within_horizon(
    event_dt,
    start_dt,
    end_dt
):
    return (
        start_dt
        <= event_dt
        <= end_dt
    )


# ------------------------------------------------------------
# BLS
# ------------------------------------------------------------

BLS_HIGH_IMPACT_MAP = {
    "employment situation": (
        "US Employment Situation / NFP"
    ),
    "consumer price index": (
        "US Consumer Price Index (CPI)"
    ),
    "producer price index": (
        "US Producer Price Index (PPI)"
    ),
    "job openings and labor turnover survey": (
        "US JOLTS"
    ),
    "employment cost index": (
        "US Employment Cost Index"
    ),
}


BLS_HTML_RELEASES = [
    (
        "BLS_EMPSIT",
        "US Employment Situation / NFP"
    ),
    (
        "BLS_CPI",
        "US Consumer Price Index (CPI)"
    ),
    (
        "BLS_PPI",
        "US Producer Price Index (PPI)"
    ),
    (
        "BLS_JOLTS",
        "US JOLTS"
    ),
    (
        "BLS_ECI",
        "US Employment Cost Index"
    ),
]


# FRED release IDs for the same BLS releases.
# FRED's release calendar shows these releases in US Central Time.
# We create the event in America/New_York using the equivalent
# official ET publication time so DST conversion to Europe/Berlin
# remains automatic and correct.
FRED_BLS_RELEASES = [
    {
        "release_id": 50,
        "title": "US Employment Situation / NFP",
        "hour_et": 8,
        "minute_et": 30,
    },
    {
        "release_id": 10,
        "title": "US Consumer Price Index (CPI)",
        "hour_et": 8,
        "minute_et": 30,
    },
    {
        "release_id": 46,
        "title": "US Producer Price Index (PPI)",
        "hour_et": 8,
        "minute_et": 30,
    },
    {
        "release_id": 192,
        "title": "US JOLTS",
        "hour_et": 10,
        "minute_et": 0,
    },
    {
        "release_id": 11,
        "title": "US Employment Cost Index",
        "hour_et": 8,
        "minute_et": 30,
    },
]


@st.cache_data(
    ttl=21600,
    show_spinner=False
)
def fetch_fred_bls_release_events():
    """
    Sekundärer BLS-Terminfeed über die offizielle FRED API.

    Die FRED API stellt mit
    include_release_dates_with_no_data=true
    auch zukünftige, bereits im Release Calendar angekündigte
    Veröffentlichungstermine bereit.

    Voraussetzung:
        derselbe FRED_API_KEY wie in regime_engine.py.
    """
    if not FRED_API_KEY:
        return (
            [],
            False,
            (
                "FRED-BLS-Fallback nicht verfügbar: "
                "FRED_API_KEY fehlt."
            )
        )

    events = []
    successful_releases = 0
    errors = []

    now_berlin = datetime.now(
        BERLIN_TZ
    )

    # Wir brauchen nur Termine rund um den aktuellen Zeitraum.
    # Die API liefert die Release-Historie; die Zeitfilterung erfolgt
    # anschließend lokal auf einen großzügigen Zeitraum.
    local_start_date = (
        now_berlin.date()
        - timedelta(
            days=45
        )
    )

    local_end_date = (
        now_berlin.date()
        + timedelta(
            days=400
        )
    )

    for cfg in FRED_BLS_RELEASES:
        release_id = int(
            cfg[
                "release_id"
            ]
        )

        try:
            response = requests.get(
                OFFICIAL_NEWS_URLS[
                    "FRED_RELEASE_DATES_API"
                ],
                params={
                    "release_id": release_id,
                    "api_key": FRED_API_KEY,
                    "file_type": "json",
                    "include_release_dates_with_no_data": "true",
                    "sort_order": "asc",
                    "limit": 1000,
                },
                headers=OFFICIAL_NEWS_HEADERS,
                timeout=15
            )

            response.raise_for_status()

            payload = (
                response.json()
            )

            release_dates = (
                payload.get(
                    "release_dates",
                    []
                )
            )

            if not isinstance(
                release_dates,
                list
            ):
                release_dates = []

            successful_releases += 1

            for item in release_dates:
                date_text = str(
                    item.get(
                        "date",
                        ""
                    )
                ).strip()

                if not date_text:
                    continue

                try:
                    release_date = (
                        datetime.strptime(
                            date_text,
                            "%Y-%m-%d"
                        )
                        .date()
                    )
                except Exception:
                    continue

                if not (
                    local_start_date
                    <= release_date
                    <= local_end_date
                ):
                    continue

                event_dt = datetime(
                    release_date.year,
                    release_date.month,
                    release_date.day,
                    int(
                        cfg[
                            "hour_et"
                        ]
                    ),
                    int(
                        cfg[
                            "minute_et"
                        ]
                    ),
                    tzinfo=NEW_YORK_TZ
                )

                events.append(
                    _event_dict(
                        cfg[
                            "title"
                        ],
                        event_dt,
                        "FRED / BLS Release Calendar",
                        (
                            OFFICIAL_NEWS_URLS[
                                "FRED_RELEASE_CALENDAR"
                            ]
                            + f"?rid={release_id}"
                        ),
                        "USA",
                        "US Macro"
                    )
                )

        except Exception as exc:
            errors.append(
                (
                    f"Release {release_id}: "
                    f"{type(exc).__name__} "
                    f"{str(exc)[:80]}"
                )
            )

    events = (
        _dedupe_events(
            events
        )
    )

    if (
        successful_releases
        == len(
            FRED_BLS_RELEASES
        )
        and events
    ):
        return (
            events,
            True,
            (
                "FRED Release Calendar Fallback aktiv "
                f"({successful_releases}/{len(FRED_BLS_RELEASES)} "
                "BLS-Releases geladen)"
            )
        )

    if (
        successful_releases > 0
        and events
    ):
        return (
            events,
            False,
            (
                "FRED Release Calendar Fallback teilweise aktiv "
                f"({successful_releases}/{len(FRED_BLS_RELEASES)} "
                "BLS-Releases geladen)"
                + (
                    " | "
                    + " | ".join(
                        errors[-2:]
                    )
                    if errors
                    else ""
                )
            )
        )

    return (
        [],
        False,
        (
            "FRED-BLS-Fallback lieferte keine verwertbaren Termine"
            + (
                ": "
                + " | ".join(
                    errors[-3:]
                )
                if errors
                else ""
            )
        )
    )


def _parse_bls_html_schedule(
    url,
    event_title
):
    """
    Offizieller BLS-HTML-Fallback.

    Die individuellen BLS-Release-Seiten enthalten Tabellen mit
    Reference Month / Release Date / Release Time. Dieser Pfad
    wird benutzt, wenn der zentrale .ics-Kalender auf einer
    Hosting-IP (z. B. Streamlit Cloud) mit HTTP 403 blockiert wird.
    """
    events = []

    r = requests.get(
        url,
        headers=OFFICIAL_NEWS_HEADERS,
        timeout=15
    )

    r.raise_for_status()

    tables = pd.read_html(
        io.StringIO(
            r.text
        )
    )

    for table in tables:
        if (
            table is None
            or table.empty
        ):
            continue

        normalized_columns = {
            str(col)
            .strip()
            .lower(): col
            for col
            in table.columns
        }

        release_date_col = next(
            (
                original
                for normalized, original
                in normalized_columns.items()
                if "release date" in normalized
            ),
            None
        )

        release_time_col = next(
            (
                original
                for normalized, original
                in normalized_columns.items()
                if "release time" in normalized
            ),
            None
        )

        if (
            release_date_col is None
            or release_time_col is None
        ):
            continue

        for _, row in table.iterrows():
            date_text = str(
                row.get(
                    release_date_col,
                    ""
                )
            ).strip()

            time_text = str(
                row.get(
                    release_time_col,
                    ""
                )
            ).strip()

            if (
                not date_text
                or not time_text
                or date_text.lower() == "nan"
                or time_text.lower() == "nan"
            ):
                continue

            combined = (
                f"{date_text} {time_text}"
            )

            parsed = pd.to_datetime(
                combined,
                errors="coerce"
            )

            if pd.isna(
                parsed
            ):
                # BLS uses e.g. "Sep. 04, 2026".
                combined_clean = re.sub(
                    r"([A-Za-z]{3})\.",
                    r"\1",
                    combined
                )

                parsed = pd.to_datetime(
                    combined_clean,
                    errors="coerce"
                )

            if pd.isna(
                parsed
            ):
                continue

            event_dt = (
                pd.Timestamp(
                    parsed
                )
                .to_pydatetime()
                .replace(
                    tzinfo=NEW_YORK_TZ
                )
            )

            events.append(
                _event_dict(
                    event_title,
                    event_dt,
                    "BLS",
                    url,
                    "USA",
                    "US Macro"
                )
            )

    return _dedupe_events(
        events
    )


@st.cache_data(
    ttl=21600,
    show_spinner=False
)
def fetch_bls_official_events():
    """
    BLS primär über offiziellen iCalendar.

    Fallback:
    Falls bls.ics auf der Hosting-IP mit 403/anderen Fehlern
    blockiert wird, werden ausschließlich die offiziellen
    BLS-HTML-Schedule-Seiten für die von uns als High Impact
    definierten Releases gelesen.
    """
    events = []
    ics_error = None

    # --------------------------------------------------------
    # PRIMARY: official BLS ICS
    # --------------------------------------------------------
    try:
        r = requests.get(
            OFFICIAL_NEWS_URLS[
                "BLS"
            ],
            headers=OFFICIAL_NEWS_HEADERS,
            timeout=15
        )

        r.raise_for_status()

        lines = _unfold_ics_lines(
            r.text
        )

        current = None

        for line in lines:
            if line == "BEGIN:VEVENT":
                current = {}

            elif (
                line == "END:VEVENT"
                and current is not None
            ):
                summary = (
                    current.get(
                        "SUMMARY",
                        ""
                    )
                )

                dtstart_key = next(
                    (
                        k
                        for k
                        in current
                        if k.startswith(
                            "DTSTART"
                        )
                    ),
                    None
                )

                if (
                    summary
                    and dtstart_key
                ):
                    summary_l = (
                        summary.lower()
                    )

                    event_title = None

                    for (
                        pattern,
                        title
                    ) in BLS_HIGH_IMPACT_MAP.items():
                        if pattern in summary_l:
                            event_title = title
                            break

                    if event_title:
                        try:
                            event_dt = (
                                _parse_ics_dtstart(
                                    dtstart_key,
                                    current[
                                        dtstart_key
                                    ]
                                )
                            )

                            events.append(
                                _event_dict(
                                    event_title,
                                    event_dt,
                                    "BLS",
                                    OFFICIAL_NEWS_URLS[
                                        "BLS"
                                    ],
                                    "USA",
                                    "US Macro"
                                )
                            )

                        except Exception:
                            pass

                current = None

            elif (
                current is not None
                and ":"
                in line
            ):
                key, value = (
                    line.split(
                        ":",
                        1
                    )
                )

                base_key = (
                    key.split(
                        ";",
                        1
                    )[0]
                    .upper()
                )

                if base_key == "SUMMARY":
                    current[
                        "SUMMARY"
                    ] = (
                        _clean_ics_value(
                            value
                        )
                    )

                elif base_key == "DTSTART":
                    current[
                        key.upper()
                    ] = value

        events = _dedupe_events(
            events
        )

        if events:
            return (
                events,
                True,
                "Offizieller BLS-iCalendar"
            )

        ics_error = (
            "BLS-iCalendar erreichbar, aber "
            "keine relevanten Termine geparst."
        )

    except Exception as exc:
        ics_error = (
            f"{type(exc).__name__}: "
            f"{str(exc)[:120]}"
        )

    # --------------------------------------------------------
    # FALLBACK: official BLS HTML schedule pages
    # --------------------------------------------------------
    html_events = []
    html_successes = 0
    html_errors = []

    for (
        url_key,
        event_title
    ) in BLS_HTML_RELEASES:
        url = OFFICIAL_NEWS_URLS[
            url_key
        ]

        try:
            parsed_events = (
                _parse_bls_html_schedule(
                    url,
                    event_title
                )
            )

            html_events.extend(
                parsed_events
            )

            # A page can be successfully parsed even if it happens
            # to contain no future rows inside our later horizon.
            html_successes += 1

        except Exception as exc:
            html_errors.append(
                (
                    f"{url_key}: "
                    f"{type(exc).__name__} "
                    f"{str(exc)[:70]}"
                )
            )

    html_events = _dedupe_events(
        html_events
    )

    if (
        html_successes == len(BLS_HTML_RELEASES)
        and html_events
    ):
        return (
            html_events,
            True,
            (
                "BLS HTML-Fallback aktiv "
                f"({html_successes}/{len(BLS_HTML_RELEASES)} "
                "offizielle Release-Seiten erreichbar); "
                f"ICS nicht nutzbar: {ics_error}"
            )
        )

    # Bei nur teilweise erreichbaren BLS-HTML-Seiten versuchen wir
    # zusätzlich FRED, statt eine unvollständige Quelle grün zu melden.

    # --------------------------------------------------------
    # SECONDARY FALLBACK: FRED Release Calendar API
    # --------------------------------------------------------

    (
        fred_events,
        fred_ok,
        fred_note
    ) = fetch_fred_bls_release_events()

    if (
        fred_ok
        and fred_events
    ):
        return (
            fred_events,
            True,
            (
                f"{fred_note}; "
                "BLS direkt/HTML nicht ausreichend. "
                f"ICS: {ics_error}"
                + (
                    " | BLS-HTML Fehler: "
                    + " | ".join(
                        html_errors[-2:]
                    )
                    if html_errors
                    else ""
                )
            )
        )

    if html_events or fred_events:
        partial_events = _dedupe_events(
            list(html_events) + list(fred_events)
        )
        return (
            partial_events,
            False,
            (
                "BLS-Termine nur teilweise abgesichert: "
                f"HTML {html_successes}/{len(BLS_HTML_RELEASES)}; "
                f"FRED: {fred_note}; ICS: {ics_error}"
            )
        )

    if html_successes > 0:
        return (
            [],
            False,
            (
                "BLS HTML-Seiten teilweise erreichbar, aber "
                "keine verwertbaren Termine geparst. "
                f"ICS: {ics_error} | "
                f"FRED-Fallback: {fred_note}"
            )
        )

    return (
        [],
        False,
        (
            "BLS weder direkt noch über FRED ausreichend verfügbar. "
            f"ICS: {ics_error}"
            + (
                " | BLS-HTML: "
                + " | ".join(
                    html_errors[-3:]
                )
                if html_errors
                else ""
            )
            + (
                f" | FRED: {fred_note}"
            )
        )
    )


# ------------------------------------------------------------
# BEA
# ------------------------------------------------------------

def _bea_title_is_high_impact(
    title
):
    title = str(
        title
    ).strip()

    if title.startswith(
        "GDP ("
    ):
        return True

    if (
        "Personal Income and Outlays"
        in title
    ):
        return True

    return False


def _bea_clean_title(
    title
):
    if (
        "Personal Income and Outlays"
        in title
    ):
        return (
            "US PCE / Personal Income & Outlays"
        )

    if title.startswith(
        "GDP ("
    ):
        return (
            "US GDP"
        )

    return title


@st.cache_data(
    ttl=21600,
    show_spinner=False
)
def fetch_bea_official_events():
    events = []

    now_berlin = datetime.now(
        BERLIN_TZ
    )

    years_to_try = {
        now_berlin.year,
        now_berlin.year + 1
    }

    pages = [
        OFFICIAL_NEWS_URLS[
            "BEA"
        ]
    ]

    pages.extend(
        [
            (
                "https://www.bea.gov/news/"
                f"schedule/{year}"
            )
            for year in years_to_try
        ]
    )

    any_success = False
    errors = []

    for url in pages:
        try:
            r = requests.get(
                url,
                headers=OFFICIAL_NEWS_HEADERS,
                timeout=15
            )

            r.raise_for_status()

            any_success = True

            page_year_match = re.search(
                r"Year\s+(20\d{2})",
                r.text,
                flags=re.I
            )

            page_year = (
                int(
                    page_year_match.group(
                        1
                    )
                )
                if page_year_match
                else now_berlin.year
            )

            if BeautifulSoup is None:
                continue

            soup = BeautifulSoup(
                r.text,
                "html.parser"
            )

            for row in soup.find_all(
                "tr"
            ):
                cells = [
                    c.get_text(
                        " ",
                        strip=True
                    )
                    for c
                    in row.find_all(
                        [
                            "th",
                            "td"
                        ]
                    )
                ]

                if len(cells) < 2:
                    continue

                date_text = (
                    cells[0]
                )

                title = (
                    cells[-1]
                )

                if not _bea_title_is_high_impact(
                    title
                ):
                    continue

                m = re.search(
                    (
                        r"([A-Z][a-z]+)\s+"
                        r"(\d{1,2})\s+"
                        r"(\d{1,2}:\d{2})\s+"
                        r"([AP]M)"
                    ),
                    date_text
                )

                if not m:
                    continue

                try:
                    event_dt = (
                        datetime.strptime(
                            (
                                f"{m.group(1)} "
                                f"{m.group(2)} "
                                f"{page_year} "
                                f"{m.group(3)} "
                                f"{m.group(4)}"
                            ),
                            "%B %d %Y %I:%M %p"
                        )
                        .replace(
                            tzinfo=NEW_YORK_TZ
                        )
                    )

                    events.append(
                        _event_dict(
                            _bea_clean_title(
                                title
                            ),
                            event_dt,
                            "BEA",
                            url,
                            "USA",
                            "US Macro"
                        )
                    )

                except Exception:
                    continue

        except Exception as exc:
            errors.append(
                str(exc)[:90]
            )

    if any_success and events:
        return (
            _dedupe_events(
                events
            ),
            True,
            "Offizieller BEA Release Schedule"
        )

    if any_success:
        return (
            [],
            False,
            "BEA-Seite erreichbar, aber keine relevanten Termine geparst."
        )

    return (
        [],
        False,
        (
            "BEA-Kalender nicht verfügbar"
            + (
                ": "
                + " | ".join(
                    errors[-2:]
                )
                if errors
                else ""
            )
        )
    )


# ------------------------------------------------------------
# FED / FOMC
# ------------------------------------------------------------

FOMC_MONTHS = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}


@st.cache_data(
    ttl=21600,
    show_spinner=False
)
def fetch_fed_official_events():
    """
    Liest ausschließlich die Meeting-Blöcke des aktuellen und
    folgenden Jahres aus dem offiziellen FOMC-Kalender.

    Wichtig:
    Die Fed-Seite listet nach dem aktuellen Jahr zunächst mehrere
    historische Jahre und erst später das Future Year. Deshalb wird
    jeder Jahresblock am NÄCHSTEN beliebigen "<Jahr> FOMC Meetings"-
    Marker beendet. So können historische Termine nicht versehentlich
    dem aktuellen Jahr zugeordnet werden.
    """
    if BeautifulSoup is None:
        return (
            [],
            False,
            "BeautifulSoup nicht verfügbar."
        )

    try:
        r = requests.get(
            OFFICIAL_NEWS_URLS[
                "FED"
            ],
            headers=OFFICIAL_NEWS_HEADERS,
            timeout=15
        )

        r.raise_for_status()

        soup = BeautifulSoup(
            r.text,
            "html.parser"
        )

        page_text = soup.get_text(
            "\n",
            strip=True
        )

        now_berlin = datetime.now(
            BERLIN_TZ
        )

        events = []

        month_pattern = (
            "|".join(
                FOMC_MONTHS.keys()
            )
        )

        for year in sorted(
            {
                now_berlin.year,
                now_berlin.year + 1
            }
        ):
            marker = (
                f"{year} FOMC Meetings"
            )

            start = page_text.find(
                marker
            )

            if start < 0:
                continue

            remainder = page_text[
                start
                + len(marker):
            ]

            # Stop at the next FOMC year heading, regardless of whether
            # that heading is historical or future.
            next_year_heading = re.search(
                r"(?:^|\n)20\d{2}\s+FOMC Meetings",
                remainder
            )

            if next_year_heading:
                block = remainder[
                    :next_year_heading.start()
                ]
            else:
                block = remainder

            for m in re.finditer(
                (
                    rf"({month_pattern})"
                    r"\s+"
                    r"(\d{1,2})"
                    r"\s*-\s*"
                    r"(\d{1,2})"
                    r"\*?"
                ),
                block,
                flags=re.I
            ):
                month_name = (
                    m.group(
                        1
                    ).title()
                )

                end_day = int(
                    m.group(
                        3
                    )
                )

                try:
                    meeting_date = datetime(
                        year,
                        FOMC_MONTHS[
                            month_name
                        ],
                        end_day,
                        tzinfo=NEW_YORK_TZ
                    )

                    decision_dt = (
                        meeting_date.replace(
                            hour=14,
                            minute=0
                        )
                    )

                    press_dt = (
                        meeting_date.replace(
                            hour=14,
                            minute=30
                        )
                    )

                    events.append(
                        _event_dict(
                            "FOMC Rate Decision",
                            decision_dt,
                            "Federal Reserve",
                            OFFICIAL_NEWS_URLS[
                                "FED"
                            ],
                            "USA",
                            "Central Bank"
                        )
                    )

                    events.append(
                        _event_dict(
                            "FOMC Press Conference",
                            press_dt,
                            "Federal Reserve",
                            OFFICIAL_NEWS_URLS[
                                "FED"
                            ],
                            "USA",
                            "Central Bank"
                        )
                    )

                except Exception:
                    continue

        events = (
            _dedupe_events(
                events
            )
        )

        if not events:
            return (
                [],
                False,
                (
                    "Fed-Seite erreichbar, aber keine "
                    "FOMC-Termine geparst."
                )
            )

        return (
            events,
            True,
            (
                "Offizieller FOMC-Kalender; "
                "Decision 14:00 ET, Press Conference 14:30 ET"
            )
        )

    except Exception as exc:
        return (
            [],
            False,
            (
                "Fed-Kalender nicht verfügbar: "
                f"{str(exc)[:120]}"
            )
        )


# ------------------------------------------------------------
# EIA
# ------------------------------------------------------------

def _parse_us_date(
    value,
    year_hint=None
):
    value = str(
        value
    ).strip()

    for fmt in [
        "%B %d, %Y",
        "%B %d %Y",
        "%b %d, %Y",
        "%b %d %Y",
    ]:
        try:
            return datetime.strptime(
                value,
                fmt
            )
        except Exception:
            pass

    if year_hint is not None:
        for fmt in [
            "%B %d",
            "%b %d",
        ]:
            try:
                parsed = datetime.strptime(
                    value,
                    fmt
                )

                return parsed.replace(
                    year=int(
                        year_hint
                    )
                )
            except Exception:
                pass

    return None


def _parse_us_clock(
    value,
    default_hour=10,
    default_minute=30
):
    value = (
        str(value)
        .strip()
        .lower()
        .replace(
            ".",
            ""
        )
    )

    for fmt in [
        "%I:%M %p",
        "%I %p",
    ]:
        try:
            parsed = datetime.strptime(
                value.upper(),
                fmt
            )

            return (
                parsed.hour,
                parsed.minute
            )
        except Exception:
            pass

    return (
        default_hour,
        default_minute
    )


@st.cache_data(
    ttl=21600,
    show_spinner=False
)
def fetch_eia_official_events():
    """
    Standard: Mittwoch 10:30 ET.
    Feiertagsausnahmen werden, soweit aus der offiziellen
    EIA-Tabelle lesbar, automatisch ersetzt.
    """
    now_berlin = datetime.now(
        BERLIN_TZ
    )

    start_date = (
        now_berlin.date()
        - timedelta(
            days=1
        )
    )

    end_date = (
        now_berlin.date()
        + timedelta(
            days=NEWS_LOOKAHEAD_DAYS
            + 14
        )
    )

    events_by_standard_date = {}

    cursor = start_date

    while cursor <= end_date:
        if cursor.weekday() == 2:
            event_dt = datetime(
                cursor.year,
                cursor.month,
                cursor.day,
                10,
                30,
                tzinfo=NEW_YORK_TZ
            )

            events_by_standard_date[
                cursor
            ] = _event_dict(
                "EIA Weekly Petroleum Status Report / Crude Inventories",
                event_dt,
                "EIA",
                OFFICIAL_NEWS_URLS[
                    "EIA"
                ],
                "USA",
                "Oil Inventories"
            )

        cursor += timedelta(
            days=1
        )

    try:
        r = requests.get(
            OFFICIAL_NEWS_URLS[
                "EIA"
            ],
            headers=OFFICIAL_NEWS_HEADERS,
            timeout=15
        )

        r.raise_for_status()

        tables = pd.read_html(
            io.StringIO(
                r.text
            )
        )

        for table in tables:
            if table.empty:
                continue

            columns_text = [
                str(c).lower()
                for c
                in table.columns
            ]

            if not any(
                "alternate release date"
                in c
                for c in columns_text
            ):
                continue

            for _, row in table.iterrows():
                row_values = [
                    str(v).strip()
                    for v
                    in row.tolist()
                ]

                if len(
                    row_values
                ) < 3:
                    continue

                week_end_text = (
                    row_values[0]
                )

                alt_date_text = (
                    row_values[1]
                )

                alt_time_text = (
                    row_values[3]
                    if len(
                        row_values
                    ) >= 4
                    else "10:30 a.m."
                )

                week_end = (
                    _parse_us_date(
                        week_end_text
                    )
                )

                alt_date = (
                    _parse_us_date(
                        alt_date_text
                    )
                )

                if (
                    week_end is None
                    or alt_date is None
                ):
                    continue

                # EIA week ending = Friday.
                # Standard WPSR follows 5 days later on Wednesday.
                standard_date = (
                    week_end.date()
                    + timedelta(
                        days=5
                    )
                )

                hour, minute = (
                    _parse_us_clock(
                        alt_time_text
                    )
                )

                alt_dt = datetime(
                    alt_date.year,
                    alt_date.month,
                    alt_date.day,
                    hour,
                    minute,
                    tzinfo=NEW_YORK_TZ
                )

                events_by_standard_date.pop(
                    standard_date,
                    None
                )

                events_by_standard_date[
                    alt_date.date()
                ] = _event_dict(
                    "EIA Weekly Petroleum Status Report / Crude Inventories",
                    alt_dt,
                    "EIA",
                    OFFICIAL_NEWS_URLS[
                        "EIA"
                    ],
                    "USA",
                    "Oil Inventories"
                )

        return (
            _dedupe_events(
                list(
                    events_by_standard_date.values()
                )
            ),
            True,
            (
                "Offizielle EIA-WPSR-Termine inkl. "
                "gelesener Feiertagsausnahmen"
            )
        )

    except Exception as exc:
        # Selbst bei ausgefallener HTML-Tabelle bleibt der offizielle
        # Standardtermin Mittwoch 10:30 ET als Fallback erhalten.
        return (
            _dedupe_events(
                list(
                    events_by_standard_date.values()
                )
            ),
            False,
            (
                "EIA Standardkalender Mittwoch 10:30 ET; "
                "Feiertagsprüfung nicht verfügbar: "
                f"{str(exc)[:90]}"
            )
        )


# ------------------------------------------------------------
# ECB
# ------------------------------------------------------------

@st.cache_data(
    ttl=21600,
    show_spinner=False
)
def fetch_ecb_official_events():
    if BeautifulSoup is None:
        return (
            [],
            False,
            "BeautifulSoup nicht verfügbar."
        )

    try:
        r = requests.get(
            OFFICIAL_NEWS_URLS[
                "ECB"
            ],
            headers=OFFICIAL_NEWS_HEADERS,
            timeout=15
        )

        r.raise_for_status()

        soup = BeautifulSoup(
            r.text,
            "html.parser"
        )

        strings = [
            s.strip()
            for s
            in soup.stripped_strings
            if s.strip()
        ]

        events = []

        for i, value in enumerate(
            strings
        ):
            if not re.fullmatch(
                r"\d{2}/\d{2}/\d{4}",
                value
            ):
                continue

            description = " ".join(
                strings[
                    i + 1:
                    i + 6
                ]
            )

            if (
                "monetary policy meeting"
                not in description.lower()
                or "day 2"
                not in description.lower()
                or "press conference"
                not in description.lower()
            ):
                continue

            try:
                date_value = datetime.strptime(
                    value,
                    "%d/%m/%Y"
                )

                decision_dt = date_value.replace(
                    hour=14,
                    minute=15,
                    tzinfo=BERLIN_TZ
                )

                press_dt = date_value.replace(
                    hour=14,
                    minute=45,
                    tzinfo=BERLIN_TZ
                )

                events.append(
                    _event_dict(
                        "ECB Monetary Policy Decision",
                        decision_dt,
                        "ECB",
                        OFFICIAL_NEWS_URLS[
                            "ECB"
                        ],
                        "Euro Area",
                        "Central Bank"
                    )
                )

                events.append(
                    _event_dict(
                        "ECB Press Conference",
                        press_dt,
                        "ECB",
                        OFFICIAL_NEWS_URLS[
                            "ECB"
                        ],
                        "Euro Area",
                        "Central Bank"
                    )
                )

            except Exception:
                continue

        events = (
            _dedupe_events(
                events
            )
        )

        if not events:
            return (
                [],
                False,
                (
                    "ECB-Seite erreichbar, aber keine "
                    "geldpolitischen Termine geparst."
                )
            )

        return (
            events,
            True,
            (
                "Offizieller ECB-Sitzungskalender; "
                "Decision 14:15, Press Conference 14:45 Frankfurt"
            )
        )

    except Exception as exc:
        return (
            [],
            False,
            (
                "ECB-Kalender nicht verfügbar: "
                f"{str(exc)[:120]}"
            )
        )


# ------------------------------------------------------------
# DESTATIS
# ------------------------------------------------------------

def _parse_destatis_calendar_page(
    url,
    target_keyword,
    title_label,
    require_preliminary=False
):
    if BeautifulSoup is None:
        return (
            [],
            False,
            "BeautifulSoup nicht verfügbar."
        )

    try:
        r = requests.get(
            url,
            headers=OFFICIAL_NEWS_HEADERS,
            timeout=15
        )

        r.raise_for_status()

        soup = BeautifulSoup(
            r.text,
            "html.parser"
        )

        events = []

        for heading in soup.find_all(
            [
                "h2",
                "h3",
                "h4"
            ]
        ):
            heading_text = (
                heading.get_text(
                    " ",
                    strip=True
                )
            )

            if (
                target_keyword.lower()
                not in heading_text.lower()
            ):
                continue

            block_parts = []

            for sibling in heading.next_siblings:
                sibling_name = getattr(
                    sibling,
                    "name",
                    None
                )

                if sibling_name in {
                    "h2",
                    "h3",
                    "h4"
                }:
                    break

                if hasattr(
                    sibling,
                    "get_text"
                ):
                    sibling_text = (
                        sibling.get_text(
                            " ",
                            strip=True
                        )
                    )
                else:
                    sibling_text = (
                        str(
                            sibling
                        )
                        .strip()
                    )

                if sibling_text:
                    block_parts.append(
                        sibling_text
                    )

            block = " ".join(
                block_parts
            )

            if (
                require_preliminary
                and "vorläufig"
                not in (
                    heading_text
                    + " "
                    + block
                ).lower()
            ):
                continue

            m = re.search(
                (
                    r"Veröffentlichungstermin"
                    r"\s*:\s*"
                    r"(\d{2}\.\d{2}\.\d{4})"
                ),
                block,
                flags=re.I
            )

            if not m:
                continue

            try:
                date_value = datetime.strptime(
                    m.group(
                        1
                    ),
                    "%d.%m.%Y"
                )

                event_dt = date_value.replace(
                    hour=8,
                    minute=0,
                    tzinfo=BERLIN_TZ
                )

                events.append(
                    _event_dict(
                        title_label,
                        event_dt,
                        "Destatis",
                        url,
                        "Germany",
                        "German Macro"
                    )
                )

            except Exception:
                continue

        return (
            _dedupe_events(
                events
            ),
            True,
            (
                "Offizieller Destatis-Veröffentlichungskalender; "
                "Pressemitteilungen regulär 08:00 Europe/Berlin"
            )
        )

    except Exception as exc:
        return (
            [],
            False,
            (
                "Destatis-Kalender nicht verfügbar: "
                f"{str(exc)[:120]}"
            )
        )


@st.cache_data(
    ttl=21600,
    show_spinner=False
)
def fetch_destatis_official_events():
    events = []
    statuses = []

    cpi_events, cpi_ok, cpi_note = (
        _parse_destatis_calendar_page(
            OFFICIAL_NEWS_URLS[
                "DESTATIS_CPI"
            ],
            "Verbraucherpreisindex",
            "Germany Preliminary CPI",
            require_preliminary=True
        )
    )

    events.extend(
        cpi_events
    )

    statuses.append(
        (
            cpi_ok,
            cpi_note
        )
    )

    gdp_events, gdp_ok, gdp_note = (
        _parse_destatis_calendar_page(
            OFFICIAL_NEWS_URLS[
                "DESTATIS_GDP"
            ],
            "Bruttoinlandsprodukt",
            "Germany GDP",
            require_preliminary=False
        )
    )

    events.extend(
        gdp_events
    )

    statuses.append(
        (
            gdp_ok,
            gdp_note
        )
    )

    overall_ok = (
        bool(statuses)
        and all(
            ok
            for ok, _
            in statuses
        )
    )

    notes = " | ".join(
        note
        for _, note
        in statuses
    )

    return (
        _dedupe_events(
            events
        ),
        overall_ok,
        notes
    )


# ------------------------------------------------------------
# COMBINED OFFICIAL CALENDAR
# ------------------------------------------------------------

@st.cache_data(
    ttl=21600,
    show_spinner=False
)
def fetch_official_news_calendar(
    market_key
):
    all_events = []
    source_status = {}

    # US-Makro ist für sämtliche aktuell im TradePilot
    # enthaltenen Märkte relevant.
    source_functions = [
        (
            "BLS",
            fetch_bls_official_events,
            OFFICIAL_NEWS_URLS[
                "BLS"
            ]
        ),
        (
            "BEA",
            fetch_bea_official_events,
            OFFICIAL_NEWS_URLS[
                "BEA"
            ]
        ),
        (
            "Federal Reserve",
            fetch_fed_official_events,
            OFFICIAL_NEWS_URLS[
                "FED"
            ]
        ),
    ]

    if _news_market_is_oil(
        market_key
    ):
        source_functions.append(
            (
                "EIA",
                fetch_eia_official_events,
                OFFICIAL_NEWS_URLS[
                    "EIA"
                ]
            )
        )

    if _news_market_is_dax(
        market_key
    ):
        source_functions.extend(
            [
                (
                    "ECB",
                    fetch_ecb_official_events,
                    OFFICIAL_NEWS_URLS[
                        "ECB"
                    ]
                ),
                (
                    "Destatis",
                    fetch_destatis_official_events,
                    OFFICIAL_NEWS_URLS[
                        "DESTATIS_CPI"
                    ]
                ),
            ]
        )

    for (
        source_name,
        source_function,
        source_url
    ) in source_functions:
        try:
            events, ok, note = (
                source_function()
            )

            all_events.extend(
                events
            )

            source_status[
                source_name
            ] = {
                "ok": bool(
                    ok
                ),
                "note": str(
                    note
                ),
                "url": source_url
            }

        except Exception as exc:
            source_status[
                source_name
            ] = {
                "ok": False,
                "note": (
                    "Fehler: "
                    f"{str(exc)[:120]}"
                ),
                "url": source_url
            }

    now_berlin = datetime.now(
        BERLIN_TZ
    )

    horizon_end = (
        now_berlin
        + timedelta(
            days=NEWS_LOOKAHEAD_DAYS
        )
    )

    # Ein kürzlich veröffentlichtes Event bleibt für das
    # Nachlauf-Sperrfenster sichtbar.
    start_dt = (
        now_berlin
        - timedelta(
            minutes=NEWS_BLOCK_AFTER_MIN
            + 5
        )
    )

    relevant_events = [
        event
        for event in _dedupe_events(
            all_events
        )
        if _event_within_horizon(
            event[
                "time"
            ],
            start_dt,
            horizon_end
        )
    ]

    return (
        relevant_events,
        source_status
    )


def evaluate_news_risk(
    events
):
    now_berlin = datetime.now(
        BERLIN_TZ
    )

    blocking_events = []

    future_events = []

    for event in events:
        delta_minutes = (
            event[
                "time"
            ]
            - now_berlin
        ).total_seconds() / 60.0

        event_copy = dict(
            event
        )

        event_copy[
            "delta_minutes"
        ] = delta_minutes

        if (
            -NEWS_BLOCK_AFTER_MIN
            <= delta_minutes
            <= NEWS_BLOCK_BEFORE_MIN
        ):
            blocking_events.append(
                event_copy
            )

        if delta_minutes >= 0:
            future_events.append(
                event_copy
            )

    blocking_events.sort(
        key=lambda x: abs(
            x[
                "delta_minutes"
            ]
        )
    )

    future_events.sort(
        key=lambda x: x[
            "time"
        ]
    )

    return {
        "now": now_berlin,
        "blocking": blocking_events,
        "future": future_events,
        "auto_block": bool(
            blocking_events
        ),
        "next_event": (
            future_events[0]
            if future_events
            else None
        )
    }


def _format_countdown(
    minutes_value
):
    if minutes_value is None:
        return "n/a"

    minutes_value = float(
        minutes_value
    )

    if minutes_value < 0:
        mins = int(
            round(
                abs(
                    minutes_value
                )
            )
        )

        return (
            f"vor {mins} Min."
        )

    mins = int(
        round(
            minutes_value
        )
    )

    if mins < 60:
        return (
            f"in {mins} Min."
        )

    hours = (
        mins // 60
    )

    rest = (
        mins % 60
    )

    if hours < 24:
        return (
            f"in {hours} Std. {rest} Min."
        )

    days = (
        hours // 24
    )

    hours_rest = (
        hours % 24
    )

    return (
        f"in {days} Tg. {hours_rest} Std."
    )


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
        "tick_size": 1.00, "tick_value": 25.00, "currency": "EUR",
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
        "Manueller Zusatzcheck: High-Impact News < 30 Min?",
        ["Nein", "Ja"],
        horizontal=True,
        help=(
            "Fallback für Ereignisse, die der automatische "
            "offizielle Kalender nicht abdeckt. "
            "Bei 'Ja' bleibt der bestehende Hard Stop aktiv."
        )
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
# 4D. OFFICIAL ECONOMIC NEWS & EVENT RISK
# ============================================================

with st.spinner(
    "Prüfe offizielle Wirtschafts- und Zentralbankkalender …"
):
    (
        official_news_events,
        official_news_sources
    ) = fetch_official_news_calendar(
        market_key
    )

news_risk = evaluate_news_risk(
    official_news_events
)

automatic_news_block = bool(
    news_risk.get(
        "auto_block",
        False
    )
)

st.markdown("---")
st.subheader(
    "📰 Economic News & Event Risk"
)

n1, n2, n3 = st.columns(
    3
)

with n1:
    next_news = (
        news_risk.get(
            "next_event"
        )
    )

    if next_news:
        st.metric(
            "Nächstes High-Impact Event",
            next_news[
                "time"
            ].strftime(
                "%d.%m. · %H:%M"
            ),
            _format_countdown(
                next_news.get(
                    "delta_minutes"
                )
            ),
            delta_color="off"
        )
    else:
        st.metric(
            "Nächstes High-Impact Event",
            "Keines in 7 Tagen"
        )

with n2:
    st.metric(
        "Auto News Gate",
        (
            "🔴 BLOCK"
            if automatic_news_block
            else "🟢 FREI"
        )
    )

with n3:
    live_sources = sum(
        1
        for data
        in official_news_sources.values()
        if data.get(
            "ok",
            False
        )
    )

    total_sources = len(
        official_news_sources
    )

    st.metric(
        "Offizielle Kalender",
        f"{live_sources}/{total_sources} erreichbar"
    )

failed_official_sources = [
    source_name
    for source_name, source_data
    in official_news_sources.items()
    if not source_data.get(
        "ok",
        False
    )
]

if failed_official_sources:
    st.warning(
        "⚠️ **News-Abdeckung unvollständig:** "
        f"{', '.join(failed_official_sources)} "
        "konnte nicht vollständig geladen werden. "
        "Das grüne Auto-News-Gate ist in diesem Fall keine "
        "Vollständigkeitsgarantie."
    )

blocking_events = (
    news_risk.get(
        "blocking",
        []
    )
)

if blocking_events:
    for event in blocking_events:
        st.error(
            "🔴 **AUTO NEWS BLOCK:** "
            f"{event['title']} · "
            f"{event['time'].strftime('%H:%M')} Uhr Europe/Berlin "
            f"({_format_countdown(event.get('delta_minutes'))}) · "
            f"Quelle: {event['source']}"
        )

    st.caption(
        f"Execution-Sperrfenster: {NEWS_BLOCK_BEFORE_MIN} Minuten "
        f"vor bis {NEWS_BLOCK_AFTER_MIN} Minuten nach dem Event."
    )

elif next_news:
    minutes_to_next = (
        next_news.get(
            "delta_minutes"
        )
    )

    if (
        minutes_to_next is not None
        and minutes_to_next <= 60
    ):
        st.warning(
            "🟡 Nächstes wichtiges Event innerhalb einer Stunde: "
            f"**{next_news['title']}** um "
            f"**{next_news['time'].strftime('%H:%M')} Uhr** "
            f"({_format_countdown(minutes_to_next)})."
        )

    else:
        st.success(
            "🟢 Kein automatisch erkanntes High-Impact-Event "
            f"innerhalb der nächsten {NEWS_BLOCK_BEFORE_MIN} Minuten."
        )

else:
    failed_sources = [
        source_name
        for source_name, source_data
        in official_news_sources.items()
        if not source_data.get(
            "ok",
            False
        )
    ]

    if failed_sources:
        st.warning(
            "⚠️ In den **erreichbaren** offiziellen Kalendern wurde "
            "für die nächsten 7 Tage kein passendes High-Impact-Event "
            "gefunden. Die automatische Abdeckung ist jedoch "
            f"unvollständig, weil **{', '.join(failed_sources)}** "
            "aktuell nicht zuverlässig geladen werden konnte. "
            "Bitte den manuellen Investing-/baha-Backup-Check verwenden."
        )
    else:
        st.info(
            "ℹ️ In allen aktuell angebundenen und erreichbaren "
            "offiziellen Kalendern wurde für die nächsten 7 Tage "
            "kein passendes High-Impact-Event gefunden."
        )

if official_news_events:
    display_rows = []

    for event in official_news_events[:10]:
        delta_minutes = (
            event[
                "time"
            ]
            - news_risk[
                "now"
            ]
        ).total_seconds() / 60.0

        display_rows.append(
            {
                "Datum": (
                    event[
                        "time"
                    ].strftime(
                        "%d.%m.%Y"
                    )
                ),
                "Uhrzeit": (
                    event[
                        "time"
                    ].strftime(
                        "%H:%M"
                    )
                ),
                "Event": event[
                    "title"
                ],
                "Quelle": event[
                    "source"
                ],
                "Region": event[
                    "region"
                ],
                "Countdown": (
                    _format_countdown(
                        delta_minutes
                    )
                )
            }
        )

    with st.expander(
        "📅 Relevante offizielle Termine – nächste 7 Tage",
        expanded=False
    ):
        st.dataframe(
            pd.DataFrame(
                display_rows
            ),
            hide_index=True,
            use_container_width=True
        )

with st.expander(
    "📡 Offizielle News-Quellen & Abdeckung",
    expanded=False
):
    source_cols = st.columns(
        2
    )

    for i, (
        source_name,
        source_data
    ) in enumerate(
        official_news_sources.items()
    ):
        source_cols[
            i % 2
        ].markdown(
            (
                f"{'🟢' if source_data.get('ok') else '⚠️'} "
                f"**{source_name}**  \n"
                f"{source_data.get('note', '')}"
            )
        )

    st.caption(
        "Automatisch abgedeckt werden die wichtigsten offiziellen "
        "US-Makrotermine (BLS mit FRED-Release-Fallback / BEA / Fed); "
        "bei Öl zusätzlich EIA; "
        "bei DAX/GER40 zusätzlich ECB und Destatis. "
        "Nicht enthalten sind z. B. alle Fed-/ECB-Reden, private "
        "PMI-Anbieter, ADP und sämtliche sonstigen weltweiten Termine."
    )

st.markdown(
    "#### 🔎 Manueller News-Backup-Check"
)

st.caption(
    "Der automatische Filter deckt ausgewählte offizielle High-Impact-"
    "Termine ab. Für einen schnellen vollständigen Tagescheck kannst du "
    "zusätzlich direkt die externen Wirtschaftskalender öffnen."
)

manual_link_col1, manual_link_col2 = (
    st.columns(2)
)

with manual_link_col1:
    st.link_button(
        "📅 Investing.com – Wirtschaftskalender",
        OFFICIAL_NEWS_URLS[
            "INVESTING"
        ],
        use_container_width=True
    )

with manual_link_col2:
    st.link_button(
        "📅 baha – Wirtschaftskalender",
        OFFICIAL_NEWS_URLS[
            "BAHA"
        ],
        use_container_width=True
    )

manual_news_block = (
    news_soon == "Ja"
)

combined_news_block = (
    automatic_news_block
    or manual_news_block
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
    price_context = fetch_price_context(
        market_key
    )

st.markdown("---")
st.subheader("📍 Price Context & Key Levels")

price_context_live = bool(
    price_context.get("ok", False)
)

if not price_context_live:
    st.warning(
        "⚠️ Yahoo Price Context aktuell nicht verfügbar: "
        f"{price_context.get('reason', 'unbekannter Fehler')}. "
        "Die manuellen/eToro-Felder bleiben als echter Fallback nutzbar."
    )

# Automatische Werte; bei ausgefallenem Yahoo bleiben sie None.
pdc_auto = price_context.get("pdc") if price_context_live else None
pdh_auto = price_context.get("pdh") if price_context_live else None
pdl_auto = price_context.get("pdl") if price_context_live else None
pwc_auto = price_context.get("pwc") if price_context_live else None
pwh_auto = price_context.get("pwh") if price_context_live else None
pwl_auto = price_context.get("pwl") if price_context_live else None
ema20_auto = price_context.get("ema20") if price_context_live else None
ema50_auto = price_context.get("ema50") if price_context_live else None
ema200_auto = price_context.get("ema200") if price_context_live else None

st.markdown("**✍️ Optionale eToro-/manuelle Overrides**")
st.caption(
    "Yahoo bleibt Standard, wenn verfügbar. Du kannst jeden Wert einzeln "
    "überschreiben. Falls Yahoo ausfällt, funktionieren dieselben Felder "
    "als manueller Fallback."
)

with st.expander("eToro-/manuelle Werte eingeben", expanded=False):
    st.markdown("##### Vortag")
    ov_pd1, ov_pd2, ov_pd3 = st.columns(3)
    with ov_pd1:
        use_pdc_override = st.checkbox("PDC überschreiben", value=False, key="override_pdc")
        pdc_manual = st.number_input(
            "PDC manuell", min_value=0.0,
            value=float(pdc_auto if pdc_auto is not None else 0.0),
            step=0.01, format="%.4f", key="manual_pdc",
            disabled=not use_pdc_override
        )
    with ov_pd2:
        use_pdh_override = st.checkbox("PDH überschreiben", value=False, key="override_pdh")
        pdh_manual = st.number_input(
            "PDH manuell", min_value=0.0,
            value=float(pdh_auto if pdh_auto is not None else 0.0),
            step=0.01, format="%.4f", key="manual_pdh",
            disabled=not use_pdh_override
        )
    with ov_pd3:
        use_pdl_override = st.checkbox("PDL überschreiben", value=False, key="override_pdl")
        pdl_manual = st.number_input(
            "PDL manuell", min_value=0.0,
            value=float(pdl_auto if pdl_auto is not None else 0.0),
            step=0.01, format="%.4f", key="manual_pdl",
            disabled=not use_pdl_override
        )

    st.markdown("##### Vorwoche")
    ov_pw1, ov_pw2, ov_pw3 = st.columns(3)
    with ov_pw1:
        use_pwc_override = st.checkbox("PWC überschreiben", value=False, key="override_pwc")
        pwc_manual = st.number_input(
            "PWC manuell", min_value=0.0,
            value=float(pwc_auto if pwc_auto is not None else 0.0),
            step=0.01, format="%.4f", key="manual_pwc",
            disabled=not use_pwc_override
        )
    with ov_pw2:
        use_pwh_override = st.checkbox("PWH überschreiben", value=False, key="override_pwh")
        pwh_manual = st.number_input(
            "PWH manuell", min_value=0.0,
            value=float(pwh_auto if pwh_auto is not None else 0.0),
            step=0.01, format="%.4f", key="manual_pwh",
            disabled=not use_pwh_override
        )
    with ov_pw3:
        use_pwl_override = st.checkbox("PWL überschreiben", value=False, key="override_pwl")
        pwl_manual = st.number_input(
            "PWL manuell", min_value=0.0,
            value=float(pwl_auto if pwl_auto is not None else 0.0),
            step=0.01, format="%.4f", key="manual_pwl",
            disabled=not use_pwl_override
        )

    st.markdown("##### Daily EMAs")
    st.caption(
        "Bei manueller Eingabe bitte Daily-EMA-Werte aus dem eToro-/Brokerchart verwenden."
    )
    ov_em1, ov_em2, ov_em3 = st.columns(3)
    with ov_em1:
        use_ema20_override = st.checkbox("EMA20 überschreiben", value=False, key="override_ema20")
        ema20_manual = st.number_input(
            "Daily EMA20 manuell", min_value=0.0,
            value=float(ema20_auto if ema20_auto is not None else 0.0),
            step=0.01, format="%.4f", key="manual_ema20",
            disabled=not use_ema20_override
        )
    with ov_em2:
        use_ema50_override = st.checkbox("EMA50 überschreiben", value=False, key="override_ema50")
        ema50_manual = st.number_input(
            "Daily EMA50 manuell", min_value=0.0,
            value=float(ema50_auto if ema50_auto is not None else 0.0),
            step=0.01, format="%.4f", key="manual_ema50",
            disabled=not use_ema50_override
        )
    with ov_em3:
        use_ema200_override = st.checkbox("EMA200 überschreiben", value=False, key="override_ema200")
        ema200_manual = st.number_input(
            "Daily EMA200 manuell", min_value=0.0,
            value=float(ema200_auto if ema200_auto is not None else 0.0),
            step=0.01, format="%.4f", key="manual_ema200",
            disabled=not use_ema200_override
        )

# Reject accidental zero overrides as missing rather than as a real market level.
def _manual_value_or_none(use_override, value):
    if not use_override:
        return None
    try:
        value = float(value)
        return value if np.isfinite(value) and value > 0 else None
    except Exception:
        return None

def _effective_context_value(auto_value, use_override, manual_value):
    manual = _manual_value_or_none(use_override, manual_value)
    if manual is not None:
        return manual, "eToro / manuell"
    if auto_value is not None:
        return auto_value, "Yahoo / automatisch"
    return None, "nicht verfügbar"

pdc, pdc_source = _effective_context_value(pdc_auto, use_pdc_override, pdc_manual)
pdh, pdh_source = _effective_context_value(pdh_auto, use_pdh_override, pdh_manual)
pdl, pdl_source = _effective_context_value(pdl_auto, use_pdl_override, pdl_manual)
pwc, pwc_source = _effective_context_value(pwc_auto, use_pwc_override, pwc_manual)
pwh, pwh_source = _effective_context_value(pwh_auto, use_pwh_override, pwh_manual)
pwl, pwl_source = _effective_context_value(pwl_auto, use_pwl_override, pwl_manual)
ema20, ema20_source = _effective_context_value(ema20_auto, use_ema20_override, ema20_manual)
ema50, ema50_source = _effective_context_value(ema50_auto, use_ema50_override, ema50_manual)
ema200, ema200_source = _effective_context_value(ema200_auto, use_ema200_override, ema200_manual)

active_overrides = [
    name for name, source in [
        ("PDC", pdc_source), ("PDH", pdh_source), ("PDL", pdl_source),
        ("PWC", pwc_source), ("PWH", pwh_source), ("PWL", pwl_source),
        ("EMA20", ema20_source), ("EMA50", ema50_source), ("EMA200", ema200_source),
    ] if source == "eToro / manuell"
]

if active_overrides:
    st.info(
        "✍️ Aktive manuelle/eToro-Overrides: "
        f"**{', '.join(active_overrides)}**."
    )

# Vortag
st.markdown("**Vortag**")
pd1, pd2, pd3, pd4 = st.columns(4)
pd1.metric("PDC · Close", _format_level(pdc))
pd2.metric("PDH · High", _format_level(pdh))
pd3.metric("PDL · Low", _format_level(pdl))
day_position = _range_position(entry_price, pdl, pdh)
pd4.metric("Entry in Vortagesrange", f"{day_position:.0f}%" if day_position is not None else "n/a")
st.caption(
    "Yahoo-Vortagesstand: "
    f"**{_format_context_date(price_context.get('previous_day_date') if price_context_live else None)}** · "
    f"PDC: **{pdc_source}** · PDH: **{pdh_source}** · PDL: **{pdl_source}**"
)

# Vorwoche
st.markdown("**Vorwoche**")
pw1, pw2, pw3, pw4 = st.columns(4)
pw1.metric("PWC · Close", _format_level(pwc))
pw2.metric("PWH · High", _format_level(pwh))
pw3.metric("PWL · Low", _format_level(pwl))
week_position = _range_position(entry_price, pwl, pwh)
pw4.metric("Entry in Vorwochenrange", f"{week_position:.0f}%" if week_position is not None else "n/a")
st.caption(
    "Yahoo-Vorwochenstand: "
    f"**{_format_context_date(price_context.get('previous_week_date') if price_context_live else None)}** · "
    f"PWC: **{pwc_source}** · PWH: **{pwh_source}** · PWL: **{pwl_source}**"
)

# Daily EMA
st.markdown("**Daily EMA Context**")
em1, em2, em3, em4 = st.columns(4)
em1.metric("EMA 20", _format_level(ema20), f"Entry {entry_price - ema20:+,.2f}" if ema20 is not None else None)
em2.metric("EMA 50", _format_level(ema50), f"Entry {entry_price - ema50:+,.2f}" if ema50 is not None else None)
em3.metric("EMA 200", _format_level(ema200), f"Entry {entry_price - ema200:+,.2f}" if ema200 is not None else None)
if ema20 is not None and ema50 is not None and ema200 is not None:
    if ema20 > ema50 > ema200:
        ema_structure = "🟢 Bullisch"
    elif ema20 < ema50 < ema200:
        ema_structure = "🔴 Bärisch"
    else:
        ema_structure = "🟡 Gemischt"
else:
    ema_structure = "⚪ Unvollständig"
em4.metric("EMA-Struktur", ema_structure)
st.caption(
    "Yahoo-EMA-Stand: "
    f"**{_format_context_date(price_context.get('ema_date') if price_context_live else None)}** · "
    f"EMA20: **{ema20_source}** · EMA50: **{ema50_source}** · EMA200: **{ema200_source}**"
)

# Entry/Stop/Target context; information only.
st.markdown("**Entry / Stop / Target Kontext**")
context_messages = []
if pdh is not None and pdl is not None:
    if entry_price > pdh:
        context_messages.append("Entry liegt **oberhalb des Vortageshochs (PDH)**.")
    elif entry_price < pdl:
        context_messages.append("Entry liegt **unterhalb des Vortagestiefs (PDL)**.")
    elif pdc is not None and entry_price >= pdc:
        context_messages.append("Entry liegt innerhalb der Vortagesrange **oberhalb des Vortagesschlusses (PDC)**.")
    elif pdc is not None:
        context_messages.append("Entry liegt innerhalb der Vortagesrange **unterhalb des Vortagesschlusses (PDC)**.")
    else:
        context_messages.append("Entry liegt **innerhalb der Vortagesrange**; PDC ist nicht verfügbar.")
if pwh is not None and pwl is not None:
    if entry_price > pwh:
        context_messages.append("Entry liegt **oberhalb des Vorwochenhochs (PWH)**.")
    elif entry_price < pwl:
        context_messages.append("Entry liegt **unterhalb des Vorwochentiefs (PWL)**.")
    else:
        context_messages.append("Entry liegt **innerhalb der Vorwochenspanne**.")
for msg in context_messages:
    st.write(f"• {msg}")

levels_for_target = {
    "PDH": pdh, "PDL": pdl, "PWH": pwh, "PWL": pwl,
    "EMA20": ema20, "EMA50": ema50, "EMA200": ema200,
}
crossed_levels = []
if direction == "Long":
    crossed_levels = [name for name, value in levels_for_target.items() if value is not None and entry_price < value <= target_price]
else:
    crossed_levels = [name for name, value in levels_for_target.items() if value is not None and target_price <= value < entry_price]
if crossed_levels:
    st.warning(
        "⚠️ Auf dem Weg vom Entry zum Target liegen folgende Referenzlevels: "
        f"**{', '.join(crossed_levels)}**. Kein automatischer Blocker; charttechnisch prüfen."
    )

stop_refs = []
if direction == "Long":
    if pdl is not None and stop_price < pdl: stop_refs.append("unter PDL")
    if pwl is not None and stop_price < pwl: stop_refs.append("unter PWL")
else:
    if pdh is not None and stop_price > pdh: stop_refs.append("über PDH")
    if pwh is not None and stop_price > pwh: stop_refs.append("über PWH")
if stop_refs:
    st.info(f"ℹ️ Stop-Lage: **{', '.join(stop_refs)}**.")

if price_context_live:
    st.caption(
        f"Quelle Automatik: **{price_context.get('source_label', 'Yahoo')}** · "
        f"Ticker `{price_context.get('ticker', 'n/a')}` · letzter Yahoo-Referenzkurs: "
        f"**{_format_level(price_context.get('reference_price'))}** "
        f"({_format_context_date(price_context.get('reference_date'))})."
    )
    if price_context.get("proxy", False):
        st.caption(
            "⚠️ Referenzhinweis: Yahoo ist bei diesem Instrument ein Proxy. "
            "Broker-CFD-/Micro-/DAX-Future-Sessionlevels können abweichen."
        )

st.caption(
    "PDH/PDL/PDC, PWH/PWL/PWC und EMA20/50/200 sind reine "
    "Execution-/Kontextinformationen. Sie verändern weder Final Regime "
    "Score noch automatisch Gear oder Trade-Freigabe."
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

if combined_news_block:
    if automatic_news_block and manual_news_block:
        news_reason = (
            "Automatischer offizieller Kalender UND manueller "
            "Zusatzcheck melden Event-Risiko."
        )
    elif automatic_news_block:
        blocking_titles = [
            event[
                "title"
            ]
            for event
            in news_risk.get(
                "blocking",
                []
            )
        ]

        news_reason = (
            "Offizieller Kalender blockiert: "
            + (
                ", ".join(
                    blocking_titles
                )
                if blocking_titles
                else "High-Impact Event"
            )
        )
    else:
        news_reason = (
            "Manueller Zusatzcheck meldet High-Impact News "
            "innerhalb von 30 Minuten."
        )

    primary_blockers.append((
        "🔴 High-Impact News",
        news_reason
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
    "Hinweis: v3.5.4 Fused Checked Trade Pilot ist ein rein quantitatives Decision Gate. "
    "Spread-, Overnight-, Kommissions- und Marginwerte sind "
    "Planungsannahmen und keine Echtzeit-Brokerdaten. "
    "Sie müssen regelmäßig gegen die tatsächlichen Brokerbedingungen "
    "validiert werden. Keine Anlageberatung."
)
