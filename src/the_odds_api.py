#! .\SportsbookOdds\env\Scripts\python.exe

from config import THEODDSAPI_KEY_TEST
import requests
from utils import remove_none_values
from rich import print

VALID_SPORTSBOOKS = {
    'betonlineag', 'betmgm', 'betrivers', 'betus', 'bovada', 'williamhill_us',
    'draftkings', 'fanduel', 'lowvig', 'mybookieag', 'ballybet', 'betanysports',
    'betparx', 'espnbet', 'fliff', 'hardrockbet', 'windcreek', 'sport888',
    'betfair_ex_uk', 'betfair_sb_uk', 'betvictor', 'betway', 'boylesports', 'casumo',
    'coral', 'grosvenor', 'ladbrokesuk', 'leovegas', 'livescorebet', 'matchbook',
    'paddypower', 'skybet', 'smarkets', 'unibet_uk', 'virginbet', 'williamhill',
    'onexbet', 'betclic', 'betfair_ex_eu', 'betsson', 'coolbet', 'marathonbet',
    'everygame', 'gtbets', 'livescorebet_eu', 'nordicbet', 'pinnacle', 'suprabets',
    'tipico_de', 'unibet_eu', 'betfair_ex_au', 'betr_au', 'betright', 'ladbrokes_au',
    'neds', 'playup', 'pointsbetau', 'sportsbet', 'tab', 'tabtouch',
    'topsport', 'unibet'
}

VALID_REGIONS = {
    'us', 'us2', 'uk', 'eu', 'au'
}

