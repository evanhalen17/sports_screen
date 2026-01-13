#! .\SportsbookOdds\env\Scripts\python.exe

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget,
    QLabel, QScrollArea, QTableWidget, QTableWidgetItem,
    QHeaderView, QHBoxLayout, QCheckBox, QComboBox,
    QPushButton, QDoubleSpinBox, QDialog, QPlainTextEdit, QDialogButtonBox,
    QLineEdit, QButtonGroup
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QSize
from PyQt6.QtGui import QColor, QBrush, QFont, QFontMetrics
import sys
from the_odds_api import OddsAPI
from config import (
    PALETTE, PALETTES, THEODDSAPI_KEY_TEST, THEODDSAPI_KEY_PROD, ODDS_FORMAT
)
from utils import (
    kelly_criterion,
    odds_converter,
    set_stylesheet,
    convert_to_eastern,
    get_all_event_ids_flat,
    fetch_event_ids_for_sports,
    compute_consensus_point,
    load_user_prefs,
    save_user_prefs,
)
from rich import print


class EventDetailsDialog(QDialog):
    def __init__(self, parent=None, content: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Event Details")
        self.setMinimumSize(600, 400)
        layout = QVBoxLayout(self)
        self.editor = QPlainTextEdit(self)
        self.editor.setReadOnly(True)
        self.editor.setPlainText(content or "No details available.")
        layout.addWidget(self.editor)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, self)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class StartupWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Odds and Edge")
        self.setGeometry(100, 100, 600, 400)

        self.sportsbook_mapping = {
            "betonlineag": "BetOnline.ag",
            "betmgm": "BetMGM",
            "betrivers": "BetRivers",
            "betus": "BetUS",
            "bovada": "Bovada",
            "williamhill_us": "Caesars",
            "draftkings": "DraftKings",
            "fanatics": "Fanatics",
            "fanduel": "FanDuel",
            "kalshi": "Kalshi",
            "lowvig": "LowVig.ag",
            "mybookieag": "MyBookie.ag",
            "ballybet": "Bally Bet",
            "espnbet": "ESPN BET",
            "pointsbet": "PointsBet",
            "pinnacle": "Pinnacle",
            "prophetx": "ProphetX"
        }

        self.selected_accounts = {}
        self.display_sportsbooks = []

        # Central widget and layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)
        self.central_widget.setLayout(main_layout)

        self.welcome_label = QLabel("Welcome to Odds and Edge", self)
        self.welcome_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        main_layout.addWidget(self.welcome_label)

        self.user_sportsbooks_button = QPushButton("Set Up User Sportsbooks", self)
        self.user_sportsbooks_button.clicked.connect(self.open_user_sportsbook_selection)
        main_layout.addWidget(self.user_sportsbooks_button)

        self.current_odds_button = QPushButton("Monitor Current Odds", self)
        self.current_odds_button.clicked.connect(self.open_current_odds)
        main_layout.addWidget(self.current_odds_button)

        # Quick Start: jump straight into Current Odds with saved or sensible defaults
        self.quick_start_button = QPushButton("Quick Start", self)
        self.quick_start_button.setToolTip("Open Current Odds using saved preferences or popular sportsbooks")
        self.quick_start_button.clicked.connect(self.quick_start)
        main_layout.addWidget(self.quick_start_button)

        self.historical_analysis_button = QPushButton("Review Historical Betslips", self)
        self.historical_analysis_button.clicked.connect(self.open_historical_analysis)
        main_layout.addWidget(self.historical_analysis_button)

        # Theme selector
        self.theme_dropdown = QComboBox(self)
        self.theme_dropdown.addItems(['dark', 'light'])
        try:
            prefs = load_user_prefs()
            current_theme = prefs.get('theme', 'dark') if isinstance(prefs, dict) else 'dark'
            idx = 0 if current_theme == 'dark' else 1
            self.theme_dropdown.setCurrentIndex(idx)
        except Exception:
            pass
        self.theme_dropdown.currentTextChanged.connect(self.change_theme)
        main_layout.addWidget(self.theme_dropdown)

    def open_user_sportsbook_selection(self):
        self.user_sportsbook_window = UserSportsbookSelectionWindow(self.sportsbook_mapping)
        self.user_sportsbook_window.show()
        self.user_sportsbook_window.save_button.clicked.connect(self.save_user_accounts)

    def save_user_accounts(self):
        self.selected_accounts, self.display_sportsbooks = self.user_sportsbook_window.get_selections()
        print("User Sportsbook Accounts Saved:", self.selected_accounts)
        print("Display Sportsbooks Selected:", self.display_sportsbooks)

    def open_current_odds(self):
        if not self.selected_accounts:
            print("Error: User sportsbooks must be set up before viewing current odds.")
            return

        self.sport_selection_window = SportSelectionWindow(self.sportsbook_mapping, self.selected_accounts, self.display_sportsbooks)
        self.sport_selection_window.show()
        self.close()

    def open_historical_analysis(self):
        self.historical_analysis_window = HistoricalAnalysisWindow()
        self.historical_analysis_window.show()
        self.close()

    def quick_start(self):
        """Open CurrentOddsWindow using saved prefs or sensible defaults."""
        try:
            prefs = load_user_prefs()
        except Exception:
            prefs = {}

        selected_accounts = prefs.get('selected_accounts', {}) if isinstance(prefs, dict) else {}
        display_sportsbooks = prefs.get('display_sportsbooks', []) if isinstance(prefs, dict) else []

        # sensible defaults if nothing saved
        if not display_sportsbooks:
            display_sportsbooks = ['draftkings', 'fanduel', 'betmgm', 'pinnacle', 'betrivers']

        # choose a default sport (first non-futures if possible)
        try:
            sports = odds_api.get_sports() or []
            default_sport = None
            last_sport = prefs.get('last_sport') if isinstance(prefs, dict) else None
            if last_sport:
                last_match = next(
                    (s for s in sports if s.get('key') == last_sport and not s.get('has_outrights')),
                    None
                )
                if last_match:
                    default_sport = last_match['key']
            if default_sport is None:
                for s in sports:
                    if not s.get('has_outrights'):
                        default_sport = s['key']
                        break
            if default_sport is None and sports:
                default_sport = sports[0]['key']
        except Exception:
            default_sport = None

        if default_sport:
            self.current_odds_window = CurrentOddsWindow([default_sport], selected_accounts, self.sportsbook_mapping, display_sportsbooks)
            self.current_odds_window.show()
            # persist last chosen sport/market for future quick starts
            try:
                if not isinstance(prefs, dict):
                    prefs = {}
                prefs['last_sport'] = default_sport
                prefs['display_sportsbooks'] = display_sportsbooks
                save_user_prefs(prefs)
            except Exception:
                pass
            self.close()
        else:
            print("Quick Start failed: could not determine a default sport.")

    def change_theme(self, theme_name: str):
        """Apply a new theme and persist the choice."""
        try:
            pal = PALETTES.get(theme_name, PALETTE)
            app = QApplication.instance()
            if app:
                app.setStyleSheet(set_stylesheet(pal))
            prefs = load_user_prefs()
            if not isinstance(prefs, dict):
                prefs = {}
            prefs['theme'] = theme_name
            save_user_prefs(prefs)
        except Exception as e:
            print(f"Failed to change theme: {e}")


