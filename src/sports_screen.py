#! .\SportsbookOdds\env\Scripts\python.exe

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget,
    QLabel, QScrollArea, QTableWidget, QTableWidgetItem,
    QHeaderView, QHBoxLayout, QCheckBox, QComboBox,
    QPushButton, QDoubleSpinBox, QDialog, QPlainTextEdit, QDialogButtonBox,
    QLineEdit, QButtonGroup, QStyledItemDelegate, QStyle
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QSize, QRectF
from PyQt6.QtGui import QColor, QBrush, QFont, QFontMetrics, QPainter, QPixmap, QPalette
import sys
import os
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
try:
    from PyQt6.QtSvg import QSvgRenderer
except Exception:
    QSvgRenderer = None


SPORTSBOOK_SVG_DIR = os.path.join(os.getcwd(), "data", "sportsbook_svgs")
SPORTSBOOK_ICON_SIZE = QSize(56, 56)
SPORTSBOOK_HEADER_HEIGHT = 96
SPORTSBOOK_COL_WIDTH = 120
SPORTSBOOK_ICON_PADDING = 6
EVENT_HEADER_HEIGHT = 42


def _load_sportsbook_pixmap(bookmaker_key: str, size: QSize) -> QPixmap | None:
    if not QSvgRenderer:
        return None
    try:
        svg_path = os.path.join(SPORTSBOOK_SVG_DIR, f"{bookmaker_key}.svg")
        if not os.path.exists(svg_path):
            return None
        renderer = QSvgRenderer(svg_path)
        if not renderer.isValid():
            return None
        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter, QRectF(0, 0, size.width(), size.height()))
        painter.end()
        return pixmap
    except Exception:
        return None


def _build_header_label(text: str, pixmap: QPixmap | None = None) -> QLabel:
    label = QLabel(text)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setFixedHeight(SPORTSBOOK_HEADER_HEIGHT)
    if pixmap is not None:
        label.setPixmap(pixmap)
    return label


def _set_header_label_content(label: QLabel, sportsbook_key: str, display_name: str, width: int, height: int) -> None:
    size = min(width, height) - (SPORTSBOOK_ICON_PADDING * 2)
    if size > 0:
        pixmap = _load_sportsbook_pixmap(sportsbook_key, QSize(size, size))
        if pixmap is not None:
            label.setPixmap(pixmap)
            label.setText("")
            label.setToolTip(display_name)
            return
    label.setPixmap(QPixmap())
    label.setText(display_name)
    label.setToolTip("")


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