class OddsAPI:
    """
    Class to retrieve odds on multiple sports/events from The Odds API.
    """
    def __init__(self, api_key):
        """
        Initialize the OddsAPI client with the given API key.
        Args:
            api_key (str): Your Odds API key.
        """
        self.api_key = api_key
        self.base_url = "https://api.the-odds-api.com/v4"

    def _api_get(self, endpoint, params=None, timeout=10):
        """
        Generic method to send GET requests to the Odds API.

        Args:
            endpoint (str): The specific endpoint to hit (e.g., '/sports', '/sports/{sport}/odds').
            params (dict): Additional parameters to include in the request.
            timeout (int): Maximum time in seconds to wait for a response (default: 10 seconds).

        Returns:
            dict: JSON response from the API.
        """
        if params is None:
            params = {}
        params["apiKey"] = self.api_key  # Add the API key to parameters
        url = f"{self.base_url}{endpoint}"

        try:
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()  # Raise HTTPError for bad responses
            return response.json()
        except requests.exceptions.Timeout as exc:
            raise TimeoutError(f"Request to {url} timed out after {timeout} seconds.") from exc
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"An error occurred during the request: {exc}") from exc

    def get_sports(self):
        """
        Fetch a list of all available sports.
        Returns:
            dict: JSON response containing the list of sports.
        """
        return self._api_get("/sports")

    def get_odds(
            self,
            sport,
            regions="us",
            markets="h2h",
            date_format="iso",
            odds_format="decimal",
            event_ids=None,
            bookmakers=None,
            commence_time_from=None,
            commence_time_to=None,
            include_links=None,
            include_sids=None,
            include_bet_limits=None,
        ):
        """
        Fetch odds for a specific sport.

        Args:
            sport (str): The sport key (e.g., 'soccer_epl', 'basketball_nba').
            regions (str): Comma-separated list of regions (default: 'us').
            markets (str): Comma-separated list of betting markets (default: 'h2h').
            date_format (str): Date format ('iso', 'unix') (default: 'iso').
            odds_format (str): Odds format ('decimal', 'american') (default: 'decimal').
            event_ids (str, optional): Comma-separated game ids to filter.
            bookmakers (str, optional): Comma-separated list of bookmakers to filter.
            commence_time_from (str, optional): Filter for games starting on or after this ISO 8601 timestamp.
            commence_time_to (str, optional): Filter for games starting on or before this ISO 8601 timestamp.
            include_links (str, optional): Include bookmaker links ("true" or "false").
            include_sids (str, optional): Include source ids ("true" or "false").
            include_bet_limits (str, optional): Include bet limits ("true" or "false").

        Returns:
            dict: JSON response containing odds data.
        """
        params = {
            "regions": regions,
            "markets": markets,
            "dateFormat": date_format,
            "oddsFormat": odds_format,
            "eventIds": event_ids,
            "bookmakers": bookmakers,
            "commenceTimeFrom": commence_time_from,
            "commenceTimeTo": commence_time_to,
            "includeLinks": include_links,
            "includeSids": include_sids,
            "includeBetLimits": include_bet_limits,
        }

        # Use helper function to remove None values
        params = remove_none_values(params)

        return self._api_get(f"/sports/{sport}/odds", params=params)

    def get_scores(
            self,
            sport,
            days_from=None,
            date_format="iso",
            event_ids=None,
        ):
        """
        Fetch scores for a specific sport.

        Args:
            sport (str): The sport key (e.g., 'soccer_epl', 'basketball_nba').
            days_from (int, optional): The number of days in the past to return completed games (1 to 3).
            date_format (str): Date format ('iso', 'unix') (default: 'iso').
            event_ids (str, optional): Comma-separated game ids to filter.

        Returns:
            dict: JSON response containing scores data.
        """
        params = {
            "daysFrom": days_from,
            "dateFormat": date_format,
            "eventIds": event_ids,
        }

        # Use helper function to remove None values
        params = remove_none_values(params)

        return self._api_get(f"/sports/{sport}/scores", params=params)

    def get_events(
            self,
            sport,
            date_format="iso",
            event_ids=None,
            commence_time_from=None,
            commence_time_to=None,
        ):
        """
        Fetch events for a specific sport.

        Args:
            sport (str): The sport key (e.g., 'soccer_epl', 'basketball_nba').
            date_format (str): Date format ('iso', 'unix') (default: 'iso').
            event_ids (str, optional): Comma-separated game ids to filter.
            commence_time_from (str, optional): Filter for games starting on or after this ISO 8601 timestamp.
            commence_time_to (str, optional): Filter for games starting on or before this ISO 8601 timestamp.

        Returns:
            dict: JSON response containing events data.
        """
        params = {
            "dateFormat": date_format,
            "eventIds": event_ids,
            "commenceTimeFrom": commence_time_from,
            "commenceTimeTo": commence_time_to,
        }

        # Use helper function to remove None values
        params = remove_none_values(params)

        return self._api_get(f"/sports/{sport}/events", params=params)

    def get_event_odds(
            self,
            sport,
            event_id,
            regions="us",
            markets="h2h",
            date_format="iso",
            odds_format="decimal",
            bookmakers=None,
            include_links=None,
            include_sids=None,
            include_bet_limits=None,
        ):
        """
        Fetch odds for a specific event within a sport.

        Args:
            sport (str): The sport key (e.g., 'soccer_epl', 'basketball_nba').
            event_id (str): The ID of the event (e.g., obtained from the events endpoint).
            regions (str): Comma-separated list of regions (default: 'us').
            markets (str): Comma-separated list of betting markets (default: 'h2h').
            date_format (str): Date format ('iso', 'unix') (default: 'iso').
            odds_format (str): Odds format ('decimal', 'american') (default: 'decimal').
            bookmakers (str, optional): Comma-separated list of bookmakers to filter.
            include_links (str, optional): Include bookmaker links ("true" or "false").
            include_sids (str, optional): Include source ids ("true" or "false").
            include_bet_limits (str, optional): Include bet limits ("true" or "false").

        Returns:
            dict: JSON response containing odds data for the specific event.
        """
        params = {
            "regions": regions,
            "markets": markets,
            "dateFormat": date_format,
            "oddsFormat": odds_format,
            "bookmakers": bookmakers,
            "includeLinks": include_links,
            "includeSids": include_sids,
            "includeBetLimits": include_bet_limits,
        }

        # Use helper function to remove None values
        params = remove_none_values(params)

        # Construct the endpoint with sport and event ID
        return self._api_get(f"/sports/{sport}/events/{event_id}/odds", params=params)

    def get_historical_odds(
            self,
            sport,
            date,
            regions="us",
            markets="h2h",
            date_format="iso",
            odds_format="decimal",
            bookmakers=None,
            event_ids=None,
            include_links=None,
            include_sids=None,
            include_bet_limits=None,
        ):
        """
        Fetch historical odds for a specific sport.

        Args:
            sport (str): The sport key (e.g., 'soccer_epl', 'basketball_nba').
            date (str): The timestamp of the data snapshot in ISO 8601 format (e.g., '2021-10-18T12:00:00Z').
            regions (str): Comma-separated list of regions (default: 'us').
            markets (str): Comma-separated list of betting markets (default: 'h2h').
            date_format (str): Date format ('iso', 'unix') (default: 'iso').
            odds_format (str): Odds format ('decimal', 'american') (default: 'decimal').
            bookmakers (str, optional): Comma-separated list of bookmakers to filter.
            event_ids (str, optional): Comma-separated game ids to filter.
            include_links (str, optional): Include bookmaker links ("true" or "false").
            include_sids (str, optional): Include source ids ("true" or "false").
            include_bet_limits (str, optional): Include bet limits ("true" or "false").

        Returns:
            dict: JSON response containing historical odds data.
        """
        params = {
            "regions": regions,
            "markets": markets,
            "dateFormat": date_format,
            "oddsFormat": odds_format,
            "bookmakers": bookmakers,
            "eventIds": event_ids,
            "includeLinks": include_links,
            "includeSids": include_sids,
            "includeBetLimits": include_bet_limits,
            "date": date,  # The additional required date parameter
        }

        # Use helper function to remove None values
        params = remove_none_values(params)

        # Adjusted endpoint to avoid repeating "v4"
        return self._api_get(f"/historical/sports/{sport}/odds", params=params)

    def get_historical_events(
            self,
            sport,
            date,
            date_format="iso",
            event_ids=None,
            commence_time_from=None,
            commence_time_to=None,
        ):
        """
        Fetch historical events for a specific sport at a given timestamp.

        Args:
            sport (str): The sport key (e.g., 'soccer_epl', 'basketball_nba').
            date (str): The timestamp of the data snapshot in ISO 8601 format (e.g., '2021-10-18T12:00:00Z').
            date_format (str): Date format ('iso', 'unix') (default: 'iso').
            event_ids (str, optional): Comma-separated game ids to filter.
            commence_time_from (str, optional): Filter for games starting on or after this ISO 8601 timestamp.
            commence_time_to (str, optional): Filter for games starting on or before this ISO 8601 timestamp.

        Returns:
            dict: JSON response containing historical events data.
        """
        params = {
            "date": date,  # Required parameter
            "dateFormat": date_format,
            "eventIds": event_ids,
            "commenceTimeFrom": commence_time_from,
            "commenceTimeTo": commence_time_to,
        }

        # Use helper function to remove None values
        params = remove_none_values(params)

        # Endpoint for historical events
        return self._api_get(f"/historical/sports/{sport}/events", params=params)

    def get_historical_event_odds(
            self,
            sport,
            event_id,
            date,
            regions="us",
            markets="h2h",
            date_format="iso",
            odds_format="decimal",
            bookmakers=None,
            include_links=None,
            include_sids=None,
            include_bet_limits=None,
        ):
        """
        Fetch historical odds for a single event as they appeared at a specific timestamp.

        Args:
            sport (str): The sport key (e.g., 'soccer_epl', 'basketball_nba').
            event_id (str): The ID of the historical game.
            date (str): The timestamp of the data snapshot in ISO 8601 format (e.g., '2023-11-29T22:42:00Z').
            regions (str): Comma-separated list of regions (default: 'us').
            markets (str): Comma-separated list of betting markets (default: 'h2h').
            date_format (str): Date format ('iso', 'unix') (default: 'iso').
            odds_format (str): Odds format ('decimal', 'american') (default: 'decimal').
            bookmakers (str, optional): Comma-separated list of bookmakers to filter.
            include_links (str, optional): Include bookmaker links ("true" or "false").
            include_sids (str, optional): Include source ids ("true" or "false").
            include_bet_limits (str, optional): Include bet limits ("true" or "false").

        Returns:
            dict: JSON response containing historical odds data for the event.
        """
        params = {
            "regions": regions,
            "markets": markets,
            "dateFormat": date_format,
            "oddsFormat": odds_format,
            "bookmakers": bookmakers,
            "includeLinks": include_links,
            "includeSids": include_sids,
            "includeBetLimits": include_bet_limits,
            "date": date,  # Required parameter
        }

        # Use helper function to remove None values
        params = remove_none_values(params)

        # Endpoint for historical event odds
        return self._api_get(f"/historical/sports/{sport}/events/{event_id}/odds", params=params)

    def get_remaining_requests(self):
        """
        Fetch the number of API requests remaining in your current quota.

        Returns:
            int: The number of requests remaining, or None if the header is not present.
        """
        url = f"{self.base_url}/sports"  # A lightweight endpoint to check the headers
        params = {"apiKey": self.api_key}

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()  # Ensure the response is valid
            
            # Extract the 'x-requests-remaining' header and safely convert to integer
            remaining = response.headers.get("x-requests-remaining", "0")
            return int(float(remaining))  # Convert to float first, then to int
        except requests.exceptions.Timeout as exc:
            raise TimeoutError("Request timed out while fetching remaining requests.") from exc
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"An error occurred during the request: {exc}") from exc