class UserSportsbookSelectionWindow(QMainWindow):
    def __init__(self, sportsbook_mapping):
        super().__init__()
        self.setWindowTitle("User Sportsbook Selection")
        self.setGeometry(100, 100, 600, 400)

        self.sportsbook_mapping = sportsbook_mapping
        self.selected_accounts = {}
        self.display_sportsbooks = []

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)
        self.central_widget.setLayout(main_layout)

        self.label = QLabel("Select your sportsbooks and enter bankrolls (leave $0 for display-only):", self)
        main_layout.addWidget(self.label)

        self.scroll_area = QScrollArea(self)
        self.scroll_area_widget = QWidget()
        self.scroll_area_layout = QVBoxLayout(self.scroll_area_widget)

        self.sportsbook_widgets = {}
        for key, title in self.sportsbook_mapping.items():
            checkbox = QCheckBox(title, self)
            bankroll_input = QDoubleSpinBox(self)
            bankroll_input.setRange(0.0, 1000000.0)
            bankroll_input.setPrefix("$")
            bankroll_input.setDecimals(2)

            self.sportsbook_widgets[key] = (checkbox, bankroll_input)

            h_layout = QHBoxLayout()
            h_layout.addWidget(checkbox)
            h_layout.addWidget(bankroll_input)

            container = QWidget()
            container.setLayout(h_layout)
            self.scroll_area_layout.addWidget(container)

        self.scroll_area.setWidget(self.scroll_area_widget)
        self.scroll_area.setWidgetResizable(True)
        main_layout.addWidget(self.scroll_area)

        # Load saved user preferences (selected sportsbooks and bankrolls)
        try:
            prefs = load_user_prefs()
            saved_accounts = prefs.get('selected_accounts', {}) if isinstance(prefs, dict) else {}
            saved_display = prefs.get('display_sportsbooks', []) if isinstance(prefs, dict) else []
            for key, (checkbox, bankroll_input) in self.sportsbook_widgets.items():
                if key in saved_display:
                    checkbox.setChecked(True)
                if key in saved_accounts:
                    try:
                        bankroll_input.setValue(float(saved_accounts.get(key, 0)))
                    except Exception:
                        pass
        except Exception:
            pass

        self.select_all_button = QPushButton("Select All", self)
        self.select_all_button.clicked.connect(self.select_all)
        main_layout.addWidget(self.select_all_button)

        # Quick preset: select popular sportsbooks
        self.select_popular_button = QPushButton("Select Popular", self)
        self.select_popular_button.setToolTip("Check a preset of popular sportsbooks")
        self.select_popular_button.clicked.connect(self.select_popular)
        main_layout.addWidget(self.select_popular_button)

        self.deselect_all_button = QPushButton("Clear Selections", self)
        self.deselect_all_button.clicked.connect(self.deselect_all)
        main_layout.addWidget(self.deselect_all_button)

        self.save_button = QPushButton("Save", self)
        self.save_button.clicked.connect(self.save_selections)
        main_layout.addWidget(self.save_button)

    def select_all(self):
        for _, widget in self.sportsbook_widgets.items():
            widget[0].setChecked(True)
    
    def deselect_all(self):
        for _, widget in self.sportsbook_widgets.items():
            widget[0].setChecked(False)

    def select_popular(self):
        """Check a small preset list of popular sportsbooks and assign light default bankrolls."""
        popular = ['draftkings', 'fanduel', 'betmgm', 'pinnacle', 'betrivers']
        for key, (checkbox, bankroll_input) in self.sportsbook_widgets.items():
            if key in popular:
                checkbox.setChecked(True)
                # set a small default bankroll if currently zero
                try:
                    if bankroll_input.value() == 0:
                        bankroll_input.setValue(100.0)
                except Exception:
                    pass

    def save_selections(self):
        self.selected_accounts = {
            key: widget[1].value()
            for key, widget in self.sportsbook_widgets.items()
            if widget[0].isChecked() and widget[1].value() > 0
        }
        self.display_sportsbooks = [
            key for key, widget in self.sportsbook_widgets.items()
            if widget[0].isChecked()
        ]
        print("Saved Accounts:", self.selected_accounts)
        print("Display Sportsbooks:", self.display_sportsbooks)
        # Persist preferences for next session
        try:
            prefs = load_user_prefs()
            if not isinstance(prefs, dict):
                prefs = {}
            prefs['selected_accounts'] = self.selected_accounts
            prefs['display_sportsbooks'] = self.display_sportsbooks
            save_user_prefs(prefs)
        except Exception:
            pass
        self.close()

    def get_selections(self):
        return self.selected_accounts, self.display_sportsbooks


class SportSelectionWindow(QMainWindow):
    def __init__(self, sportsbook_mapping, selected_accounts, display_sportsbooks):
        super().__init__()
        self.setWindowTitle("Select Sports")
        self.setGeometry(100, 100, 600, 400)

        self.sportsbook_mapping = sportsbook_mapping
        self.selected_accounts = selected_accounts
        self.display_sportsbooks = display_sportsbooks
        self.selected_sports = []  # Allow multiple selections
        self.sport_mapping = {}
        self.has_outrights = {}

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)
        self.central_widget.setLayout(main_layout)

        self.label = QLabel("Select the sports you are interested in:", self)
        main_layout.addWidget(self.label)

        self.scroll_area = QScrollArea(self)
        self.scroll_area_widget = QWidget()
        self.scroll_area_layout = QVBoxLayout(self.scroll_area_widget)

        self.sports_checkboxes = []
        sports = self.fetch_sports()
        for sport in sports:
            checkbox = QCheckBox(sport['title'], self)
            checkbox.setChecked(False)
            self.sports_checkboxes.append(checkbox)
            self.sport_mapping[sport['title']] = sport['key']
            self.has_outrights[sport['key']] = sport['has_outrights']
            self.scroll_area_layout.addWidget(checkbox)

        self.scroll_area.setWidget(self.scroll_area_widget)
        self.scroll_area.setWidgetResizable(True)
        main_layout.addWidget(self.scroll_area)

        self.next_button = QPushButton("Next", self)
        self.next_button.clicked.connect(self.open_next_window)
        main_layout.addWidget(self.next_button)

        self.back_button = QPushButton("Back", self)
        self.back_button.clicked.connect(self.go_back)
        main_layout.addWidget(self.back_button)

    def fetch_sports(self):
        try:
            return odds_api.get_sports()
        except Exception as e:
            print(f"Error fetching sports: {e}")
            return []

    def open_next_window(self):
        selected_sport_titles = [
            cb.text() for cb in self.sports_checkboxes if cb.isChecked()
        ]
        if not selected_sport_titles:
            print("Error: No sports selected.")
            return

        self.selected_sports = [self.sport_mapping[title] for title in selected_sport_titles]

        futures_sports = [sport for sport in self.selected_sports if self.has_outrights[sport]]
        non_futures_sports = [sport for sport in self.selected_sports if not self.has_outrights[sport]]

        if futures_sports and non_futures_sports:
            print("Error: Cannot mix futures and non-futures sports.")
            return

        if futures_sports:
            self.futures_odds_window = FuturesOddsWindow(
                futures_sports, self.selected_accounts, self.sportsbook_mapping, self.display_sportsbooks
            )
            self.futures_odds_window.show()
        elif non_futures_sports:
            self.current_odds_window = CurrentOddsWindow(
                non_futures_sports, self.selected_accounts, self.sportsbook_mapping, self.display_sportsbooks
            )
            self.current_odds_window.show()
            try:
                prefs = load_user_prefs()
                if not isinstance(prefs, dict):
                    prefs = {}
                prefs['last_sport'] = non_futures_sports[0]
                save_user_prefs(prefs)
            except Exception:
                pass

            # start background fetch of event ids for the selected sports
            try:
                self._event_ids_worker = EventIdsWorker(odds_api, non_futures_sports)
                self._event_ids_worker.finished.connect(self._on_event_ids_fetched)
                self._event_ids_worker.start()
            except Exception as e:
                print(f"Failed to start event id worker: {e}")

        self.close()

    def go_back(self):
        self.startup_window = StartupWindow()
        self.startup_window.show()
        self.close()

    def _on_event_ids_fetched(self, mapping):
        try:
            if hasattr(self, 'current_odds_window') and self.current_odds_window:
                self.current_odds_window.set_event_ids_map(mapping)
        except Exception as e:
            print(f"Error applying fetched event ids: {e}")