class ItemBackgroundDelegate(QStyledItemDelegate):
    """Custom background painting to preserve alternation + allow per-cell overrides."""
    def paint(self, painter, option, index):
        bg = index.data(Qt.ItemDataRole.BackgroundRole)
        if isinstance(bg, QBrush):
            painter.fillRect(option.rect, bg)
            option.state &= ~(QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_MouseOver)
        else:
            base = option.palette.base().color()
            alt = option.palette.alternateBase().color()
            painter.fillRect(option.rect, QBrush(alt if index.row() % 2 else base))
            if option.state & QStyle.StateFlag.State_Selected:
                painter.fillRect(option.rect, option.palette.highlight())
                option.palette.setColor(QPalette.ColorRole.Text, option.palette.highlightedText().color())
            option.state &= ~(QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_MouseOver)
        super().paint(painter, option, index)


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
        try:
            self.showMaximized()
        except Exception:
            pass

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
        self.search_input.setPlaceholderText("Search events...")
        try:
            self.search_input.setClearButtonEnabled(True)
        except Exception:
            pass
        self.search_input.setMinimumWidth(200)
        try:
            self.search_input.textChanged.connect(self._filter_events_list)
        except Exception:
            pass
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

        self.summary_label = QLabel("Events: 0 | Outcomes: 0", self)
        self.summary_label.setStyleSheet("font-size:11px;color:gray;")
        main_layout.addWidget(self.summary_label)

        # Odds board (single, grouped table)
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        try:
            self.table.setItemDelegate(ItemBackgroundDelegate(self.table))
        except Exception:
            pass
        try:
            self.table.verticalHeader().setVisible(False)
        except Exception:
            pass

        board_title = QLabel("Odds Board", self)
        board_title.setStyleSheet("font-weight:700; font-size:15px;")
        main_layout.addWidget(board_title)
        main_layout.addWidget(self.table)

        self.update_table()

        try:
            self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
            self.table.cellDoubleClicked.connect(self._on_table_double_clicked)
        except Exception:
            pass

        # Legend explaining icons and consensus
        self.legend_label = QLabel("Legend: Consensus = weighted odds (Pinnacle-weighted).", self)
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

    def update_requests_remaining(self):
        try:
            requests_remaining = odds_api.get_remaining_requests()
            self.requests_remaining_label.setText(f"Requests Remaining: {requests_remaining}")
        except Exception as e:
            print(f"Error fetching requests remaining: {e}")
            self.requests_remaining_label.setText("Requests Remaining: Error")

    def go_back(self):
        self.sport_selection_window = SportSelectionWindow(
            self.sportsbook_mapping, self.selected_accounts, self.display_sportsbooks
        )
        self.sport_selection_window.show()
        self.close()

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
                if needed > 0 and remaining >= needed:
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
            self._event_row_groups = []
            for event in odds_data or []:
                self.populate_table_rows(event)
            try:
                self._filter_events_list(self.search_input.text())
            except Exception:
                pass
            try:
                events_count = len(odds_data or [])
                outcomes_count = sum(len(rows) for _, rows, _ in getattr(self, "_event_row_groups", []))
                self.summary_label.setText(f"Events: {events_count} | Outcomes: {outcomes_count}")
            except Exception:
                pass
            self.update_requests_remaining()
            try:
                sportsbook_start = 7
                for offset, _ in enumerate(self.display_sportsbooks):
                    col_idx = sportsbook_start + offset
                    self.table.setColumnWidth(col_idx, SPORTSBOOK_HEADER_HEIGHT)
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
        headers = ["Event", "Outcome", point_label, "Hold", "Best Sportsbook", "Positive Edge", "Kelly Bet"] + [
            self.sportsbook_mapping[bookmaker]
            for bookmaker in self.display_sportsbooks
        ] + ["Consensus Odds"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        try:
            header = self.table.horizontalHeader()
            header.setFixedHeight(SPORTSBOOK_HEADER_HEIGHT)
        except Exception:
            pass
        sportsbook_start = 7
        sportsbook_columns = {
            sportsbook_start + offset: (
                bookmaker_key,
                self.sportsbook_mapping.get(bookmaker_key, bookmaker_key),
            )
            for offset, bookmaker_key in enumerate(self.display_sportsbooks)
        }
        for offset, bookmaker_key in enumerate(self.display_sportsbooks):
            col_idx = sportsbook_start + offset
            try:
                header = self.table.horizontalHeader()
                header.setSectionResizeMode(col_idx, QHeaderView.Fixed)
                self.table.setColumnWidth(col_idx, SPORTSBOOK_HEADER_HEIGHT)
            except Exception:
                pass
        try:
            header = self.table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.Stretch)
            header.setSectionResizeMode(1, QHeaderView.Fixed)
            header.setSectionResizeMode(2, QHeaderView.Fixed)
            header.setSectionResizeMode(3, QHeaderView.Fixed)
            header.setSectionResizeMode(4, QHeaderView.Fixed)
            header.setSectionResizeMode(5, QHeaderView.Fixed)
            header.setSectionResizeMode(6, QHeaderView.Fixed)
            self.table.setColumnWidth(1, 170)
            self.table.setColumnWidth(2, 70)
            self.table.setColumnWidth(3, 60)
            self.table.setColumnWidth(4, 140)
            self.table.setColumnWidth(5, 80)
            self.table.setColumnWidth(6, 80)
            consensus_col_idx = len(self.display_sportsbooks) + 7
            if consensus_col_idx < self.table.columnCount():
                header.setSectionResizeMode(consensus_col_idx, QHeaderView.Fixed)
                self.table.setColumnWidth(consensus_col_idx, 110)
        except Exception:
            pass
        # Improve header alignment and add helpful tooltips
        try:
            header = self.table.horizontalHeader()
            header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
            # Tooltip and emphasis for Consensus Odds column in the right table
            consensus_col_idx = len(self.display_sportsbooks) + 7
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

    def _filter_events_list(self, text: str):
        """Filter grouped event sections by event header text."""
        try:
            query = (text or "").strip().lower()
            groups = getattr(self, "_event_row_groups", [])
            for header_row, rows, label in groups:
                hide = bool(query) and query not in label
                self.table.setRowHidden(header_row, hide)
                for r in rows:
                    self.table.setRowHidden(r, hide)
        except Exception:
            pass

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
            vheader.setSectionResizeMode(QHeaderView.Fixed)
            vheader.setDefaultSectionSize(row_height)
            try:
                vheader.setMinimumSectionSize(row_height)
                vheader.setMaximumSectionSize(row_height)
            except Exception:
                pass
            for r in range(self.table.rowCount()):
                self.table.setRowHeight(r, row_height)
        except Exception:
            pass

    def populate_table_rows(self, event):
        market_key = self.market_dropdown.currentText()

        home = event.get('home_team') or ''
        away = event.get('away_team') or ''
        if home and away:
            event_label = f"{away} @ {home}"
        else:
            event_label = event.get('title') or event.get('description') or "Event"
        event_time = convert_to_eastern(event.get('commence_time'))
        cp = event.get('_consensus_point')
        cp_text = f" • Consensus {cp:+.1f}" if isinstance(cp, (int, float)) else ""
        requery_mark = ""

        # For spreads, iterate by team names to avoid mismatch due to point formatting differences
        if market_key == 'spreads':
            outcome_names = [event.get('home_team'), event.get('away_team')]
        else:
            # default behavior: use outcomes from first bookmaker/market
            first_bm = event['bookmakers'][0]
            first_market = first_bm['markets'][0]
            outcome_names = [o['name'] for o in first_market.get('outcomes', [])]

        outcome_rows = []
        start_row = self.table.rowCount()
        for idx, outcome_name in enumerate(outcome_names):
            row = self.table.rowCount()
            self.table.insertRow(row)
            outcome_rows.append(row)
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
            # Event column (merged across outcomes)
            if row == start_row:
                event_item = QTableWidgetItem(f"{event_label} - {event_time}{cp_text}{requery_mark}")
                try:
                    event_font = event_item.font()
                    event_font.setBold(True)
                    event_item.setFont(event_font)
                    base = self.table.palette().alternateBase().color()
                    event_item.setBackground(QBrush(base))
                except Exception:
                    pass
                self.table.setItem(row, 0, event_item)
            # Outcome
            self.table.setItem(row, 1, QTableWidgetItem(outcome_name))
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

            for col, bookmaker_key in enumerate(self.display_sportsbooks, start=7):
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

            # set Spread cell (compact) in column index 2 (Event, Outcome, Spread)
            self.table.setItem(row, 2, QTableWidgetItem(spread_display))

            # Correct column alignment (after Event, Outcome, Spread, Hold...)
            hold_col = 3
            best_sportsbook_col = 4
            edge_col = 5
            kelly_col = 6
            consensus_col = len(self.display_sportsbooks) + 7

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
            # Conditional formatting for positive edge + best odds cell
            try:
                if best_edge > 0:
                    max_edge = 0.08
                    intensity = min(best_edge / max_edge, 1.0)
                    alpha = int(80 + intensity * 160)
                    highlight = QBrush(QColor(60, 200, 90, alpha))
                    edge_item = self.table.item(row, edge_col)
                    if edge_item:
                        edge_item.setBackground(highlight)
                    kelly_item = self.table.item(row, kelly_col)
                    if kelly_item:
                        kelly_item.setBackground(highlight)
                    if best_sportsbook in self.display_sportsbooks:
                        bs_col = 7 + self.display_sportsbooks.index(best_sportsbook)
                        bs_item = self.table.item(row, bs_col)
                        if bs_item:
                            bs_item.setBackground(highlight)
            except Exception:
                pass

        try:
            if outcome_rows:
                self.table.setSpan(start_row, 0, len(outcome_rows), 1)
        except Exception:
            pass

        try:
            if hasattr(self, "_event_row_groups"):
                self._event_row_groups.append((start_row, outcome_rows, event_label.lower()))
        except Exception:
            pass


