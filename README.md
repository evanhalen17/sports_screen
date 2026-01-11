# Sports Screen - Odds & Edge Tracker

A PyQt6-based desktop application for tracking and analyzing sports betting odds across multiple sportsbooks. Built to help identify arbitrage opportunities and calculate optimal bet sizing using the Kelly Criterion.

## Features

- **Multi-Sportsbook Odds Tracking**: Aggregates odds from 40+ sportsbooks including BetMGM, FanDuel, DraftKings, BetRivers, Bovada, and more
- **Real-time Odds Updates**: Fetches current odds from The Odds API with support for multiple regions (US, UK, EU, AU)
- **Kelly Criterion Calculator**: Calculates optimal bet sizing based on probability and odds to maximize long-term growth
- **Odds Conversion**: Converts between different odds formats (Decimal, American, Fractional, Probability)
- **Multi-Sport Support**: Tracks odds for various sports including NFL, NBA, MLB, soccer, and more
- **Dark/Light Theme UI**: Customizable interface with dark and light color palettes
- **Responsive GUI**: Built with PyQt6 for a native desktop experience
- **Timezone Handling**: Automatic conversion to Eastern Time for event times

## Project Structure

```
sports_screen/
├── src/
│   ├── sports_screen.py      # Main PyQt6 GUI application
│   ├── the_odds_api.py       # Odds API client wrapper
│   ├── config.py             # Configuration and settings
│   └── utils.py              # Utility functions (Kelly criterion, odds conversion, etc.)
├── data/
│   └── API/
│       ├── key.env           # API keys (do not commit)
│       └── Kalshi_Read.txt    # Kalshi API documentation/reference
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
   - Copy `.env.example` to `.env` (or create `data/API/key.env`)
   - Add your API keys:
     ```
     RAPIDAPI_KEY=your_rapidapi_key
     THEODDSAPI_KEY_TEST=your_test_key
     THEODDSAPI_KEY_PROD=your_production_key
     KALSHIAPI_KEY=your_kalshi_key
     ```

## Usage

Run the application from the project root:

```bash
python src/sports_screen.py
```

### Main Window

- **Sportsbook Selection**: Choose which sportsbooks to display odds from
- **Odds Format**: View odds in Decimal, American, or Fractional format
- **Kelly Criterion**: Input probability estimates to calculate optimal bet sizing
- **Theme Toggle**: Switch between dark and light UI themes

## API Keys

This application uses the following APIs:

- **The Odds API** (https://the-odds-api.com/) - Primary source for sports betting odds
  - Free tier available (limited requests)
  - Supports 40+ sportsbooks across multiple regions
  
- **Kalshi API** - Additional market data (optional)

- **RapidAPI** - Secondary data source (optional)

Get your API keys from their respective websites and add them to your `.env` file.

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
- **Fractional** (1/2, 3/1, etc.)
- **Probability** (0.0 - 1.0)

## Dependencies

Major dependencies include:
- **PyQt6** - GUI framework
- **requests** - HTTP library for API calls
- **python-dotenv** - Environment variable management
- **pandas** - Data manipulation
- **numpy** - Numerical computing
- **rich** - Terminal formatting
- **pytz** - Timezone handling

See `requirements.txt` for the complete list.

## Development

### Running in Development Mode

The application is designed to work with both test and production API keys. By default, it uses the test key when first launched.

### Data Storage

- Raw odds data can be saved to `data/raw/`
- API responses are cached in JSON format
- Last pull timestamp is stored in `data/API/last_pulled.json`

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