class EventIdsWorker(QThread):
    """Background worker to fetch event id mappings for sports."""
    finished = pyqtSignal(dict)

    def __init__(self, odds_api, sport_keys, commence_time_from=None, commence_time_to=None, cache_ttl=300, cache_file=None):
        super().__init__()
        self.odds_api = odds_api
        self.sport_keys = sport_keys
        self.commence_time_from = commence_time_from
        self.commence_time_to = commence_time_to
        self.cache_ttl = cache_ttl
        self.cache_file = cache_file

    def run(self):
        try:
            mapping = fetch_event_ids_for_sports(
                self.odds_api,
                sport_keys=self.sport_keys,
                commence_time_from=self.commence_time_from,
                commence_time_to=self.commence_time_to,
                cache_ttl=self.cache_ttl,
                cache_file=self.cache_file,
            )
            # Emit the per-sport mapping directly: {sport_key: [event_ids]}
            self.finished.emit(mapping)
        except Exception:
            # Emit empty mapping on failure
            self.finished.emit({})

    def open_next_window(self):
        selected_sport_titles = [
            cb.text() for cb in self.sports_checkboxes if cb.isChecked()
        ]
        if not selected_sport_titles:
            print("Error: No sports selected.")
            return

        self.selected_sports = [self.sport_mapping[title] for title in selected_sport_titles]

        futures_sports = [sport for sport in self.selected_sports if self.has_outrights[sport]]
        non_futures_sports = [sport for sport in self.selected_sports if not self.has_outrights[sport]]

        if futures_sports and non_futures_sports:
            print("Error: Cannot mix futures and non-futures sports.")
            return

        if futures_sports:
            self.futures_odds_window = FuturesOddsWindow(
                futures_sports, self.selected_accounts, self.sportsbook_mapping, self.display_sportsbooks
            )
            self.futures_odds_window.show()
        elif non_futures_sports:
            self.current_odds_window = CurrentOddsWindow(
                non_futures_sports, self.selected_accounts, self.sportsbook_mapping, self.display_sportsbooks
            )
            self.current_odds_window.show()

            # start background fetch of event ids for the selected sports
            try:
                self._event_ids_worker = EventIdsWorker(odds_api, non_futures_sports)
                self._event_ids_worker.finished.connect(self._on_event_ids_fetched)
                self._event_ids_worker.start()
            except Exception as e:
                print(f"Failed to start event id worker: {e}")

        self.close()

    def go_back(self):
        self.startup_window = StartupWindow()
        self.startup_window.show()
        self.close()

    def _on_event_ids_fetched(self, mapping):
        try:
            if hasattr(self, 'current_odds_window') and self.current_odds_window:
                self.current_odds_window.set_event_ids_map(mapping)
        except Exception as e:
            print(f"Error applying fetched event ids: {e}")