class FuturesOddsWindow(QMainWindow):
    def __init__(self, selected_sports, selected_accounts, sportsbook_mapping, display_sportsbooks):
        super().__init__()
        self.setWindowTitle("Futures Odds")
        self.setGeometry(100, 100, 1200, 800)
        try:
            self.showMaximized()
        except Exception:
            pass

        self.selected_sports = selected_sports if isinstance(selected_sports, list) else [selected_sports]
        self.current_sport = self.selected_sports[0]
        self.selected_accounts = selected_accounts
        self.sportsbook_mapping = sportsbook_mapping
        self.display_sportsbooks = display_sportsbooks

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)
        self.central_widget.setLayout(main_layout)

        self.requests_remaining_label = QLabel("Requests Remaining: Retrieving...", self)
        main_layout.addWidget(self.requests_remaining_label)

        self.sport_dropdown = QComboBox(self)
        self.sport_dropdown.addItems(self.selected_sports)
        self.sport_dropdown.currentTextChanged.connect(self.update_sport)
        main_layout.addWidget(self.sport_dropdown)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        try:
            self.table.setItemDelegate(ItemBackgroundDelegate(self.table))
        except Exception:
            pass
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
        headers = ["Team", "Best Sportsbook", "Positive Edge", "Kelly Bet"] + [
            self.sportsbook_mapping[bookmaker]
            for bookmaker in self.display_sportsbooks
        ] + ["Consensus Odds"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        try:
            header = self.table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.Stretch)
            for i in range(1, 4):
                header.setSectionResizeMode(i, QHeaderView.Fixed)
            self.table.setColumnWidth(1, 160)
            self.table.setColumnWidth(2, 90)
            self.table.setColumnWidth(3, 90)
            consensus_col = len(self.display_sportsbooks) + 4
            if consensus_col < self.table.columnCount():
                header.setSectionResizeMode(consensus_col, QHeaderView.Fixed)
                self.table.setColumnWidth(consensus_col, 110)
            for offset, _ in enumerate(self.display_sportsbooks):
                col_idx = 4 + offset
                header.setSectionResizeMode(col_idx, QHeaderView.Fixed)
                self.table.setColumnWidth(col_idx, SPORTSBOOK_HEADER_HEIGHT)
        except Exception:
            pass

    def populate_table_rows(self, event):
        for outcome in event['bookmakers'][0]['markets'][0]['outcomes']:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(outcome['name']))

            probabilities = []
            weights = []
            for col, bookmaker_key in enumerate(self.display_sportsbooks, start=4):
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

                            weight = 10 if bookmaker_key == "pinnacle" else 1
                            weights.append(weight)

            if probabilities:
                consensus_probability = sum(p * w for p, w in zip(probabilities, weights)) / sum(weights)
                consensus_odds = odds_converter("probability", ODDS_FORMAT, consensus_probability)

                best_sportsbook_col = 1
                edge_col = 2
                kelly_col = 3
                consensus_col = len(self.display_sportsbooks) + 4

                self.table.setItem(row, consensus_col, QTableWidgetItem(f"{consensus_odds:.2f}"))

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

                self.table.setItem(row, best_sportsbook_col, QTableWidgetItem(self.sportsbook_mapping[best_sportsbook] if best_sportsbook else "N/A"))
                self.table.setItem(row, edge_col, QTableWidgetItem(f"{best_edge:.2%}"))
                self.table.setItem(row, kelly_col, QTableWidgetItem(f"{best_kelly:.2%}"))
                # Conditional formatting for positive edge + best odds cell
                try:
                    if best_edge > 0:
                        max_edge = 0.08
                        intensity = min(best_edge / max_edge, 1.0)
                        alpha = int(80 + intensity * 160)
                        highlight = QBrush(QColor(60, 200, 90, alpha))
                        edge_item = self.table.item(row, edge_col)
                        if edge_item:
                            edge_item.setBackground(highlight)
                        kelly_item = self.table.item(row, kelly_col)
                        if kelly_item:
                            kelly_item.setBackground(highlight)
                        if best_sportsbook in self.display_sportsbooks:
                            bs_col = 4 + self.display_sportsbooks.index(best_sportsbook)
                            bs_item = self.table.item(row, bs_col)
                            if bs_item:
                                bs_item.setBackground(highlight)
                except Exception:
                    pass
            else:
                best_sportsbook_col = 1
                edge_col = 2
                kelly_col = 3
                consensus_col = len(self.display_sportsbooks) + 4
                self.table.setItem(row, consensus_col, QTableWidgetItem("N/A"))
                self.table.setItem(row, edge_col, QTableWidgetItem("N/A"))
                self.table.setItem(row, kelly_col, QTableWidgetItem("N/A"))
                self.table.setItem(row, best_sportsbook_col, QTableWidgetItem("N/A"))

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