if __name__ == "__main__":
    key = THEODDSAPI_KEY_TEST
    run_sports = [
        'americanfootball_nfl',
        'baseball_mlb',
        'basketball_nba',
        'icehockey_nhl'
    ]
    run_futures = [
        'americanfootball_nfl_super_bowl_winner',
        'baseball_mlb_world_series_winner',
        'basketball_nba_championship_winner',
        'icehockey_nhl_championship_winner'
    ]
    bookmakers = [
        'pinnacle',
        'fanduel',
        'draftkings',
        'espnbet',
        'betmgm',
        'williamhill_us',
        'fliff'
    ]
    bookmakers = ','.join(bookmakers)
    markets = 'h2h,spreads,totals'
    markets_futures = 'outrights'
    odds_api = OddsAPI(key)
    sports = odds_api.get_sports()
    print(sports)
    quit()
    futures = [i['key'] for i in sports if i['key'] in run_futures]
    sports = [i['key'] for i in sports if i['key'] in run_sports]
    odds = {}
    start_req = odds_api.get_remaining_requests()
    for sport in sports:
        odds[sport] = odds_api.get_odds(
            sport, markets=markets, bookmakers=bookmakers
        )
    # for sport in futures:
    #     odds[sport] = odds_api.get_odds(
    #         sport, markets=markets_futures, bookmakers=bookmakers
    #     )
    final_req = odds_api.get_remaining_requests()
    print(odds)
    print(f'Total request cost: {start_req - final_req}')