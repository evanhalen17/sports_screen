# Sports Screen - Odds & Edge Tracker

A PyQt6 desktop application for tracking and analyzing sports betting odds across multiple sportsbooks. Built to compare lines, surface consensus odds, and size bets using the Kelly Criterion.

## Features

- **Current + Futures Odds**: Dedicated views for live/upcoming games and outrights
- **Multi-Sportsbook Board**: Compare selected sportsbooks side by side with icon headers
- **Consensus + Edge**: Pinnacle-weighted consensus odds, edge, and best-book highlighting
- **Spread Consensus by Mode**: Uses alternate spreads to normalize lines and compare apples-to-apples
- **Odds Format Toggle**: Live switching between American, Decimal, and Probability
- **Kelly Bet $ Sizing**: Kelly output shown as a dollar amount based on each book’s bankroll
- **Pre-Game / Live Filter**: Filter events by commence time with live counts
- **Export CSV**: Quick export of the current table
- **Themes + Preferences**: Dark/light themes and persisted user settings

## Project Structure

```
sports_screen/
├── src/
│   ├── sports_screen.py      # Main PyQt6 GUI application
│   ├── the_odds_api.py       # Odds API client wrapper
│   ├── config.py             # Configuration and settings
│   └── utils.py              # Utility functions (Kelly criterion, odds conversion, etc.)
├── data/
│   ├── API/
│   │   └── key.env           # API keys (do not commit)
│   ├── sportsbook_svgs/       # Sportsbook icons
│   └── user_prefs.json        # Saved preferences (auto-generated)
├── env/                       # Python virtual environment
└── requirements.txt           # Project dependencies
```

## Installation

### Prerequisites
- Python 3.10+ (tested with 3.12)
- pip (Python package manager)

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/sports_screen.git
   cd sports_screen
   ```

2. **Create and activate virtual environment**
   ```bash
   # Windows
   python -m venv env
   .\env\Scripts\activate
   
   # macOS/Linux
   python3 -m venv env
   source env/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure API Keys**
   - Create `data/API/key.env`
   - Add your Odds API keys:
     ```
     THEODDSAPI_KEY_TEST=your_test_key
     THEODDSAPI_KEY_PROD=your_production_key
     ```

5. **Create user preferences file**
   - Copy `data/user_prefs.example.json` to `data/user_prefs.json`

## Usage

Run the application from the project root:

```bash
python src/sports_screen.py
```

### Main Window

- **Set Up User Sportsbooks**: Select display books and enter bankrolls (leave $0 for display-only)
- **Monitor Current Odds**: Live board with filters, search, and export
- **Review Historical Betslips**: Placeholder for future functionality
- **Quick Start**: Opens current odds using saved preferences

### Current Odds Window

- **Filters**: Sport, Market (Moneyline/Spreads/Totals), Period, Pre‑Game/Live
- **Odds Type**: American, Decimal, Probability
- **Quick Actions**: Refresh, Export CSV, Reset Filters
- **Consensus**: Pinnacle-weighted consensus; spreads use alternate_spreads to align lines

### Futures Odds Window

- **Filters**: Sport, Pre‑Game/Live, Odds Type
- **Quick Actions**: Refresh, Export CSV, Reset Filters

## API Keys

This application uses **The Odds API** (https://the-odds-api.com/) as its data source.
Get your keys from the Odds API dashboard and add them to `data/API/key.env`.

## Key Functions

### Kelly Criterion
Calculates the optimal fraction of your bankroll to wager:
```python
kelly_fraction = (b * p - q) / b
```
Where:
- `p` = probability of winning
- `q` = probability of losing (1 - p)
- `b` = decimal odds - 1

### Odds Conversion
Supports conversion between:
- **Decimal** (1.50, 2.00, etc.)
- **American** (-110, +150, etc.)
- **Probability** (0.0 - 1.0)

## Dependencies

Major dependencies include:
- **PyQt6** - GUI framework
- **requests** - HTTP library for API calls
- **python-dotenv** - Environment variable management
- **rich** - Terminal formatting
- **pytz/zoneinfo** - Timezone handling

See `requirements.txt` for the complete list.

## Development

### Data Storage

- Preferences are saved to `data/user_prefs.json`

## Supported Sportsbooks

The application supports odds from 40+ sportsbooks including:
- US: BetMGM, FanDuel, DraftKings, BetRivers, Bovada, Pinnacle, and more
- UK: Betfair, Sky Bet, Ladbrokes, William Hill, and more
- EU: Unibet, Betsson, and more
- AU: Sportsbet, TAB, Pointsbet, and more

## License

[Add your license here - MIT, Apache 2.0, GPL, etc.]

## Contributing

[Add contribution guidelines if applicable]

## Author

Created for sports betting odds analysis and arbitrage opportunity identification.

## Disclaimer

This tool is for educational and research purposes. Always verify odds and calculations independently. Sports betting involves risk of financial loss. Please gamble responsibly and in compliance with all applicable laws in your jurisdiction.