class CurrentOddsWindow(QMainWindow):
    def __init__(self, selected_sports, selected_accounts, sportsbook_mapping, display_sportsbooks):
        super().__init__()
        self.setWindowTitle("Current Odds")
        self.setGeometry(100, 100, 1200, 800)

        self.selected_sports = selected_sports
        self.current_sport = selected_sports[0]  # Default to the first sport in the list
        self.selected_accounts = selected_accounts
        self.sportsbook_mapping = sportsbook_mapping
        self.display_sportsbooks = display_sportsbooks

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)
        self.central_widget.setLayout(main_layout)

        # Top selector bar (odds-first, compact)
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        # Sport Selection Dropdown
        self.sport_dropdown = QComboBox(self)
        self.sport_dropdown.addItems(self.selected_sports)
        self.sport_dropdown.currentTextChanged.connect(self.update_sport)
        top_bar.addWidget(self.sport_dropdown)

        # Market Selection Dropdown
        self.market_dropdown = QComboBox(self)
        self.market_dropdown.addItems(["h2h", "spreads", "totals"])
        self.market_dropdown.currentTextChanged.connect(self.update_table)
        top_bar.addWidget(self.market_dropdown)

        # Period Selection Dropdown (placeholder for future wiring)
        self.period_dropdown = QComboBox(self)
        self.period_dropdown.addItems(["Full Game"])
        top_bar.addWidget(self.period_dropdown)

        # Pre-Game / Live toggle (UI only for now)
        self.pregame_button = QPushButton("Pre-Game", self)
        self.pregame_button.setCheckable(True)
        self.live_button = QPushButton("Live", self)
        self.live_button.setCheckable(True)
        self.pregame_button.setChecked(True)
        self.live_toggle_group = QButtonGroup(self)
        self.live_toggle_group.setExclusive(True)
        self.live_toggle_group.addButton(self.pregame_button)
        self.live_toggle_group.addButton(self.live_button)
        top_bar.addWidget(self.pregame_button)
        top_bar.addWidget(self.live_button)

        top_bar.addStretch(1)

        # Search box (filters will be wired later)
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Search teams...")
        try:
            self.search_input.setClearButtonEnabled(True)
        except Exception:
            pass
        self.search_input.setMinimumWidth(200)
        top_bar.addWidget(self.search_input)

        # Odds format selector (UI only for now)
        self.odds_format_dropdown = QComboBox(self)
        self.odds_format_dropdown.addItems(["American", "Decimal", "Probability"])
        top_bar.addWidget(self.odds_format_dropdown)

        # Refresh button (moved to top bar)
        self.refresh_button = QPushButton("Refresh", self)
        self.refresh_button.clicked.connect(self.update_table)
        top_bar.addWidget(self.refresh_button)

        main_layout.addLayout(top_bar)

        # Status row (compact)
        status_row = QHBoxLayout()
        self.requests_remaining_label = QLabel("Requests Remaining: Retrieving...", self)
        status_row.addWidget(self.requests_remaining_label)

        # Event IDs load status
        self.event_ids_status_label = QLabel("Event IDs: Not loaded", self)
        status_row.addWidget(self.event_ids_status_label)
        status_row.addStretch(1)
        main_layout.addLayout(status_row)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)

        # Create a frozen table for the left-side columns (Event, Requery, Event Date, Outcome, Spread/Point, Hold)
        self.frozen_table = QTableWidget()
        self.frozen_table.setColumnCount(6)
        self.frozen_table.setHorizontalHeaderLabels(["Event", "Requery", "Event Date", "Outcome", "Spread", "Hold"])
        self.frozen_table.setAlternatingRowColors(True)
        self.frozen_table.verticalHeader().setVisible(False)
        self.frozen_table.setWordWrap(True)

        # Place frozen_table and main table side-by-side so frozen columns remain visible
        tables_layout = QHBoxLayout()
        tables_layout.addWidget(self.frozen_table)
        tables_layout.addWidget(self.table)
        main_layout.addLayout(tables_layout)

        self.update_table()

        # Selection sync guard
        self._syncing_selection = False
        # Enable row selection behavior and connect selection handlers
        try:
            self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
            self.frozen_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            self.frozen_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
            self.table.selectionModel().selectionChanged.connect(self._on_main_selection_changed)
            self.frozen_table.selectionModel().selectionChanged.connect(self._on_frozen_selection_changed)
            # Wire double-click to open event details
            try:
                self.table.cellDoubleClicked.connect(self._on_table_double_clicked)
                self.frozen_table.cellDoubleClicked.connect(self._on_frozen_double_clicked)
            except Exception:
                pass
        except Exception:
            pass

        # Requery toggle (persisted)
        try:
            prefs = load_user_prefs()
        except Exception:
            prefs = {}
        requery_default = prefs.get('enable_requery', True) if isinstance(prefs, dict) else True
        self.requery_checkbox = QCheckBox("Enable precise requery (uses API quota)", self)
        self.requery_checkbox.setChecked(bool(requery_default))
        self.requery_checkbox.setToolTip("When enabled, the app will re-query event-level odds for the consensus point (may consume API requests). Toggle to conserve quota.")
        self.requery_checkbox.toggled.connect(self._on_requery_toggled)
        main_layout.addWidget(self.requery_checkbox)

        # Legend explaining icons and consensus
        self.legend_label = QLabel("Legend: ⟳ = event-level requery used; Consensus = weighted odds (Pinnacle-weighted).", self)
        self.legend_label.setStyleSheet("font-size:11px;color:gray;")
        main_layout.addWidget(self.legend_label)

        button_layout = QHBoxLayout()
        self.back_button = QPushButton("Back to Sport Selection", self)
        self.back_button.clicked.connect(self.go_back)
        button_layout.addWidget(self.back_button)

        main_layout.addLayout(button_layout)

        self.update_requests_remaining()

    def update_sport(self, sport):
        self.current_sport = sport
        try:
            prefs = load_user_prefs()
            if not isinstance(prefs, dict):
                prefs = {}
            prefs['last_sport'] = sport
            save_user_prefs(prefs)
        except Exception:
            pass
        self.update_table()

    def update_table(self):
        self.table.clear()
        self.table.setRowCount(0)
        # clear cached row->event mapping
        self._row_event_map = []
        self._last_odds_data = None

        try:
            odds_data = self.fetch_odds_data()
            # cache fetched data for detail views
            self._last_odds_data = odds_data
            # If market is spreads or totals, compute consensus point per event and try
            # to fetch event-level odds for that exact point to make apples-to-apples comparisons.
            market_type = self.market_dropdown.currentText()
            if market_type in ('spreads', 'totals') and isinstance(odds_data, list):
                event_target_points = {}
                for event in odds_data:
                    cp, fav = compute_consensus_point(event, market_type)
                    if cp is not None:
                        # store rounded consensus and favorite (if any)
                        try:
                            event['_consensus_point'] = cp
                            if market_type == 'spreads':
                                # favorite is only meaningful for spreads
                                event['_consensus_favorite'] = fav
                        except Exception:
                            pass
                        event_target_points[event.get('id')] = cp

                # Check remaining requests and only proceed if we have enough quota
                try:
                    remaining = odds_api.get_remaining_requests()
                except Exception:
                    remaining = 0

                needed = len(event_target_points)
                # Respect user preference for requery
                try:
                    prefs = load_user_prefs()
                    enable_requery = prefs.get('enable_requery', True) if isinstance(prefs, dict) else True
                except Exception:
                    enable_requery = True

                if enable_requery and needed > 0 and remaining >= needed:
                    for event in odds_data:
                        eid = event.get('id')
                        if eid in event_target_points:
                            target = event_target_points[eid]
                            try:
                                ev_odds = odds_api.get_event_odds(
                                    self.current_sport,
                                    eid,
                                    markets='spreads',
                                    odds_format=ODDS_FORMAT,
                                    bookmakers=','.join(self.display_sportsbooks)
                                )
                                # ev_odds is expected to be a list with single event dict
                                if isinstance(ev_odds, list) and len(ev_odds) > 0:
                                    ev = ev_odds[0]
                                    for b in ev.get('bookmakers', []):
                                        orig_b = next((ob for ob in event.get('bookmakers', []) if ob.get('key') == b.get('key')), None)
                                        if not orig_b:
                                            continue
                                        ev_market = next((m for m in b.get('markets', []) if m.get('key') == 'spreads'), None)
                                        if not ev_market:
                                            continue
                                            # Filter outcomes to those matching the absolute target point (both sides)
                                            matched = [o for o in ev_market.get('outcomes', []) if 'point' in o and abs(abs(float(o.get('point', 0))) - abs(target)) < 1e-6]
                                        if matched:
                                            # replace original spreads outcomes with the exact-point ones
                                            orig_market = next((m for m in orig_b.get('markets', []) if m.get('key') == 'spreads'), None)
                                            if orig_market:
                                                orig_market['outcomes'] = matched
                                                # mark that we used an event-level requery for this event's spreads
                                                try:
                                                    event['_spread_method'] = 'requery'
                                                except Exception:
                                                    pass
                            except Exception as e:
                                print(f"Failed to fetch event-level odds for {eid}: {e}")

            self.process_odds_data(odds_data)
            self.add_headers()
            for event in odds_data:
                self.populate_table_rows(event)
            self.update_requests_remaining()
            self.table.resizeColumnsToContents()
            self._apply_row_heights()

            # UX polish: fix the first two columns (Event and Requery) to stable widths
            try:
                # Fix frozen table column widths so left-side info remains stable
                fheader = self.frozen_table.horizontalHeader()
                for ci in range(self.frozen_table.columnCount()):
                    fheader.setSectionResizeMode(ci, QHeaderView.Fixed)
                # reasonable widths
                # Event title
                try:
                    self.frozen_table.setColumnWidth(0, 300)
                    # Requery icon
                    self.frozen_table.setColumnWidth(1, 40)
                    # Event Date
                    self.frozen_table.setColumnWidth(2, 140)
                    # Outcome
                    self.frozen_table.setColumnWidth(3, 140)
                    # Spread/Point
                    self.frozen_table.setColumnWidth(4, 60)
                    # Hold
                    self.frozen_table.setColumnWidth(5, 70)
                except Exception:
                    pass
            except Exception:
                pass

            # Copy left-side columns into frozen_table and sync scrolling
            try:
                rows = self.table.rowCount()
                self.frozen_table.setRowCount(rows)
                for r in range(rows):
                    for c in range(6):
                        src_item = self.table.item(r, c)
                        if src_item:
                            new_item = QTableWidgetItem(src_item.text())
                            new_item.setTextAlignment(src_item.textAlignment())
                            try:
                                new_item.setForeground(src_item.foreground())
                            except Exception:
                                pass
                            try:
                                new_item.setFont(src_item.font())
                            except Exception:
                                pass
                            self.frozen_table.setItem(r, c, new_item)
                        else:
                            self.frozen_table.setItem(r, c, QTableWidgetItem(""))
                    try:
                        self.frozen_table.setRowHeight(r, self.table.rowHeight(r))
                    except Exception:
                        pass

                # Sync vertical scrolling
                self.table.verticalScrollBar().valueChanged.connect(self.frozen_table.verticalScrollBar().setValue)
                self.frozen_table.verticalScrollBar().valueChanged.connect(self.table.verticalScrollBar().setValue)
            except Exception:
                pass
            self._apply_row_heights()

        except Exception as e:
            print(f"Error updating table: {e}")

    def fetch_odds_data(self):
        response = odds_api.get_odds(
            sport=self.current_sport,
            markets=self.market_dropdown.currentText(),
            odds_format=ODDS_FORMAT,
            bookmakers=','.join(self.display_sportsbooks)
        )
        print(response)
        return response

    def process_odds_data(self, odds_data):
        for event in odds_data:
            for bookmaker in event['bookmakers']:
                for market in bookmaker['markets']:
                    total_prob = sum(
                        odds_converter(ODDS_FORMAT, "probability", outcome["price"])
                        for outcome in market["outcomes"]
                    )
                    for outcome in market["outcomes"]:
                        prob = odds_converter(ODDS_FORMAT, "probability", outcome["price"])
                        no_vig_prob = prob / total_prob if total_prob > 0 else 0
                        outcome["no_vig_price"] = odds_converter("probability", ODDS_FORMAT, no_vig_prob)

    def add_headers(self):
        # Dynamic label: show 'Point' for totals market, 'Spread' for spreads
        point_label = "Point" if self.market_dropdown.currentText() == 'totals' else "Spread"
        # Insert a small 'Requery' indicator column after Event to show event-level requery usage
        headers = ["Event", "Requery", "Event Date", "Outcome", point_label, "Hold", "Best Sportsbook", "Positive Edge", "Kelly Bet"] + [
            self.sportsbook_mapping[bookmaker]
            for bookmaker in self.display_sportsbooks
        ] + ["Consensus Odds"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        # Hide the left-side columns in the main table (they are shown in frozen_table)
        try:
            for i in range(6):
                self.table.hideColumn(i)
        except Exception:
            pass
        # Keep frozen table headers in sync (Point/Spread label)
        try:
            if self.frozen_table.horizontalHeaderItem(4):
                self.frozen_table.horizontalHeaderItem(4).setText(point_label)
        except Exception:
            pass
        # Improve header alignment and add helpful tooltips
        try:
            header = self.table.horizontalHeader()
            header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
            # Tooltip for Requery column (frozen table will show it)
            try:
                if self.frozen_table.horizontalHeaderItem(1):
                    self.frozen_table.horizontalHeaderItem(1).setToolTip("⟳ = event-level requery was used to fetch exact-point odds for apples-to-apples comparison")
            except Exception:
                pass
            # Tooltip and emphasis for Consensus Odds column in the right table
            consensus_col_idx = len(self.display_sportsbooks) + 9
            if consensus_col_idx < self.table.columnCount() and self.table.horizontalHeaderItem(consensus_col_idx):
                self.table.horizontalHeaderItem(consensus_col_idx).setToolTip("Consensus Odds: Pinnacle-weighted consensus across selected sportsbooks (no-vig normalized)")
                try:
                    hdr_item = self.table.horizontalHeaderItem(consensus_col_idx)
                    hdr_font = hdr_item.font()
                    hdr_font.setBold(True)
                    hdr_item.setFont(hdr_font)
                    hdr_item.setBackground(QBrush(QColor('#f0f0f0')))
                except Exception:
                    pass
        except Exception:
            pass

    def _on_requery_toggled(self, enabled: bool):
        try:
            prefs = load_user_prefs()
            if not isinstance(prefs, dict):
                prefs = {}
            prefs['enable_requery'] = bool(enabled)
            save_user_prefs(prefs)
        except Exception:
            pass

    def _on_main_selection_changed(self, selected, deselected):
        if self._syncing_selection:
            return
        try:
            self._syncing_selection = True
            sels = self.table.selectionModel().selectedRows()
            if sels:
                r = sels[0].row()
                self.frozen_table.selectRow(r)
            else:
                self.frozen_table.clearSelection()
        except Exception:
            pass
        finally:
            self._syncing_selection = False

    def _on_frozen_selection_changed(self, selected, deselected):
        if self._syncing_selection:
            return
        try:
            self._syncing_selection = True
            sels = self.frozen_table.selectionModel().selectedRows()
            if sels:
                r = sels[0].row()
                self.table.selectRow(r)
            else:
                self.table.clearSelection()
        except Exception:
            pass
        finally:
            self._syncing_selection = False
        # (Header synchronization handled in add_headers)

    def _desired_row_height(self) -> int:
        fm = QFontMetrics(self.table.font())
        market_key = None
        try:
            market_key = self.market_dropdown.currentText()
        except Exception:
            market_key = None
        if market_key in ('spreads', 'totals'):
            return max(fm.lineSpacing() * 3 + 12, 44)
        return max(fm.lineSpacing() * 2 + 6, 44)

    def _apply_row_heights(self):
        """Ensure rows are tall enough for stacked odds and keep tables in sync."""
        try:
            row_height = self._desired_row_height()
            vheader = self.table.verticalHeader()
            fvheader = self.frozen_table.verticalHeader()
            vheader.setSectionResizeMode(QHeaderView.Fixed)
            fvheader.setSectionResizeMode(QHeaderView.Fixed)
            vheader.setDefaultSectionSize(row_height)
            fvheader.setDefaultSectionSize(row_height)
            try:
                vheader.setMinimumSectionSize(row_height)
                vheader.setMaximumSectionSize(row_height)
                fvheader.setMinimumSectionSize(row_height)
                fvheader.setMaximumSectionSize(row_height)
            except Exception:
                pass
            for r in range(self.table.rowCount()):
                self.table.setRowHeight(r, row_height)
                self.frozen_table.setRowHeight(r, row_height)
        except Exception:
            pass

    def populate_table_rows(self, event):
        market_key = self.market_dropdown.currentText()

        # For spreads, iterate by team names to avoid mismatch due to point formatting differences
        if market_key == 'spreads':
            outcome_names = [event.get('home_team'), event.get('away_team')]
        else:
            # default behavior: use outcomes from first bookmaker/market
            first_bm = event['bookmakers'][0]
            first_market = first_bm['markets'][0]
            outcome_names = [o['name'] for o in first_market.get('outcomes', [])]

        for idx, outcome_name in enumerate(outcome_names):
            row = self.table.rowCount()
            self.table.insertRow(row)
            try:
                self.table.setRowHeight(row, self._desired_row_height())
            except Exception:
                pass
            try:
                # map this table row back to the source event id for detail views
                if not hasattr(self, '_row_event_map') or self._row_event_map is None:
                    self._row_event_map = []
                self._row_event_map.append(event.get('id'))
            except Exception:
                pass
            # Event column
            self.table.setItem(row, 0, QTableWidgetItem(f"{event['home_team']} vs {event['away_team']}"))
            # Requery indicator (will be filled later if requery used)
            self.table.setItem(row, 1, QTableWidgetItem(""))
            # Event Date
            self.table.setItem(row, 2, QTableWidgetItem(convert_to_eastern(event['commence_time'])))
            # Outcome
            self.table.setItem(row, 3, QTableWidgetItem(outcome_name))
            # Point/Spread column (compact, per-outcome). Show consensus point when available.
            spread_display = ""
            if market_key == 'spreads':
                cp = event.get('_consensus_point')
                fav = event.get('_consensus_favorite')
                if cp is not None:
                    try:
                        # For each outcome row, show numeric signed consensus point.
                        if fav:
                            if outcome_name == fav:
                                spread_display = f"-{abs(cp):.1f}"
                            else:
                                spread_display = f"+{abs(cp):.1f}"
                        else:
                            # pick 0.0 for pick'em
                            spread_display = f"{0:.1f}"
                    except Exception:
                        spread_display = str(cp)
            elif market_key == 'totals':
                cp = event.get('_consensus_point')
                if cp is not None:
                    try:
                        name_lower = outcome_name.lower()
                        if 'over' in name_lower:
                            suffix = 'o'
                        elif 'under' in name_lower:
                            suffix = 'u'
                        else:
                            # fallback by position: first -> over, second -> under
                            suffix = 'o' if idx == 0 else 'u'
                        if float(cp).is_integer():
                            pts = f"{int(cp)}"
                        else:
                            pts = f"{cp:.1f}"
                        spread_display = f"{pts}{suffix}"
                    except Exception:
                        spread_display = str(cp)

            probabilities = []
            weights = []
            method_used = event.get('_spread_method', 'native')

            # Compute average market hold across available books for this event/market
            hold_values = []
            for bm in event.get('bookmakers', []):
                market = next((m for m in bm.get('markets', []) if m.get('key') == market_key), None)
                if not market:
                    continue
                try:
                    total_prob = sum(
                        odds_converter(ODDS_FORMAT, 'probability', o.get('price'))
                        for o in market.get('outcomes', [])
                        if o.get('price') is not None
                    )
                    hold_values.append(max(total_prob - 1, 0))
                except Exception:
                    continue
            avg_hold = sum(hold_values) / len(hold_values) if hold_values else None

            for col, bookmaker_key in enumerate(self.display_sportsbooks, start=9):
                bookmaker = next((b for b in event.get('bookmakers', []) if b.get('key') == bookmaker_key), None)
                if bookmaker:
                    market = next((m for m in bookmaker.get('markets', []) if m.get('key') == market_key), None)
                    if market:
                        # Try to match by exact name first
                        outcome_data = next((o for o in market.get('outcomes', []) if o.get('name') == outcome_name), None)

                        # If not found and this is spreads, try to match by team substring
                        if outcome_data is None and market_key == 'spreads':
                            outcome_data = next((o for o in market.get('outcomes', []) if outcome_name in o.get('name', '')), None)

                        # If still not found, as a fallback normalize points to nearest 0.5 and pick closest
                        if outcome_data is None and market_key == 'spreads':
                            # attempt to find outcome with nearest point to consensus if available
                            pts = [o for o in market.get('outcomes', []) if 'point' in o and o.get('point') is not None]
                            if pts:
                                # choose one with smallest absolute point difference to 0 (prefer favorites/underdogs by name presence)
                                outcome_data = pts[0]
                                method_used = 'normalized'

                        if outcome_data:
                            price_display = outcome_data.get('price')
                            cell_text = str(price_display)
                            if market_key in ('spreads', 'totals'):
                                point = outcome_data.get('point')
                                if point is not None:
                                    try:
                                        pval = float(point)
                                        if market_key == 'spreads':
                                            point_text = f"{pval:+.1f}" if not pval.is_integer() else f"{pval:+.0f}"
                                        else:
                                            pval = abs(pval)
                                            point_text = f"{pval:.1f}" if not pval.is_integer() else f"{pval:.0f}"
                                    except Exception:
                                        point_text = str(point)
                                    cell_text = f"{point_text}\n{price_display}"
                            cell_item = QTableWidgetItem(cell_text)
                            cell_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                            if "\n" in cell_text:
                                try:
                                    cell_item.setSizeHint(QSize(0, self._desired_row_height()))
                                except Exception:
                                    pass
                            self.table.setItem(row, col, cell_item)

                            # populate spread_display from the first matching bookmaker outcome that has a 'point'
                            if spread_display == "" and market_key == 'spreads' and outcome_data.get('point') is not None:
                                pt = outcome_data.get('point')
                                # keep sign if present, else show absolute with + for positive
                                try:
                                    spread_display = ("+" + str(pt)) if float(pt) > 0 else str(pt)
                                except Exception:
                                    spread_display = str(pt)

                            # Use no_vig_price if precomputed, else compute probability directly
                            no_vig = outcome_data.get('no_vig_price') if 'no_vig_price' in outcome_data else None
                            if no_vig is not None:
                                probabilities.append(odds_converter(ODDS_FORMAT, 'probability', no_vig))
                            else:
                                try:
                                    prob = odds_converter(ODDS_FORMAT, 'probability', outcome_data.get('price'))
                                    probabilities.append(prob)
                                except Exception:
                                    pass

                            weight = 10 if bookmaker_key == 'pinnacle' else 1
                            weights.append(weight)

            # set Spread cell (compact) in column index 4 (Event, Requery, Event Date, Outcome, Spread)
            self.table.setItem(row, 4, QTableWidgetItem(spread_display))

            # Correct column alignment (after Event, Requery, Event Date, Outcome, Spread, Hold...)
            hold_col = 5
            best_sportsbook_col = 6
            edge_col = 7
            kelly_col = 8
            consensus_col = len(self.display_sportsbooks) + 9

            consensus_probability = None
            if probabilities and sum(weights) > 0:
                consensus_probability = sum(p * w for p, w in zip(probabilities, weights)) / sum(weights)
                consensus_odds = odds_converter('probability', ODDS_FORMAT, consensus_probability)
                self.table.setItem(row, consensus_col, QTableWidgetItem(f"{consensus_odds:.2f}"))
            else:
                self.table.setItem(row, consensus_col, QTableWidgetItem("N/A"))

            # Calculate Positive Edge and Kelly Bet based on user-selected sportsbooks
            best_sportsbook = None
            best_edge = -float('inf')
            best_kelly = 0

            if consensus_probability is not None:
                for account_key in self.selected_accounts:
                    user_market = next(
                        (m for b in event.get('bookmakers', []) if b.get('key') == account_key for m in b.get('markets', []) if m.get('key') == market_key),
                        None
                    )
                    if user_market:
                        # match user outcome similarly by team
                        user_outcome = next((o for o in user_market.get('outcomes', []) if o.get('name') == outcome_name), None)
                        if user_outcome is None and market_key == 'spreads':
                            user_outcome = next((o for o in user_market.get('outcomes', []) if outcome_name in o.get('name', '')), None)
                        if user_outcome:
                            try:
                                user_probability = odds_converter(ODDS_FORMAT, 'probability', user_outcome.get('price'))
                                edge = consensus_probability - user_probability
                                kelly = kelly_criterion(
                                    consensus_probability, odds_converter(ODDS_FORMAT, 'decimal', user_outcome.get('price'))
                                )

                                if edge > best_edge:
                                    best_edge = edge
                                    best_kelly = kelly
                                    best_sportsbook = account_key
                            except Exception:
                                continue
            else:
                best_edge = 0
                best_kelly = 0
                best_sportsbook = None

            if avg_hold is not None:
                self.table.setItem(row, hold_col, QTableWidgetItem(f"{avg_hold:.2%}"))
            else:
                self.table.setItem(row, hold_col, QTableWidgetItem("N/A"))
            self.table.setItem(row, best_sportsbook_col, QTableWidgetItem(self.sportsbook_mapping[best_sportsbook] if best_sportsbook else "N/A"))
            self.table.setItem(row, edge_col, QTableWidgetItem(f"{best_edge:.2%}"))
            self.table.setItem(row, kelly_col, QTableWidgetItem(f"{best_kelly:.2%}"))
            # If we marked that this event used an event-level requery for spreads, show an indicator
            try:
                method_used = event.get('_spread_method', 'native')
                if method_used == 'requery':
                    # Put a small icon/text in the Requery column for each outcome row belonging to this event
                    # The Requery column index is 1; style it for visibility
                    rq_item = QTableWidgetItem('⟳')
                    rq_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    rq_brush = QBrush(QColor('#1e90ff'))
                    rq_item.setForeground(rq_brush)
                    rq_font = rq_item.font()
                    rq_font.setBold(True)
                    rq_item.setFont(rq_font)
                    self.table.setItem(row, 1, rq_item)
            except Exception:
                pass

    def _on_table_double_clicked(self, row, column):
        try:
            self._open_event_details(row)
        except Exception:
            pass

    def _on_frozen_double_clicked(self, row, column):
        try:
            self._open_event_details(row)
        except Exception:
            pass

    def _open_event_details(self, row_index: int):
        """Open a dialog showing full event-level bookmakers/markets for the selected row's event."""
        try:
            if not hasattr(self, '_row_event_map') or self._row_event_map is None:
                return
            if row_index < 0 or row_index >= len(self._row_event_map):
                return
            event_id = self._row_event_map[row_index]
            if not event_id or not self._last_odds_data:
                return
            event = next((e for e in self._last_odds_data if e.get('id') == event_id), None)
            if not event:
                dlg = EventDetailsDialog(self, "No details available for this event.")
                dlg.exec()
                return

            # Build a readable text summary of the event odds
            lines = []
            lines.append(f"Event: {event.get('home_team')} vs {event.get('away_team')}")
            lines.append(f"Commence: {convert_to_eastern(event.get('commence_time'))}")
            lines.append("")
            for bm in event.get('bookmakers', []):
                lines.append(f"Bookmaker: {bm.get('title') or bm.get('key')}")
                for m in bm.get('markets', []):
                    lines.append(f"  Market: {m.get('key')}")
                    for o in m.get('outcomes', []):
                        pt = o.get('point') if 'point' in o else ''
                        price = o.get('price')
                        nv = o.get('no_vig_price', '')
                        lines.append(f"    {o.get('name')} {pt} -> price: {price} no-vig: {nv}")
                lines.append("")

            content = "\n".join(lines)
            dlg = EventDetailsDialog(self, content)
            dlg.exec()
        except Exception:
            pass
    def update_requests_remaining(self):
        try:
            requests_remaining = odds_api.get_remaining_requests()
            self.requests_remaining_label.setText(f"Requests Remaining: {requests_remaining}")
        except Exception as e:
            print(f"Error fetching requests remaining: {e}")
            self.requests_remaining_label.setText("Requests Remaining: Error")

    def set_event_ids_map(self, mapping: dict):
        """Receive pre-fetched event id mapping (or flat list under key '_all')."""
        try:
            self.event_ids_map = mapping
            total = 0
            if isinstance(mapping, dict):
                # mapping may be {'_all': [ids]}
                if '_all' in mapping and isinstance(mapping['_all'], list):
                    total = len(mapping['_all'])
                else:
                    for v in mapping.values():
                        if isinstance(v, list):
                            total += len(v)
            self.event_ids_status_label.setText(f"Event IDs loaded: {total}")
        except Exception as e:
            print(f"Error setting event ids map: {e}")

    def go_back(self):
        self.sport_selection_window = SportSelectionWindow(self.sportsbook_mapping, self.selected_accounts, self.display_sportsbooks)
        self.sport_selection_window.show()
        self.close()


class FuturesOddsWindow(QMainWindow):
    def __init__(self, selected_sports, selected_accounts, sportsbook_mapping, display_sportsbooks):
        super().__init__()
        self.setWindowTitle("Futures Odds")
        self.setGeometry(100, 100, 1200, 800)

        self.selected_sports = selected_sports if isinstance(selected_sports, list) else [selected_sports]
        self.current_sport = self.selected_sports[0]  # Default to the first sport in the list
        self.selected_accounts = selected_accounts
        self.sportsbook_mapping = sportsbook_mapping
        self.display_sportsbooks = display_sportsbooks

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)
        self.central_widget.setLayout(main_layout)

        self.requests_remaining_label = QLabel("Requests Remaining: Retrieving...", self)
        main_layout.addWidget(self.requests_remaining_label)

        # Sport Selection Dropdown
        self.sport_dropdown = QComboBox(self)
        self.sport_dropdown.addItems(self.selected_sports)
        self.sport_dropdown.currentTextChanged.connect(self.update_sport)
        main_layout.addWidget(self.sport_dropdown)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        main_layout.addWidget(self.table)
        self.update_table()

        button_layout = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh", self)
        self.refresh_button.clicked.connect(self.update_table)
        button_layout.addWidget(self.refresh_button)

        self.back_button = QPushButton("Back to Sport Selection", self)
        self.back_button.clicked.connect(self.go_back)
        button_layout.addWidget(self.back_button)

        main_layout.addLayout(button_layout)

        self.update_requests_remaining()

    def update_sport(self, sport):
        self.current_sport = sport
        self.update_table()

    def update_table(self):
        self.table.clear()
        self.table.setRowCount(0)

        try:
            odds_data = self.fetch_odds_data()
            self.process_odds_data(odds_data)
            self.add_headers()
            for event in odds_data:
                self.populate_table_rows(event)
            self.update_requests_remaining()
            self.table.resizeColumnsToContents()

        except Exception as e:
            print(f"Error updating table: {e}")

    def fetch_odds_data(self):
        response = odds_api.get_odds(
            sport=self.current_sport,
            markets="outrights",
            odds_format=ODDS_FORMAT,
            bookmakers=','.join(self.display_sportsbooks)
        )
        print(response)
        return response

    def process_odds_data(self, odds_data):
        for event in odds_data:
            for bookmaker in event['bookmakers']:
                for market in bookmaker['markets']:
                    total_prob = sum(
                        odds_converter(ODDS_FORMAT, "probability", outcome["price"])
                        for outcome in market["outcomes"]
                    )
                    for outcome in market["outcomes"]:
                        prob = odds_converter(ODDS_FORMAT, "probability", outcome["price"])
                        no_vig_prob = prob / total_prob if total_prob > 0 else 0
                        outcome["no_vig_price"] = odds_converter("probability", ODDS_FORMAT, no_vig_prob)

    def add_headers(self):
        headers = ["Team"] + [
            self.sportsbook_mapping[bookmaker]
            for bookmaker in self.display_sportsbooks
        ] + ["Consensus Odds", "Positive Edge", "Kelly Bet", "Best Sportsbook"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

    def populate_table_rows(self, event):
        for outcome in event['bookmakers'][0]['markets'][0]['outcomes']:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(outcome['name']))

            probabilities = []
            weights = []
            for col, bookmaker_key in enumerate(self.display_sportsbooks, start=1):
                bookmaker = next((b for b in event['bookmakers'] if b['key'] == bookmaker_key), None)
                if bookmaker:
                    market = next((m for m in bookmaker['markets'] if m['key'] == "outrights"), None)
                    if market:
                        outcome_data = next((o for o in market['outcomes'] if o['name'] == outcome['name']), None)
                        if outcome_data:
                            self.table.setItem(row, col, QTableWidgetItem(str(outcome_data["price"])))
                            try:
                                probabilities.append(
                                    odds_converter(ODDS_FORMAT, "probability", outcome_data["no_vig_price"])
                                )
                            except Exception:
                                pass

                            # Apply weighting for Pinnacle
                            weight = 10 if bookmaker_key == "pinnacle" else 1
                            weights.append(weight)

            if probabilities:
                consensus_probability = sum(p * w for p, w in zip(probabilities, weights)) / sum(weights)
                consensus_odds = odds_converter("probability", ODDS_FORMAT, consensus_probability)

                # Correct column alignment
                consensus_col = len(self.display_sportsbooks) + 1
                edge_col = len(self.display_sportsbooks) + 2
                kelly_col = len(self.display_sportsbooks) + 3
                best_sportsbook_col = len(self.display_sportsbooks) + 4

                self.table.setItem(row, consensus_col, QTableWidgetItem(f"{consensus_odds:.2f}"))

                # Calculate Positive Edge and Kelly Bet based on user-selected sportsbooks
                best_sportsbook = None
                best_edge = -float('inf')
                best_kelly = 0

                for account_key in self.selected_accounts:
                    user_market = next(
                        (m for b in event['bookmakers'] if b['key'] == account_key for m in b['markets'] if m['key'] == "outrights"),
                        None
                    )
                    if user_market:
                        user_outcome = next((o for o in user_market["outcomes"] if o["name"] == outcome['name']), None)
                        if user_outcome:
                            user_probability = odds_converter(ODDS_FORMAT, "probability", user_outcome["price"])
                            edge = consensus_probability - user_probability
                            kelly = kelly_criterion(
                                consensus_probability, odds_converter(ODDS_FORMAT, "decimal", user_outcome["price"])
                            )

                            if edge > best_edge:
                                best_edge = edge
                                best_kelly = kelly
                                best_sportsbook = account_key

                self.table.setItem(row, edge_col, QTableWidgetItem(f"{best_edge:.2%}"))
                self.table.setItem(row, kelly_col, QTableWidgetItem(f"{best_kelly:.2%}"))
                self.table.setItem(row, best_sportsbook_col, QTableWidgetItem(self.sportsbook_mapping[best_sportsbook] if best_sportsbook else "N/A"))

    def update_requests_remaining(self):
        try:
            requests_remaining = odds_api.get_remaining_requests()
            self.requests_remaining_label.setText(f"Requests Remaining: {requests_remaining}")
        except Exception as e:
            print(f"Error fetching requests remaining: {e}")
            self.requests_remaining_label.setText("Requests Remaining: Error")

    def go_back(self):
        self.sport_selection_window = SportSelectionWindow(self.sportsbook_mapping, self.selected_accounts, self.display_sportsbooks)
        self.sport_selection_window.show()
        self.close()


class HistoricalAnalysisWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Historical Analysis")
        self.setGeometry(100, 100, 800, 600)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)
        self.central_widget.setLayout(main_layout)

        self.label = QLabel("Historical Analysis is under development. This feature will allow users to review and analyze betslips over time.", self)
        main_layout.addWidget(self.label)

        self.back_button = QPushButton("Back to Startup", self)
        self.back_button.clicked.connect(self.go_back)
        main_layout.addWidget(self.back_button)

    def go_back(self):
        self.startup_window = StartupWindow()
        self.startup_window.show()
        self.close()


if __name__ == "__main__":
    # Initialize the OddsAPI instance
    odds_api = OddsAPI(THEODDSAPI_KEY_PROD)

    # Initialize the App
    app = QApplication(sys.argv)

    # Initialize GUI formatting
    # Load user theme preference
    prefs = load_user_prefs()
    theme = prefs.get('theme', 'dark') if isinstance(prefs, dict) else 'dark'
    chosen_palette = PALETTES.get(theme, PALETTE)
    stylesheet = set_stylesheet(chosen_palette)
    app.setStyleSheet(stylesheet)

    # Run App
    startup_window = StartupWindow()
    startup_window.show()
    sys.exit(app.exec())
