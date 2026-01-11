#! .\SportsbookOdds\env\Scripts\python.exe

import os
import json
import re
from typing import Generator, Union
from datetime import datetime, timedelta
import pytz

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

def convert_to_eastern(utc_timestamp: str) -> str:
    """Converts a UTC timestamp to Eastern Time (ET) and formats it for tabular display."""
    utc_zone = pytz.timezone("UTC")
    eastern_zone = pytz.timezone("America/New_York")

    # Parse the UTC timestamp
    utc_time = datetime.strptime(utc_timestamp, "%Y-%m-%dT%H:%M:%SZ")
    utc_time = utc_zone.localize(utc_time)

    # Convert to Eastern Time
    eastern_time = utc_time.astimezone(eastern_zone)

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
    return f"""
    QMainWindow {{
        background-color: {palette['background-dark']};
        color: {palette['table-row-alt1']};
    }}

    QTableWidget {{
        background-color: {palette['table-row-alt1']};
        alternate-background-color: {palette['table-row-alt2']};
        gridline-color: #444;
        color: {palette['text-light']};
        selection-background-color: {palette['text-light']};
        selection-color: {palette['text-dark']};
        border: 1px solid #555;
    }}

    QTableWidget::item {{
        padding: 5px;
        border: 0px;
    }}

    QTableWidget::item:hover {{
        background-color: {palette['table-row-hover']};
        color: {palette['text-light']};
    }}

    QTableWidget::item:selected {{
        background-color: {palette['text-light']};
        color: {palette['text-dark']};
    }}

    QHeaderView::section {{
        background-color: {palette['table-hdr-dark']};
        color: {palette['text-light']};
        padding: 5px;
        border: 1px solid #444;
        font-weight: bold;
    }}

    QComboBox {{
        background-color: {palette['table-hdr-dark']};
        color: {palette['text-light']};
        border: 1px solid #444;
        padding: 3px;
        border-radius: 4px;
        font-size: 14px;
    }}

    QComboBox:hover {{
        background-color: {palette['combobox-hover']}
    }}

    QLabel {{
        color: {palette['text-light']};
        font-size: 20px;
        font-weight: bold;
    }}

    QPushButton {{
        background-color: {palette['table-hdr-dark']};
        color: {palette['text-light']};
        border: 1px solid #555;
        padding: 6px;
        border-radius: 4px;
        font-size: 14px;
        font-weight: bold;
    }}

    QPushButton:hover {{
        background-color: {palette['combobox-hover']};
    }}
    """

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