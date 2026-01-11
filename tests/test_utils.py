import pytest
from src.utils import fetch_event_ids_for_sports, get_all_event_ids_flat, compute_consensus_point


class DummyAPI:
    def __init__(self, events_map):
        self._events_map = events_map

    def get_sports(self):
        return [{'key': k, 'title': k} for k in self._events_map.keys()]

    def get_events(self, sport, commence_time_from=None, commence_time_to=None):
        return self._events_map.get(sport, [])


def make_event_with_spreads(home, away, outcomes_by_bookmaker):
    bookies = []
    for bk_key, outcomes in outcomes_by_bookmaker.items():
        bookies.append({'key': bk_key, 'markets': [{'key': 'spreads', 'outcomes': outcomes}]})
    return {'home_team': home, 'away_team': away, 'bookmakers': bookies}


def make_event_with_totals(outcomes_by_bookmaker):
    bookies = []
    for bk_key, outcomes in outcomes_by_bookmaker.items():
        bookies.append({'key': bk_key, 'markets': [{'key': 'totals', 'outcomes': outcomes}]})
    return {'bookmakers': bookies}


def test_fetch_event_ids_for_sports_and_flat(tmp_path):
    events_map = {
        'sport_a': [
            {'id': 'a1'},
            {'id': 'a2'},
        ],
        'sport_b': [
            {'id': 'b1'},
            {'id': 'b2'},
            {'id': 'a2'},
        ]
    }
    api = DummyAPI(events_map)
import pytest
from src.utils import fetch_event_ids_for_sports, get_all_event_ids_flat, compute_consensus_point


class DummyAPI:
    def __init__(self, events_map):
        self._events_map = events_map

    def get_sports(self):
        return [{'key': k, 'title': k} for k in self._events_map.keys()]

    def get_events(self, sport, commence_time_from=None, commence_time_to=None):
        return self._events_map.get(sport, [])


def make_event_with_spreads(home, away, outcomes_by_bookmaker):
    bookies = []
    for bk_key, outcomes in outcomes_by_bookmaker.items():
        bookies.append({'key': bk_key, 'markets': [{'key': 'spreads', 'outcomes': outcomes}]})
    return {'home_team': home, 'away_team': away, 'bookmakers': bookies}


def make_event_with_totals(outcomes_by_bookmaker):
    bookies = []
    for bk_key, outcomes in outcomes_by_bookmaker.items():
        bookies.append({'key': bk_key, 'markets': [{'key': 'totals', 'outcomes': outcomes}]})
    return {'bookmakers': bookies}


def test_fetch_event_ids_for_sports_and_flat(tmp_path):
    events_map = {
        'sport_a': [
            {'id': 'a1'},
            {'id': 'a2'},
        ],
        'sport_b': [
            {'id': 'b1'},
            {'id': 'b2'},
            {'id': 'a2'},
        ]
    }
    api = DummyAPI(events_map)

    cache_file = str(tmp_path / 'cache.json')
    mapping = fetch_event_ids_for_sports(api, sport_keys=list(events_map.keys()), cache_ttl=1, cache_file=cache_file)
    assert isinstance(mapping, dict)
    assert set(mapping.keys()) == set(events_map.keys())
    assert mapping['sport_a'] == ['a1', 'a2']

    flat = get_all_event_ids_flat(api, sport_keys=list(events_map.keys()), cache_ttl=1, cache_file=cache_file)
    assert sorted(flat) == sorted(['a1', 'a2', 'b1', 'b2'])


def test_compute_consensus_spreads():
    ev = make_event_with_spreads('Home', 'Away', {
        'dk': [{'name': 'Home', 'point': -3}, {'name': 'Away', 'point': 3}],
        'pinnacle': [{'name': 'Home', 'point': -3.5}, {'name': 'Away', 'point': 3.5}],
        'other': [{'name': 'Home', 'point': -2.5}, {'name': 'Away', 'point': 2.5}],
    })
    cp, fav = compute_consensus_point(ev, 'spreads')
    assert fav == 'Home'
    assert cp is not None
    assert float(cp) < 0


def test_compute_consensus_totals():
    ev = make_event_with_totals({
        'dk': [{'name': 'Over', 'point': 48}, {'name': 'Under', 'point': 48}],
        'pinnacle': [{'name': 'Over', 'point': 49}, {'name': 'Under', 'point': 49}],
        'other': [{'name': 'Over', 'point': 47.5}, {'name': 'Under', 'point': 47.5}],
    })
    cp, fav = compute_consensus_point(ev, 'totals')
    assert fav is None
    assert cp is not None
    assert 47 < cp < 50