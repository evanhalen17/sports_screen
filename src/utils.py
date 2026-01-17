#! .\SportsbookOdds\env\Scripts\python.exe

import os
import json
import re
from typing import Generator, Union, Optional, Dict, List
from datetime import datetime, timedelta, timezone
import tempfile
import time

def save_to_json(json_response, directory, file_name) -> None:
    if not os.path.exists(directory):
        os.makedirs(directory)
    file_path = os.path.join(directory, file_name)
    with open(file_path, 'w') as file:
        # Use indent for pretty printing
        json.dump(json_response, file, indent=4)

def date_range(
        start_date: Union[str, datetime],
        end_date: Union[str, datetime],
        step: Union[str, timedelta] = timedelta(days=1)
    ) -> Generator[str, None, None]:
    
    # Helper function to parse step from string
    def parse_step(step: str) -> timedelta:
        match = re.match(r'(\d+)\s*(seconds?|minutes?|hours?|days?|weeks?|months?|years?)', step)
        if not match:
            raise ValueError("Invalid step format")
        value, unit = int(match.group(1)), match.group(2).lower().rstrip('s')
        if 'second' in unit:
            return timedelta(seconds=value)
        elif 'minute' in unit:
            return timedelta(minutes=value)
        elif 'hour' in unit:
            return timedelta(hours=value)
        elif 'day' in unit:
            return timedelta(days=value)
        elif 'week' in unit:
            return timedelta(weeks=value)
        elif 'month' in unit:
            # Approximate one month as 30 days
            return timedelta(days=value * 30)
        elif 'year' in unit:
            # Approximate one year as 365 days
            return timedelta(days=value * 365)
        else:
            raise ValueError("Invalid time unit in step")

    # Convert start_date and end_date to datetime if they are strings
    if isinstance(start_date, str):
        start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
    if isinstance(end_date, str):
        end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))

    # Convert step to timedelta if it is a string
    if isinstance(step, str):
        step = parse_step(step)
    
    current_date = start_date
    while current_date <= end_date:
        # Ensure only 'Z' is appended for UTC
        if current_date.tzinfo is not None:
            yield current_date.strftime('%Y-%m-%dT%H:%M:%SZ')
        else:
            yield current_date.isoformat() + 'Z'
        current_date += step

try:
    from zoneinfo import ZoneInfo

    _EASTERN_ZONE = ZoneInfo("America/New_York")
    _UTC_ZONE = timezone.utc
except Exception:
    import pytz

    _UTC_ZONE = pytz.timezone("UTC")
    _EASTERN_ZONE = pytz.timezone("America/New_York")


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt
    if hasattr(_UTC_ZONE, "localize"):
        return _UTC_ZONE.localize(dt)
    return dt.replace(tzinfo=_UTC_ZONE)


def convert_to_eastern(utc_timestamp: str) -> str:
    """Converts a UTC timestamp to Eastern Time (ET) and formats it for tabular display."""
    if not utc_timestamp:
        return ""

    try:
        utc_time = datetime.fromisoformat(utc_timestamp.replace("Z", "+00:00"))
    except ValueError:
        try:
            utc_time = datetime.strptime(utc_timestamp, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return str(utc_timestamp)

    utc_time = _ensure_aware(utc_time)
    eastern_time = utc_time.astimezone(_EASTERN_ZONE)

    # Format for display (e.g., 'Mon, Jun 27, 2022 - 08:00 PM ET')
    return eastern_time.strftime("%a, %b %d, %Y - %I:%M %p ET")

def kelly_criterion(p: float, decimal_odds: float) -> float:
    """
    Calculate the Kelly Criterion for optimal bet sizing.

    Args:
        p (float): Probability of success (must be between 0 and 1).
        decimal_odds (float): Decimal odds of the bet.

    Returns:
        float: Optimal fraction of bankroll to bet according to the Kelly Criterion.
    """
    if not (0 < p < 1):
        raise ValueError("Probability of success (p) must be between 0 and 1.")

    if decimal_odds <= 1:
        raise ValueError("Odds must be greater than 1.")

    # Calculate the Kelly Criterion formula
    kelly_fraction = (p * (decimal_odds - 1) - (1 - p)) / (decimal_odds - 1)

    # Ensure the result is non-negative
    return max(kelly_fraction, 0)

def odds_converter(odds_from: str, odds_to: str, odds_value: float) -> float:
    """
    Convert between different odds formats: probability, american, decimal, fractional.

    Args:
        odds_from (str): The format of the input odds ("probability", "american", "decimal", "fractional").
        odds_to (str): The format of the output odds ("probability", "american", "decimal", "fractional").
        odds_value (float): The value of the odds in the input format.

    Returns:
        float: The value of the odds in the output format.
    """
    def no_conversion(odds_value):
        return odds_value

    def probability_to_decimal(prob):
        return 1 / prob

    def decimal_to_probability(dec):
        return 1 / dec

    def decimal_to_american(dec):
        return (dec - 1) * 100 if dec >= 2 else -100 / (dec - 1)

    def american_to_decimal(amer):
        return (amer / 100) + 1 if amer > 0 else (100 / -amer) + 1

    def decimal_to_fractional(dec):
        return dec - 1

    def fractional_to_decimal(frac):
        return frac + 1

    def probability_to_american(prob):
        return decimal_to_american(probability_to_decimal(prob))

    def american_to_probability(amer):
        return decimal_to_probability(american_to_decimal(amer))

    def fractional_to_probability(frac):
        return decimal_to_probability(fractional_to_decimal(frac))

    def probability_to_fractional(prob):
        return decimal_to_fractional(probability_to_decimal(prob))

    # Conversion map
    conversions = {
        ("probability", "probability"): no_conversion,
        ("american", "american"): no_conversion,
        ("decimal", "decimal"): no_conversion,
        ("fractional", "fractional"): no_conversion,
        ("probability", "decimal"): probability_to_decimal,
        ("decimal", "probability"): decimal_to_probability,
        ("decimal", "american"): decimal_to_american,
        ("american", "decimal"): american_to_decimal,
        ("decimal", "fractional"): decimal_to_fractional,
        ("fractional", "decimal"): fractional_to_decimal,
        ("probability", "american"): probability_to_american,
        ("american", "probability"): american_to_probability,
        ("fractional", "probability"): fractional_to_probability,
        ("probability", "fractional"): probability_to_fractional,
    }

    if (odds_from, odds_to) not in conversions:
        raise ValueError(f"Conversion from {odds_from} to {odds_to} is not supported.")

    return conversions[(odds_from, odds_to)](odds_value)

def remove_none_values(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}

def set_stylesheet(palette: dict[str: str]) -> str:
    """Return a modernized stylesheet string based on the provided palette.

    The stylesheet focuses on readable typography, comfortable spacing, and
    clear contrast for both light and dark palettes.
    """
    return f"""
    /* Global font + app background */
    QMainWindow {{
        background-color: {palette['background-dark']};
        color: {palette['text-light']};
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial;
        font-size: 13px;
    }}

    /* Table styling */
    QTableWidget {{
        background-color: {palette['table-row-alt1']};
        alternate-background-color: {palette['table-row-alt2']};
        gridline-color: rgba(0,0,0,0.08);
        color: {palette['text-light']};
        selection-background-color: {palette['table-row-hover']};
        selection-color: {palette['text-light']};
        border-radius: 8px;
        padding: 6px;
    }}

    QTableWidget::item {{
        padding: 0px;
        border-bottom: 1px solid rgba(0,0,0,0.06);
    }}

    QTableWidget::item:hover {{
        background-color: {palette['table-row-hover']};
        color: {palette['text-light']};
    }}

    QTableWidget::item:selected {{
        background-color: {palette['table-row-hover']};
        color: {palette['text-light']};
    }}

    /* Header */
    QHeaderView::section {{
        background-color: {palette['table-hdr-dark']};
        color: {palette['text-light']};
        padding: 8px;
        border: none;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.6px;
    }}

    /* Comboboxes */
    QComboBox {{
        background-color: transparent;
        color: {palette['text-light']};
        border: 1px solid rgba(0,0,0,0.12);
        padding: 6px 8px;
        border-radius: 6px;
        min-height: 28px;
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
    }}

    /* Labels */
    QLabel {{
        color: {palette['text-light']};
    }}

    /* Buttons */
    QPushButton {{
        background-color: {palette['table-hdr-dark']};
        color: {palette['text-light']};
        border: none;
        padding: 8px 12px;
        border-radius: 8px;
        font-size: 13px;
    }}
    QPushButton:hover {{
        background-color: {palette['combobox-hover']};
    }}
    QPushButton:checked {{
        background-color: {palette['table-row-hover']};
    }}

    /* Line edits */
    QLineEdit {{
        background-color: transparent;
        color: {palette['text-light']};
        border: 1px solid rgba(0,0,0,0.12);
        padding: 6px 8px;
        border-radius: 6px;
        min-height: 28px;
    }}

    /* Small helper text */
    .smallLabel {{
        font-size: 11px;
        color: rgba(255,255,255,0.75);
    }}

    /* Filters container */
    #filtersBox {{
        background-color: rgba(0, 0, 0, 0.08);
        border: 1px solid rgba(0, 0, 0, 0.12);
        border-radius: 8px;
    }}

    /* Scrollbar styling */
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
    }}
    QScrollBar::handle:vertical {{
        background: {palette['table-hdr-dark']};
        border-radius: 5px;
        min-height: 20px;
    }}

    /* Inputs */
    QDoubleSpinBox, QLineEdit {{
        background-color: rgba(255,255,255,0.02);
        border: 1px solid rgba(0,0,0,0.08);
        padding: 6px;
        border-radius: 6px;
    }}

    /* Emphasize selection */
    QTableWidget QTableCornerButton::section {{
        background: transparent;
    }}
    """


def fetch_event_ids_for_sports(
    odds_api,
    sport_keys: Optional[List[str]] = None,
    commence_time_from: Optional[str] = None,
    commence_time_to: Optional[str] = None,
    cache_ttl: int = 300,
    cache_file: Optional[str] = None,
) -> Dict[str, List[str]]:
    """
    Fetch event IDs for the given sports using the provided `odds_api` client.

    - If `sport_keys` is None, the function will call `odds_api.get_sports()` to
      discover available sports.
    - Results are cached to a temp file for `cache_ttl` seconds to avoid
      repeated network calls. The cache file location may be overridden with
      `cache_file`.

    Returns a mapping of `sport_key` -> list of event ids.
    """
    if cache_file is None:
        cache_file = os.path.join(tempfile.gettempdir(), 'sports_screen_event_ids_cache.json')

    now = int(time.time())
    # return cached results when available and fresh
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                cache = json.load(f)
            if cache.get('timestamp', 0) + cache_ttl > now:
                return cache.get('event_ids', {})
        except Exception:
            pass

    event_ids: Dict[str, List[str]] = {}

    # discover sports if not provided
    if sport_keys is None:
        try:
            sports = odds_api.get_sports()
            sport_keys = [s['key'] for s in sports]
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch sports from OddsAPI: {exc}")

    for sk in sport_keys:
        try:
            events = odds_api.get_events(sk, commence_time_from=commence_time_from, commence_time_to=commence_time_to)
            # some endpoints may wrap results in a 'data' key
            if isinstance(events, dict) and 'data' in events:
                evs = events.get('data', [])
            else:
                evs = events or []

            ids = [e['id'] for e in evs if 'id' in e]
            if ids:
                event_ids[sk] = ids
        except Exception:
            # Skip sports that fail to return events
            continue

    # persist cache (best-effort)
    try:
        with open(cache_file, 'w') as f:
            json.dump({'timestamp': now, 'event_ids': event_ids}, f)
    except Exception:
        pass

    return event_ids


def get_all_event_ids_flat(
    odds_api,
    sport_keys: Optional[List[str]] = None,
    commence_time_from: Optional[str] = None,
    commence_time_to: Optional[str] = None,
    cache_ttl: int = 300,
    cache_file: Optional[str] = None,
) -> List[str]:
    """Return a deduplicated flat list of event ids across requested sports."""
    mapping = fetch_event_ids_for_sports(
        odds_api,
        sport_keys=sport_keys,
        commence_time_from=commence_time_from,
        commence_time_to=commence_time_to,
        cache_ttl=cache_ttl,
        cache_file=cache_file,
    )
    seen = set()
    flat: List[str] = []
    for ids in mapping.values():
        for i in ids:
            if i not in seen:
                seen.add(i)
                flat.append(i)
    return flat


def _prefs_file_path(custom_path: Optional[str] = None) -> str:
    """Return the prefs file path, creating `data/` if needed.

    If `custom_path` is provided, it is returned directly.
    """
    if custom_path:
        return custom_path
    base = os.path.join(os.getcwd(), 'data')
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        pass
    return os.path.join(base, 'user_prefs.json')


def load_user_prefs(path: Optional[str] = None) -> Dict:
    """Load user preferences from JSON. Returns empty dict on error."""
    fp = _prefs_file_path(path)
    try:
        if os.path.exists(fp):
            with open(fp, 'r') as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}


def save_user_prefs(prefs: Dict, path: Optional[str] = None) -> bool:
    """Save user preferences to JSON. Returns True on success."""
    fp = _prefs_file_path(path)
    try:
        with open(fp, 'w') as f:
            json.dump(prefs or {}, f, indent=2)
        return True
    except Exception:
        return False


def compute_consensus_point(
    event: dict,
    market_type: str = 'spreads',
    pinnacle_weight: int = 10,
    market_key: str | None = None,
):
    """
    Compute a consensus point for an event.

    For 'spreads' this returns a signed point where negative means the home team is favored.
    For 'totals' this returns a positive total value.

    Returns (consensus_point: float|None, favorite: str|None)
    """
    if not isinstance(event, dict):
        return None, None

    if market_type == 'spreads':
        home = event.get('home_team')
        away = event.get('away_team')
        if not home or not away:
            return None, None

        abs_points = []
        fav_votes = {home: 0, away: 0}
        spreads_key = market_key or 'spreads'

        for bookmaker in event.get('bookmakers', []):
            market = next((m for m in bookmaker.get('markets', []) if m.get('key') == spreads_key), None)
            if not market:
                continue
            for outcome in market.get('outcomes', []):
                if 'point' not in outcome or outcome['point'] is None:
                    continue
                try:
                    p = float(outcome['point'])
                except Exception:
                    continue
                normalized = round(p * 2) / 2.0
                abs_points.append(abs(normalized))

        if not abs_points:
            return None, None

        counts = {}
        for p in abs_points:
            counts[p] = counts.get(p, 0) + 1

        max_count = max(counts.values())
        mode_candidates = [p for p, c in counts.items() if c == max_count]
        mode_point = min(mode_candidates)

        for bookmaker in event.get('bookmakers', []):
            market = next((m for m in bookmaker.get('markets', []) if m.get('key') == spreads_key), None)
            if not market:
                continue
            for outcome in market.get('outcomes', []):
                if 'point' not in outcome or outcome['point'] is None:
                    continue
                try:
                    p = float(outcome['point'])
                except Exception:
                    continue
                normalized = round(p * 2) / 2.0
                if abs(normalized) != mode_point:
                    continue
                if normalized < 0:
                    name = outcome.get('name', '')
                    if name == home or home in name:
                        fav_votes[home] += 1
                    elif name == away or away in name:
                        fav_votes[away] += 1

        favorite = None
        if fav_votes[home] > fav_votes[away]:
            favorite = home
        elif fav_votes[away] > fav_votes[home]:
            favorite = away

        if favorite == home:
            return -mode_point, favorite
        if favorite == away:
            return mode_point, favorite
        return mode_point, None

    if market_type == 'totals':
        pts = []
        wts = []
        for bookmaker in event.get('bookmakers', []):
            market = next((m for m in bookmaker.get('markets', []) if m.get('key') == 'totals'), None)
            if not market:
                continue
            weight = pinnacle_weight if bookmaker.get('key') == 'pinnacle' else 1
            for outcome in market.get('outcomes', []):
                if 'point' in outcome and outcome['point'] is not None:
                    try:
                        p = abs(float(outcome['point']))
                    except Exception:
                        continue
                    pts.append(p)
                    wts.append(weight)

        if pts and wts and sum(wts) > 0:
            weighted_avg = sum(p * w for p, w in zip(pts, wts)) / sum(wts)
            target_point = round(weighted_avg * 2) / 2.0
            return target_point, None

    return None, None


if __name__ == '__main__':
    
    step_value = 5
    total_steps = 5

    start_date = datetime(2020, 10, 30, 12)
    step = timedelta(days=step_value)
    end_date = start_date + total_steps * step
    for date in date_range(start_date, end_date, step):
        print(date)
    
    start_date_str = start_date.strftime('%Y-%m-%dT%H:%M:%SZ')
    step_str = f'{step_value} days'
    end_date_str = end_date.strftime('%Y-%m-%dT%H:%M:%SZ')
    for date in date_range(start_date_str, end_date_str, step_str):
        print(date)
