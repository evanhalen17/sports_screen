#! .\SportsbookOdds\env\Scripts\python.exe

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget,
    QLabel, QScrollArea, QTableWidget, QTableWidgetItem,
    QHeaderView, QHBoxLayout, QGridLayout, QCheckBox, QComboBox,
    QPushButton, QDoubleSpinBox, QDialog, QPlainTextEdit, QDialogButtonBox,
    QLineEdit, QButtonGroup, QStyledItemDelegate, QStyle, QFileDialog, QStyleOptionViewItem,
    QSlider
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QSize, QModelIndex
from PyQt6.QtGui import QColor, QBrush, QFontMetrics, QPalette, QPainter
import sys
import csv
from datetime import datetime
from typing import Dict, List, Optional
from the_odds_api import OddsAPI
from config import (
    PALETTE, PALETTES, THEODDSAPI_KEY_PROD, ODDS_FORMAT
)
from utils import (
    kelly_criterion,
    odds_converter,
    set_stylesheet,
    convert_to_eastern,
    fetch_event_ids_for_sports,
    compute_consensus_point,
    load_user_prefs,
    save_user_prefs,
)
from rich import print


odds_api: OddsAPI | None = None


def _require_odds_api() -> OddsAPI:
    if odds_api is None:
        raise RuntimeError("OddsAPI is not initialized.")
    return odds_api

SPORTSBOOK_HEADER_HEIGHT = 96


def _export_table_to_csv(parent: QWidget, table: QTableWidget, default_prefix: str) -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_name = f"{default_prefix}_{timestamp}.csv"
    path, _ = QFileDialog.getSaveFileName(parent, "Export CSV", default_name, "CSV Files (*.csv)")
    if not path:
        return
    try:
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            headers = []
            for col in range(table.columnCount()):
                item = table.horizontalHeaderItem(col)
                headers.append(item.text() if item else "")
            writer.writerow(headers)
            for row in range(table.rowCount()):
                row_values = []
                for col in range(table.columnCount()):
                    item = table.item(row, col)
                    row_values.append(item.text() if item else "")
                writer.writerow(row_values)
    except Exception as exc:
        print(f"Export failed: {exc}")


def _default_sportsbook_weights(sportsbook_mapping: Dict[str, str]) -> Dict[str, float]:
    weights: Dict[str, float] = {}
    for key in sportsbook_mapping.keys():
        weights[key] = 1.0 if key == "pinnacle" else 0.6
    return weights


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
    def paint(self, painter: Optional[QPainter], option: QStyleOptionViewItem, index: QModelIndex):
        if painter is None or option is None:
            return
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
        self.user_sportsbook_window = None
        self.sport_selection_window = None
        self.current_odds_window = None
        self.futures_odds_window = None
        self.historical_analysis_window = None

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

        self.matchup_odds_button = QPushButton("View Matchup Odds", self)
        self.matchup_odds_button.clicked.connect(self.open_matchup_odds)
        main_layout.addWidget(self.matchup_odds_button)

        self.futures_odds_button = QPushButton("View Futures Odds", self)
        self.futures_odds_button.clicked.connect(self.open_futures_odds)
        main_layout.addWidget(self.futures_odds_button)

        # Quick Start: jump straight into Current Odds with saved or sensible defaults
        self.quick_start_button = QPushButton("Quick Start", self)
        self.quick_start_button.setToolTip("Open Matchup Odds using saved preferences or popular sportsbooks")
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
        if not self.user_sportsbook_window:
            return
        self.selected_accounts, self.display_sportsbooks = self.user_sportsbook_window.get_selections()
        print("User Sportsbook Accounts Saved:", self.selected_accounts)
        print("Display Sportsbooks Selected:", self.display_sportsbooks)

    def _load_sportsbook_prefs(self):
        try:
            prefs = load_user_prefs()
        except Exception:
            prefs = {}
        selected_accounts = self.selected_accounts if self.selected_accounts else prefs.get('selected_accounts', {})
        display_sportsbooks = self.display_sportsbooks if self.display_sportsbooks else prefs.get('display_sportsbooks', [])
        if not display_sportsbooks:
            display_sportsbooks = ['draftkings', 'fanduel', 'betmgm', 'pinnacle', 'betrivers']
        return selected_accounts, display_sportsbooks

    def _fetch_sports(self):
        try:
            return _require_odds_api().get_sports() or []
        except Exception as e:
            print(f"Error fetching sports: {e}")
            return []

    def open_matchup_odds(self):
        selected_accounts, display_sportsbooks = self._load_sportsbook_prefs()
        sports = self._fetch_sports()
        matchup_sports = [s.get('key') for s in sports if s.get('key') and not s.get('has_outrights')]
        if not matchup_sports:
            print("Error: No matchup sports available.")
            return
        self.current_odds_window = CurrentOddsWindow(
            matchup_sports, selected_accounts, self.sportsbook_mapping, display_sportsbooks
        )
        self.current_odds_window.show()
        self.close()

    def open_futures_odds(self):
        selected_accounts, display_sportsbooks = self._load_sportsbook_prefs()
        sports = self._fetch_sports()
        futures_sports = [s.get('key') for s in sports if s.get('key') and s.get('has_outrights')]
        if not futures_sports:
            print("Error: No futures sports available.")
            return
        self.futures_odds_window = FuturesOddsWindow(
            futures_sports, selected_accounts, self.sportsbook_mapping, display_sportsbooks
        )
        self.futures_odds_window.show()
        self.close()

    def open_historical_analysis(self):
        self.historical_analysis_window = HistoricalAnalysisWindow()
        self.historical_analysis_window.show()
        self.close()

    def quick_start(self):
        """Open Matchup Odds using saved prefs or sensible defaults."""
        self.open_matchup_odds()

    def change_theme(self, theme_name: str):
        """Apply a new theme and persist the choice."""
        try:
            pal = PALETTES.get(theme_name, PALETTE)
            app = QApplication.instance()
            if isinstance(app, QApplication):
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
        self.sportsbook_weights = {}
        self._default_weights = _default_sportsbook_weights(self.sportsbook_mapping)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)
        self.central_widget.setLayout(main_layout)

        self.label = QLabel("Select your sportsbooks and enter bankrolls (leave $0 for display-only):", self)
        main_layout.addWidget(self.label)
        self.weight_hint = QLabel("Sharpness weights influence consensus odds (0.00 to 1.00). Default favors Pinnacle.", self)
        self.weight_hint.setStyleSheet("font-size:11px;color:gray;")
        main_layout.addWidget(self.weight_hint)

        self.scroll_area = QScrollArea(self)
        self.scroll_area_widget = QWidget()
        self.scroll_area_layout = QGridLayout(self.scroll_area_widget)
        self.scroll_area_layout.setHorizontalSpacing(16)
        self.scroll_area_layout.setVerticalSpacing(10)
        self.scroll_area_layout.setColumnStretch(0, 1)
        self.scroll_area_layout.setColumnStretch(1, 0)
        self.scroll_area_layout.setColumnStretch(2, 1)
        self.scroll_area_layout.setColumnStretch(3, 0)

        header_name = QLabel("Sportsbook", self)
        header_bankroll = QLabel("Bankroll", self)
        header_weight = QLabel("Sharpness", self)
        header_weight_value = QLabel("Value", self)
        header_name.setStyleSheet("font-weight: 700;")
        header_bankroll.setStyleSheet("font-weight: 700;")
        header_weight.setStyleSheet("font-weight: 700;")
        header_weight_value.setStyleSheet("font-weight: 700;")
        self.scroll_area_layout.addWidget(header_name, 0, 0)
        self.scroll_area_layout.addWidget(header_bankroll, 0, 1)
        self.scroll_area_layout.addWidget(header_weight, 0, 2)
        self.scroll_area_layout.addWidget(header_weight_value, 0, 3)

        self.sportsbook_widgets = {}
        for row_idx, (key, title) in enumerate(self.sportsbook_mapping.items(), start=1):
            checkbox = QCheckBox(title, self)
            bankroll_input = QDoubleSpinBox(self)
            bankroll_input.setRange(0.0, 1000000.0)
            bankroll_input.setPrefix("$")
            bankroll_input.setDecimals(2)
            bankroll_input.setMinimumWidth(120)
            bankroll_input.setMinimumHeight(30)
            bankroll_input.setToolTip("Enter $0 to show odds without tracking bankroll.")
            weight_slider = QSlider(Qt.Orientation.Horizontal, self)
            weight_slider.setRange(0, 100)
            weight_slider.setSingleStep(5)
            weight_slider.setPageStep(10)
            weight_slider.setMinimumWidth(120)
            weight_slider.setToolTip("Sharpness weight from 0.00 (low) to 1.00 (sharp).")
            weight_value = QLabel("0.00", self)
            weight_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            default_weight = float(self._default_weights.get(key, 0.6))
            weight_slider.setValue(int(round(default_weight * 100)))
            weight_value.setText(f"{default_weight:.2f}")
            def _update_weight_label(val: int, label: QLabel = weight_value) -> None:
                label.setText(f"{val / 100:.2f}")
            weight_slider.valueChanged.connect(_update_weight_label)

            self.sportsbook_widgets[key] = (checkbox, bankroll_input, weight_slider, weight_value)
            self.scroll_area_layout.addWidget(checkbox, row_idx, 0)
            self.scroll_area_layout.addWidget(bankroll_input, row_idx, 1)
            self.scroll_area_layout.addWidget(weight_slider, row_idx, 2)
            self.scroll_area_layout.addWidget(weight_value, row_idx, 3)
            self.scroll_area_layout.setRowMinimumHeight(row_idx, 34)

        self.scroll_area.setWidget(self.scroll_area_widget)
        self.scroll_area.setWidgetResizable(True)
        main_layout.addWidget(self.scroll_area)

        # Load saved user preferences (selected sportsbooks and bankrolls)
        try:
            prefs = load_user_prefs()
            saved_accounts = prefs.get('selected_accounts', {}) if isinstance(prefs, dict) else {}
            saved_display = prefs.get('display_sportsbooks', []) if isinstance(prefs, dict) else []
            saved_weights = prefs.get('sportsbook_weights', {}) if isinstance(prefs, dict) else {}
            for key, (checkbox, bankroll_input, weight_slider, _weight_value) in self.sportsbook_widgets.items():
                if key in saved_display:
                    checkbox.setChecked(True)
                if key in saved_accounts:
                    try:
                        bankroll_input.setValue(float(saved_accounts.get(key, 0)))
                    except Exception:
                        pass
                try:
                    if key in saved_weights:
                        weight_slider.setValue(int(round(float(saved_weights.get(key, self._default_weights.get(key, 0.6))) * 100)))
                    else:
                        weight_slider.setValue(int(round(float(self._default_weights.get(key, 0.6)) * 100)))
                except Exception:
                    pass
        except Exception:
            pass

        actions_layout = QHBoxLayout()
        self.select_all_button = QPushButton("Select All", self)
        self.select_all_button.clicked.connect(self.select_all)
        actions_layout.addWidget(self.select_all_button)

        # Quick preset: select popular sportsbooks
        self.select_popular_button = QPushButton("Select Popular", self)
        self.select_popular_button.setToolTip("Check a preset of popular sportsbooks")
        self.select_popular_button.clicked.connect(self.select_popular)
        actions_layout.addWidget(self.select_popular_button)

        self.deselect_all_button = QPushButton("Clear Selections", self)
        self.deselect_all_button.clicked.connect(self.deselect_all)
        actions_layout.addWidget(self.deselect_all_button)

        actions_layout.addStretch(1)
        self.save_button = QPushButton("Save", self)
        self.save_button.clicked.connect(self.save_selections)
        actions_layout.addWidget(self.save_button)
        main_layout.addLayout(actions_layout)

    def select_all(self):
        for _, widget in self.sportsbook_widgets.items():
            widget[0].setChecked(True)
    
    def deselect_all(self):
        for _, widget in self.sportsbook_widgets.items():
            widget[0].setChecked(False)

    def select_popular(self):
        """Check a small preset list of popular sportsbooks and assign light default bankrolls."""
        popular = ['draftkings', 'fanduel', 'betmgm', 'pinnacle', 'betrivers']
        for key, (checkbox, bankroll_input, weight_slider, _weight_value) in self.sportsbook_widgets.items():
            if key in popular:
                checkbox.setChecked(True)
                # set a small default bankroll if currently zero
                try:
                    if bankroll_input.value() == 0:
                        bankroll_input.setValue(100.0)
                except Exception:
                    pass
                try:
                    if weight_slider.value() == 0:
                        weight_slider.setValue(int(round(float(self._default_weights.get(key, 0.6)) * 100)))
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
        self.sportsbook_weights = {
            key: float(widget[2].value()) / 100.0
            for key, widget in self.sportsbook_widgets.items()
        }
        print("Saved Accounts:", self.selected_accounts)
        print("Display Sportsbooks:", self.display_sportsbooks)
        # Persist preferences for next session
        try:
            prefs = load_user_prefs()
            if not isinstance(prefs, dict):
                prefs = {}
            prefs['selected_accounts'] = self.selected_accounts
            prefs['display_sportsbooks'] = self.display_sportsbooks
            prefs['sportsbook_weights'] = self.sportsbook_weights
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
        self.current_odds_window = None
        self.futures_odds_window = None
        self.startup_window = None
        self._event_ids_worker = None

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
            return _require_odds_api().get_sports()
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
                self._event_ids_worker = EventIdsWorker(_require_odds_api(), non_futures_sports)
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


class OddsWindowMixin:
    selected_sports: List[str]
    current_sport: str
    live_button: QPushButton
    live_counts_label: QLabel
    requests_remaining_label: QLabel
    sport_summary_label: QLabel
    _odds_format_map: Dict[str, str]
    odds_format_dropdown: QComboBox
    _display_odds_format: str
    _api_odds_format: str
    _sportsbook_weights: Dict[str, float]
    table: QTableWidget
    def update_table(self) -> None:
        raise NotImplementedError

    def _build_sport_title_map(self):
        try:
            api = _require_odds_api()
            sports = api.get_sports() or []
            return {s.get('key'): s.get('title') or s.get('key') for s in sports if s.get('key')}
        except Exception:
            return {}

    def _display_sport_title(self, sport_key: str) -> str:
        title = getattr(self, "_sport_title_map", {}).get(sport_key)
        if title:
            return title
        return str(sport_key).replace("_", " ").title()

    def _parse_commence_time(self, commence_time):
        if not commence_time:
            return None
        try:
            return datetime.fromisoformat(commence_time.replace("Z", "+00:00"))
        except Exception:
            return None

    def _is_live_event(self, event):
        dt = self._parse_commence_time(event.get('commence_time'))
        if dt is None:
            return False
        try:
            now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.utcnow()
        except Exception:
            now = datetime.utcnow()
        return dt <= now

    def _update_live_counts(self, odds_data):
        try:
            total_live = 0
            total_pre = 0
            for event in odds_data or []:
                if self._is_live_event(event):
                    total_live += 1
                else:
                    total_pre += 1
            self.live_counts_label.setText(f"Pre-Game: {total_pre} | Live: {total_live}")
        except Exception:
            self.live_counts_label.setText("Pre-Game: -- | Live: --")

    def _filter_by_live_toggle(self, odds_data):
        try:
            if self.live_button.isChecked():
                return [e for e in odds_data or [] if self._is_live_event(e)]
            return [e for e in odds_data or [] if not self._is_live_event(e)]
        except Exception:
            return odds_data

    def update_requests_remaining(self):
        try:
            api = _require_odds_api()
            requests_remaining = api.get_remaining_requests()
            self.requests_remaining_label.setText(f"Requests Remaining: {requests_remaining}")
        except Exception as e:
            print(f"Error fetching requests remaining: {e}")
            self.requests_remaining_label.setText("Requests Remaining: Error")

    def _update_sport_summary(self):
        try:
            total = len(self.selected_sports) if isinstance(self.selected_sports, list) else 0
            if total <= 1:
                summary = f"Sports: {self._display_sport_title(self.current_sport)}"
            else:
                summary = f"Sports: {self._display_sport_title(self.current_sport)} + {total - 1} more"
            self.sport_summary_label.setText(summary)
        except Exception:
            self.sport_summary_label.setText("")

    def _load_odds_format_pref(self):
        try:
            prefs = load_user_prefs()
        except Exception:
            prefs = {}
        pref_fmt = None
        if isinstance(prefs, dict):
            pref_fmt = prefs.get('odds_format')

        if pref_fmt not in ('american', 'decimal', 'probability'):
            pref_fmt = ODDS_FORMAT if ODDS_FORMAT in ('american', 'decimal', 'probability') else 'american'

        self._display_odds_format = pref_fmt
        self._api_odds_format = pref_fmt if pref_fmt in ('american', 'decimal') else 'decimal'

        if hasattr(self, 'odds_format_dropdown') and hasattr(self, '_odds_format_map'):
            try:
                current_label = next(k for k, v in self._odds_format_map.items() if v == pref_fmt)
                idx = self.odds_format_dropdown.findText(current_label)
                if idx >= 0:
                    self.odds_format_dropdown.setCurrentIndex(idx)
            except Exception:
                pass

    def _load_sportsbook_weights(self):
        weights = _default_sportsbook_weights(self.sportsbook_mapping)
        try:
            prefs = load_user_prefs()
            saved = prefs.get('sportsbook_weights') if isinstance(prefs, dict) else None
            if isinstance(saved, dict):
                for key, value in saved.items():
                    try:
                        weights[key] = float(value)
                    except Exception:
                        pass
        except Exception:
            pass
        self._sportsbook_weights = weights

    def _on_odds_format_changed(self, label: str):
        fmt = self._odds_format_map.get(label, 'american')
        self._display_odds_format = fmt
        self._api_odds_format = fmt if fmt in ('american', 'decimal') else 'decimal'
        try:
            prefs = load_user_prefs()
            if not isinstance(prefs, dict):
                prefs = {}
            prefs['odds_format'] = fmt
            save_user_prefs(prefs)
        except Exception:
            pass
        self.update_table()

    def _format_odds_value(self, price):
        if price is None:
            return "N/A"
        api_fmt = self._api_odds_format
        disp_fmt = self._display_odds_format
        try:
            if disp_fmt == api_fmt:
                if disp_fmt == 'american':
                    ival = int(round(float(price)))
                    return f"{ival:+d}" if ival > 0 else f"{ival}"
                if disp_fmt == 'decimal':
                    return f"{float(price):.2f}"
            prob = odds_converter(api_fmt, 'probability', price)
            if disp_fmt == 'probability':
                return f"{prob:.1%}"
            converted = odds_converter('probability', disp_fmt, prob)
            if disp_fmt == 'american':
                ival = int(round(float(converted)))
                return f"{ival:+d}" if ival > 0 else f"{ival}"
            if disp_fmt == 'decimal':
                return f"{float(converted):.2f}"
            return str(converted)
        except Exception:
            return str(price)

    def _format_probability(self, prob):
        if prob is None:
            return "N/A"
        disp_fmt = self._display_odds_format
        try:
            if disp_fmt == 'probability':
                return f"{prob:.1%}"
            converted = odds_converter('probability', disp_fmt, prob)
            if disp_fmt == 'american':
                ival = int(round(float(converted)))
                return f"{ival:+d}" if ival > 0 else f"{ival}"
            if disp_fmt == 'decimal':
                return f"{float(converted):.2f}"
            return str(converted)
        except Exception:
            return "N/A"


class CurrentOddsWindow(OddsWindowMixin, QMainWindow):
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
        self._display_odds_format = ODDS_FORMAT
        self._api_odds_format = ODDS_FORMAT if ODDS_FORMAT in ("american", "decimal") else "decimal"
        self._sport_title_map = self._build_sport_title_map()
        self._load_sportsbook_weights()
        self._event_ids_map = {}
        self._event_row_groups = []
        self._row_event_map = []
        self._last_odds_data = None
        self.sport_selection_window = None

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)
        self.central_widget.setLayout(main_layout)

        # Filters bar
        filters_box = QWidget(self)
        filters_box.setObjectName("filtersBox")
        filters_layout = QVBoxLayout(filters_box)
        filters_layout.setContentsMargins(8, 6, 8, 6)
        filters_layout.setSpacing(4)

        filters_title = QLabel("Filters", self)
        filters_title.setStyleSheet("font-weight:700;")
        filters_layout.addWidget(filters_title)
        self.sport_summary_label = QLabel("", self)
        self.sport_summary_label.setStyleSheet("font-size:11px;color:gray;")
        filters_layout.addWidget(self.sport_summary_label)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        # Sport Selection Dropdown
        self.sport_dropdown = QComboBox(self)
        for sport_key in self.selected_sports:
            self.sport_dropdown.addItem(self._display_sport_title(sport_key), sport_key)
        # connect after table is created
        top_bar.addWidget(self.sport_dropdown)

        # Market Selection Dropdown
        self.market_dropdown = QComboBox(self)
        self._market_label_map = {
            "h2h": "Moneyline",
            "spreads": "Spreads",
            "totals": "Totals",
        }
        for key, label in self._market_label_map.items():
            self.market_dropdown.addItem(label, key)
        # connect after table is created
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
        # connect after table is created
        self.live_counts_label = QLabel("Pre-Game: -- | Live: --", self)
        top_bar.addWidget(self.live_counts_label)

        top_bar.addStretch(1)

        # Search box (filters will be wired later)
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Search events...")
        try:
            self.search_input.setClearButtonEnabled(True)
        except Exception:
            pass
        self.search_input.setMinimumWidth(200)
        # connect after table is created
        top_bar.addWidget(self.search_input)

        # Odds format selector
        self.odds_format_dropdown = QComboBox(self)
        self.odds_format_dropdown.addItems(["American", "Decimal", "Probability"])
        self._odds_format_map = {
            "American": "american",
            "Decimal": "decimal",
            "Probability": "probability",
        }
        self._load_odds_format_pref()
        # connect after table is created
        top_bar.addWidget(self.odds_format_dropdown)

        filters_layout.addLayout(top_bar)
        main_layout.addWidget(filters_box)

        # restore last sport if available
        try:
            prefs = load_user_prefs()
            last_sport = prefs.get('last_sport') if isinstance(prefs, dict) else None
            if last_sport in self.selected_sports:
                self.sport_dropdown.setCurrentIndex(self.selected_sports.index(last_sport))
        except Exception:
            pass
        self.current_sport = self.sport_dropdown.currentData() or self.current_sport
        self._update_sport_summary()

        quick_actions = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh", self)
        self.refresh_button.clicked.connect(self.update_table)
        quick_actions.addWidget(self.refresh_button)
        self.export_button = QPushButton("Export CSV", self)
        self.export_button.clicked.connect(self._export_csv)
        quick_actions.addWidget(self.export_button)
        self.reset_filters_button = QPushButton("Reset Filters", self)
        self.reset_filters_button.clicked.connect(self._reset_filters)
        quick_actions.addWidget(self.reset_filters_button)
        quick_actions.addStretch(1)
        main_layout.addLayout(quick_actions)

        # Status row (compact)
        status_row = QHBoxLayout()
        self.requests_remaining_label = QLabel("Requests Remaining: Retrieving...", self)
        status_row.addWidget(self.requests_remaining_label)

        # Event IDs load status
        self.event_ids_status_label = QLabel("Event IDs: Not loaded", self)
        status_row.addWidget(self.event_ids_status_label)
        self.last_refresh_label = QLabel("Last refresh: --", self)
        status_row.addWidget(self.last_refresh_label)
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
            vheader = self.table.verticalHeader()
            if vheader is not None:
                vheader.setVisible(False)
        except Exception:
            pass
        self.table.setSortingEnabled(False)

        board_title = QLabel("Odds Board", self)
        board_title.setStyleSheet("font-weight:700; font-size:15px;")
        main_layout.addWidget(board_title)
        main_layout.addWidget(self.table)

        # Now that the table exists, connect update triggers safely
        try:
            self.sport_dropdown.currentIndexChanged.connect(self._on_sport_changed)
            self.market_dropdown.currentIndexChanged.connect(self.update_table)
            self.live_toggle_group.buttonClicked.connect(lambda _: self.update_table())
            self.search_input.textChanged.connect(self._filter_events_list)
            self.odds_format_dropdown.currentTextChanged.connect(self._on_odds_format_changed)
        except Exception:
            pass

        self.update_table()

        try:
            self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
            self.table.cellDoubleClicked.connect(self._on_table_double_clicked)
        except Exception:
            pass

        # Legend explaining icons and consensus
        self.legend_label = QLabel("Legend: Consensus = weighted odds (user-defined sharpness).", self)
        self.legend_label.setStyleSheet("font-size:11px;color:gray;")
        main_layout.addWidget(self.legend_label)

        button_layout = QHBoxLayout()
        self.back_button = QPushButton("Back to Home", self)
        self.back_button.clicked.connect(self.go_back)
        button_layout.addWidget(self.back_button)

        main_layout.addLayout(button_layout)

        self.update_requests_remaining()

        # start background fetch of event ids for all matchup sports
        try:
            self._event_ids_worker = EventIdsWorker(_require_odds_api(), self.selected_sports)
            self._event_ids_worker.finished.connect(self.set_event_ids_map)
            self._event_ids_worker.start()
        except Exception as e:
            print(f"Failed to start event id worker: {e}")

    def _on_sport_changed(self, idx: int):
        sport_key = self.sport_dropdown.itemData(idx) or self.sport_dropdown.currentText()
        self.update_sport(sport_key)

    def _current_market_key(self) -> str:
        return self.market_dropdown.currentData() or self.market_dropdown.currentText()

    def update_sport(self, sport):
        self.current_sport = sport
        self._update_sport_summary()
        try:
            prefs = load_user_prefs()
            if not isinstance(prefs, dict):
                prefs = {}
            prefs['last_sport'] = sport
            save_user_prefs(prefs)
        except Exception:
            pass
        self.update_table()

    def set_event_ids_map(self, mapping: dict):
        """Store event id mapping and update UI label."""
        try:
            self._event_ids_map = mapping or {}
            total = sum(len(v) for v in self._event_ids_map.values()) if isinstance(self._event_ids_map, dict) else 0
            self.event_ids_status_label.setText(f"Event IDs: {total} loaded")
        except Exception:
            self.event_ids_status_label.setText("Event IDs: Error")

    def go_back(self):
        self.startup_window = StartupWindow()
        self.startup_window.show()
        self.close()

    def update_table(self):
        if not hasattr(self, "table"):
            return
        self.table.clear()
        self.table.setRowCount(0)
        # clear cached row->event mapping
        self._row_event_map = []
        self._last_odds_data = None

        try:
            odds_data = self.fetch_odds_data()
            self._update_live_counts(odds_data)
            odds_data = self._filter_by_live_toggle(odds_data)
            # cache fetched data for detail views
            self._last_odds_data = odds_data
            # If market is spreads or totals, compute consensus point per event and try
            # to fetch event-level odds for that exact point to make apples-to-apples comparisons.
            market_type = self._current_market_key()
            if market_type in ('spreads', 'totals') and isinstance(odds_data, list):
                if market_type == 'totals':
                    # totals: use alternate_totals from event odds to pick a mode point
                    try:
                        remaining = _require_odds_api().get_remaining_requests()
                    except Exception:
                        remaining = 0

                    needed = len(odds_data or [])
                    if needed > 0 and remaining >= needed:
                        for event in odds_data:
                            eid = event.get('id')
                            if not eid:
                                continue
                            try:
                                ev_odds = _require_odds_api().get_event_odds(
                                    self.current_sport,
                                    eid,
                                    markets='alternate_totals',
                                    odds_format=self._api_odds_format,
                                    bookmakers=','.join(self.display_sportsbooks)
                                )
                                if isinstance(ev_odds, list) and len(ev_odds) > 0:
                                    ev = ev_odds[0]
                                    cp, _ = compute_consensus_point(
                                        ev,
                                        'totals',
                                        sportsbook_weights=self._sportsbook_weights,
                                        market_key='alternate_totals'
                                    )
                                    if cp is not None:
                                        try:
                                            event['_consensus_point'] = cp
                                        except Exception:
                                            pass
                                    for b in ev.get('bookmakers', []):
                                        orig_b = next((ob for ob in event.get('bookmakers', []) if ob.get('key') == b.get('key')), None)
                                        if not orig_b:
                                            continue
                                        ev_market = next((m for m in b.get('markets', []) if m.get('key') == 'alternate_totals'), None)
                                        if not ev_market:
                                            ev_market = None
                                        matched = []
                                        if ev_market and cp is not None:
                                            matched = [
                                                o for o in ev_market.get('outcomes', [])
                                                if 'point' in o and abs(float(o.get('point', 0)) - float(cp)) < 1e-6
                                            ]
                                        orig_market = next((m for m in orig_b.get('markets', []) if m.get('key') == 'totals'), None)
                                        if orig_market is not None and matched:
                                            orig_market['outcomes'] = matched
                                            try:
                                                event['_spread_method'] = 'alternate_totals'
                                            except Exception:
                                                pass
                            except Exception as e:
                                print(f"Failed to fetch event-level odds for {eid}: {e}")
                    # fallback to base totals consensus if alternate totals didn't yield one
                    for event in odds_data:
                        if event.get('_consensus_point') is None:
                            cp, _ = compute_consensus_point(event, 'totals', sportsbook_weights=self._sportsbook_weights)
                            if cp is not None:
                                event['_consensus_point'] = cp
                else:
                    # spreads: use alternate_spreads from event odds to pick a mode point
                    try:
                        remaining = _require_odds_api().get_remaining_requests()
                    except Exception:
                        remaining = 0

                    needed = len(odds_data or [])
                    if needed > 0 and remaining >= needed:
                        for event in odds_data:
                            eid = event.get('id')
                            if not eid:
                                continue
                            try:
                                ev_odds = _require_odds_api().get_event_odds(
                                    self.current_sport,
                                    eid,
                                    markets='alternate_spreads',
                                    odds_format=self._api_odds_format,
                                    bookmakers=','.join(self.display_sportsbooks)
                                )
                                # ev_odds is expected to be a list with single event dict
                                if isinstance(ev_odds, list) and len(ev_odds) > 0:
                                    ev = ev_odds[0]
                                    cp, fav = compute_consensus_point(
                                        ev,
                                        'spreads',
                                        sportsbook_weights=self._sportsbook_weights,
                                        market_key='alternate_spreads'
                                    )
                                    if cp is not None:
                                        try:
                                            event['_consensus_point'] = cp
                                            event['_consensus_favorite'] = fav
                                        except Exception:
                                            pass
                                    for b in ev.get('bookmakers', []):
                                        orig_b = next((ob for ob in event.get('bookmakers', []) if ob.get('key') == b.get('key')), None)
                                        if not orig_b:
                                            continue
                                        ev_market = next((m for m in b.get('markets', []) if m.get('key') == 'alternate_spreads'), None)
                                        if not ev_market:
                                            ev_market = None
                                        # Filter outcomes to those matching the absolute target point (both sides)
                                        matched = []
                                        if ev_market and cp is not None:
                                            matched = [
                                                o for o in ev_market.get('outcomes', [])
                                                if 'point' in o and abs(abs(float(o.get('point', 0))) - abs(cp)) < 1e-6
                                            ]
                                        # replace original spreads outcomes with the exact-point ones (even if empty)
                                        orig_market = next((m for m in orig_b.get('markets', []) if m.get('key') == 'spreads'), None)
                                        if orig_market is not None:
                                            orig_market['outcomes'] = matched
                                            try:
                                                event['_spread_method'] = 'alternate_spreads'
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
            try:
                self.last_refresh_label.setText(f"Last refresh: {datetime.now().strftime('%I:%M:%S %p')}")
            except Exception:
                pass

        except Exception as e:
            print(f"Error updating table: {e}")
            try:
                self.last_refresh_label.setText("Last refresh: error")
            except Exception:
                pass

    def fetch_odds_data(self):
        response = _require_odds_api().get_odds(
            sport=self.current_sport,
            markets=self._current_market_key(),
            odds_format=self._api_odds_format,
            bookmakers=','.join(self.display_sportsbooks)
        )
        print(response)
        return response

    def _export_csv(self):
        _export_table_to_csv(self, self.table, f"current_odds_{self.current_sport}")

    def _reset_filters(self):
        try:
            if self.selected_sports:
                self.sport_dropdown.setCurrentIndex(0)
        except Exception:
            pass
        try:
            self.market_dropdown.setCurrentIndex(0)
        except Exception:
            pass
        try:
            self.period_dropdown.setCurrentIndex(0)
        except Exception:
            pass
        try:
            self.pregame_button.setChecked(True)
        except Exception:
            pass
        try:
            self.search_input.setText("")
        except Exception:
            pass
        try:
            self._load_odds_format_pref()
        except Exception:
            pass
        self.update_table()

    def process_odds_data(self, odds_data):
        for event in odds_data:
            for bookmaker in event['bookmakers']:
                for market in bookmaker['markets']:
                    total_prob = sum(
                        odds_converter(self._api_odds_format, "probability", outcome["price"])
                        for outcome in market["outcomes"]
                    )
                    for outcome in market["outcomes"]:
                        prob = odds_converter(self._api_odds_format, "probability", outcome["price"])
                        no_vig_prob = prob / total_prob if total_prob > 0 else 0
                        outcome["no_vig_price"] = odds_converter("probability", self._api_odds_format, no_vig_prob)

    def add_headers(self):
        # Dynamic label: show 'Point' for totals market, 'Spread' for spreads
        point_label = "Point" if self._current_market_key() == 'totals' else "Spread"
        headers = ["Event", "Outcome", point_label, "Hold", "Best\nBook", "Positive\nEdge", "Kelly\nBet"] + [
            self.sportsbook_mapping[bookmaker]
            for bookmaker in self.display_sportsbooks
        ] + ["Consensus\nOdds"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        try:
            header = self.table.horizontalHeader()
            if header is None:
                return
            header.setFixedHeight(SPORTSBOOK_HEADER_HEIGHT)
            header.setSectionsMovable(False)
            header.setSectionsClickable(False)
            header.setHighlightSections(False)
            header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
            hdr_font = header.font()
            if hdr_font.pointSize() > 9:
                hdr_font.setPointSize(hdr_font.pointSize() - 1)
            header.setFont(hdr_font)
        except Exception:
            pass
        sportsbook_start = 7
        for offset, bookmaker_key in enumerate(self.display_sportsbooks):
            col_idx = sportsbook_start + offset
            try:
                header = self.table.horizontalHeader()
                if header is None:
                    continue
                header.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Fixed)
                self.table.setColumnWidth(col_idx, SPORTSBOOK_HEADER_HEIGHT)
            except Exception:
                pass
        try:
            header = self.table.horizontalHeader()
            if header is None:
                return
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
            header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
            header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(1, 170)
            self.table.setColumnWidth(2, 70)
            self.table.setColumnWidth(3, 60)
            self.table.setColumnWidth(4, 140)
            self.table.setColumnWidth(5, 80)
            self.table.setColumnWidth(6, 80)
            consensus_col_idx = len(self.display_sportsbooks) + 7
            if consensus_col_idx < self.table.columnCount():
                header.setSectionResizeMode(consensus_col_idx, QHeaderView.ResizeMode.Fixed)
                self.table.setColumnWidth(consensus_col_idx, 110)
        except Exception:
            pass
        # Improve header alignment and add helpful tooltips
        try:
            header = self.table.horizontalHeader()
            if header is None:
                return
            header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
            # Tooltip and emphasis for Consensus Odds column in the right table
            consensus_col_idx = len(self.display_sportsbooks) + 7
            item = self.table.horizontalHeaderItem(consensus_col_idx)
            if consensus_col_idx < self.table.columnCount() and item is not None:
                item.setToolTip("Consensus Odds: weighted consensus across selected sportsbooks (no-vig normalized)")
                try:
                    hdr_font = item.font()
                    hdr_font.setBold(True)
                    item.setFont(hdr_font)
                    item.setBackground(QBrush(QColor('#f0f0f0')))
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

    def _on_table_double_clicked(self, row: int, column: int):
        return

    def _desired_row_height(self) -> int:
        fm = QFontMetrics(self.table.font())
        market_key = None
        try:
            market_key = self._current_market_key()
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
            if vheader is None:
                return
            vheader.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
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
        market_key = self._current_market_key()

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
                        odds_converter(self._api_odds_format, 'probability', o.get('price'))
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
                            price_text = self._format_odds_value(price_display)
                            cell_text = str(price_text)
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
                                    cell_text = f"{point_text}\n{price_text}"
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
                                probabilities.append(odds_converter(self._api_odds_format, 'probability', no_vig))
                            else:
                                try:
                                    prob = odds_converter(self._api_odds_format, 'probability', outcome_data.get('price'))
                                    probabilities.append(prob)
                                except Exception:
                                    pass

                            weight = self._sportsbook_weights.get(bookmaker_key, 1.0)
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
                consensus_display = self._format_probability(consensus_probability)
                self.table.setItem(row, consensus_col, QTableWidgetItem(consensus_display))
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
                                user_probability = odds_converter(self._api_odds_format, 'probability', user_outcome.get('price'))
                                edge = consensus_probability - user_probability
                                kelly = kelly_criterion(
                                    consensus_probability, odds_converter(self._api_odds_format, 'decimal', user_outcome.get('price'))
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
            kelly_amount_text = "N/A"
            if best_sportsbook:
                try:
                    bankroll = float(self.selected_accounts.get(best_sportsbook, 0))
                    kelly_amount_text = f"${bankroll * best_kelly:,.2f}"
                except Exception:
                    kelly_amount_text = "N/A"
            self.table.setItem(row, kelly_col, QTableWidgetItem(kelly_amount_text))
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


class FuturesOddsWindow(OddsWindowMixin, QMainWindow):
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
        self._display_odds_format = ODDS_FORMAT
        self._api_odds_format = ODDS_FORMAT if ODDS_FORMAT in ("american", "decimal") else "decimal"
        self._load_odds_format_pref()
        self._sport_title_map = self._build_sport_title_map()
        self._load_sportsbook_weights()
        self.sport_selection_window = None

        # Filters bar
        filters_box = QWidget(self)
        filters_box.setObjectName("filtersBox")
        filters_layout = QVBoxLayout(filters_box)
        filters_layout.setContentsMargins(8, 6, 8, 6)
        filters_layout.setSpacing(4)

        filters_title = QLabel("Filters", self)
        filters_title.setStyleSheet("font-weight:700;")
        filters_layout.addWidget(filters_title)
        self.sport_summary_label = QLabel("", self)
        self.sport_summary_label.setStyleSheet("font-size:11px;color:gray;")
        filters_layout.addWidget(self.sport_summary_label)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)
        self.central_widget.setLayout(main_layout)

        status_row = QHBoxLayout()
        self.requests_remaining_label = QLabel("Requests Remaining: Retrieving...", self)
        status_row.addWidget(self.requests_remaining_label)
        self.last_refresh_label = QLabel("Last refresh: --", self)
        status_row.addWidget(self.last_refresh_label)
        status_row.addStretch(1)
        main_layout.addLayout(status_row)

        top_bar = QHBoxLayout()
        self.sport_dropdown = QComboBox(self)
        for sport_key in self.selected_sports:
            self.sport_dropdown.addItem(self._display_sport_title(sport_key), sport_key)
        self.sport_dropdown.currentIndexChanged.connect(self._on_sport_changed)
        top_bar.addWidget(self.sport_dropdown)

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
        self.live_toggle_group.buttonClicked.connect(lambda _: self.update_table())
        self.live_counts_label = QLabel("Pre-Game: -- | Live: --", self)
        top_bar.addWidget(self.live_counts_label)

        self.odds_format_dropdown = QComboBox(self)
        self.odds_format_dropdown.addItems(["American", "Decimal", "Probability"])
        self._odds_format_map = {
            "American": "american",
            "Decimal": "decimal",
            "Probability": "probability",
        }
        try:
            current_label = next(k for k, v in self._odds_format_map.items() if v == self._display_odds_format)
        except Exception:
            current_label = "American"
        idx = self.odds_format_dropdown.findText(current_label)
        if idx >= 0:
            self.odds_format_dropdown.setCurrentIndex(idx)
        self.odds_format_dropdown.currentTextChanged.connect(self._on_odds_format_changed)
        top_bar.addWidget(self.odds_format_dropdown)
        top_bar.addStretch(1)
        filters_layout.addLayout(top_bar)
        main_layout.addWidget(filters_box)

        # restore last sport if available
        try:
            prefs = load_user_prefs()
            last_sport = prefs.get('last_sport') if isinstance(prefs, dict) else None
            if last_sport in self.selected_sports:
                self.sport_dropdown.setCurrentIndex(self.selected_sports.index(last_sport))
        except Exception:
            pass
        self.current_sport = self.sport_dropdown.currentData() or self.current_sport
        self._update_sport_summary()

        quick_actions = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh", self)
        self.refresh_button.clicked.connect(self.update_table)
        quick_actions.addWidget(self.refresh_button)
        self.export_button = QPushButton("Export CSV", self)
        self.export_button.clicked.connect(self._export_csv)
        quick_actions.addWidget(self.export_button)
        self.reset_filters_button = QPushButton("Reset Filters", self)
        self.reset_filters_button.clicked.connect(self._reset_filters)
        quick_actions.addWidget(self.reset_filters_button)
        quick_actions.addStretch(1)
        main_layout.addLayout(quick_actions)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        try:
            self.table.setItemDelegate(ItemBackgroundDelegate(self.table))
        except Exception:
            pass
        main_layout.addWidget(self.table)
        self.update_table()

        button_layout = QHBoxLayout()
        self.back_button = QPushButton("Back to Home", self)
        self.back_button.clicked.connect(self.go_back)
        button_layout.addWidget(self.back_button)
        main_layout.addLayout(button_layout)

        self.update_requests_remaining()

    def _on_sport_changed(self, idx: int):
        sport_key = self.sport_dropdown.itemData(idx) or self.sport_dropdown.currentText()
        self.update_sport(sport_key)

    def update_sport(self, sport):
        self.current_sport = sport
        self._update_sport_summary()
        self.update_table()

    def update_table(self):
        self.table.clear()
        self.table.setRowCount(0)

        try:
            odds_data = self.fetch_odds_data()
            self._update_live_counts(odds_data)
            odds_data = self._filter_by_live_toggle(odds_data)
            self.process_odds_data(odds_data)
            self.add_headers()
            for event in odds_data:
                self.populate_table_rows(event)
            self.update_requests_remaining()
            self.table.resizeColumnsToContents()
            try:
                self.last_refresh_label.setText(f"Last refresh: {datetime.now().strftime('%I:%M:%S %p')}")
            except Exception:
                pass
        except Exception as e:
            print(f"Error updating table: {e}")
            try:
                self.last_refresh_label.setText("Last refresh: error")
            except Exception:
                pass

    def fetch_odds_data(self):
        response = _require_odds_api().get_odds(
            sport=self.current_sport,
            markets="outrights",
            odds_format=self._api_odds_format,
            bookmakers=','.join(self.display_sportsbooks)
        )
        print(response)
        return response

    def _export_csv(self):
        _export_table_to_csv(self, self.table, f"futures_odds_{self.current_sport}")

    def _reset_filters(self):
        try:
            if self.selected_sports:
                self.sport_dropdown.setCurrentIndex(0)
        except Exception:
            pass
        try:
            self.pregame_button.setChecked(True)
        except Exception:
            pass
        try:
            self._load_odds_format_pref()
        except Exception:
            pass
        self.update_table()

    def process_odds_data(self, odds_data):
        for event in odds_data:
            for bookmaker in event['bookmakers']:
                for market in bookmaker['markets']:
                    total_prob = sum(
                        odds_converter(self._api_odds_format, "probability", outcome["price"])
                        for outcome in market["outcomes"]
                    )
                    for outcome in market["outcomes"]:
                        prob = odds_converter(self._api_odds_format, "probability", outcome["price"])
                        no_vig_prob = prob / total_prob if total_prob > 0 else 0
                        outcome["no_vig_price"] = odds_converter("probability", self._api_odds_format, no_vig_prob)

    def add_headers(self):
        headers = ["Team", "Best\nBook", "Positive\nEdge", "Kelly\nBet"] + [
            self.sportsbook_mapping[bookmaker]
            for bookmaker in self.display_sportsbooks
        ] + ["Consensus\nOdds"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        try:
            header = self.table.horizontalHeader()
            if header is None:
                return
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            header.setSectionsMovable(False)
            header.setSectionsClickable(False)
            header.setHighlightSections(False)
            header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
            header.setFixedHeight(64)
            hdr_font = header.font()
            if hdr_font.pointSize() > 9:
                hdr_font.setPointSize(hdr_font.pointSize() - 1)
            header.setFont(hdr_font)
            for i in range(1, 4):
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(1, 160)
            self.table.setColumnWidth(2, 90)
            self.table.setColumnWidth(3, 90)
            consensus_col = len(self.display_sportsbooks) + 4
            if consensus_col < self.table.columnCount():
                header.setSectionResizeMode(consensus_col, QHeaderView.ResizeMode.Fixed)
                self.table.setColumnWidth(consensus_col, 110)
            for offset, _ in enumerate(self.display_sportsbooks):
                col_idx = 4 + offset
                header.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Fixed)
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
                            price_text = self._format_odds_value(outcome_data["price"])
                            self.table.setItem(row, col, QTableWidgetItem(str(price_text)))
                            try:
                                probabilities.append(
                                    odds_converter(self._api_odds_format, "probability", outcome_data["no_vig_price"])
                                )
                            except Exception:
                                pass

                            weight = self._sportsbook_weights.get(bookmaker_key, 1.0)
                            weights.append(weight)

            if probabilities:
                consensus_probability = sum(p * w for p, w in zip(probabilities, weights)) / sum(weights)
                consensus_display = self._format_probability(consensus_probability)

                best_sportsbook_col = 1
                edge_col = 2
                kelly_col = 3
                consensus_col = len(self.display_sportsbooks) + 4

                self.table.setItem(row, consensus_col, QTableWidgetItem(consensus_display))

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
                            user_probability = odds_converter(self._api_odds_format, "probability", user_outcome["price"])
                            edge = consensus_probability - user_probability
                            kelly = kelly_criterion(
                                consensus_probability, odds_converter(self._api_odds_format, "decimal", user_outcome["price"])
                            )

                            if edge > best_edge:
                                best_edge = edge
                                best_kelly = kelly
                                best_sportsbook = account_key

                self.table.setItem(row, best_sportsbook_col, QTableWidgetItem(self.sportsbook_mapping[best_sportsbook] if best_sportsbook else "N/A"))
                self.table.setItem(row, edge_col, QTableWidgetItem(f"{best_edge:.2%}"))
                kelly_amount_text = "N/A"
                if best_sportsbook:
                    try:
                        bankroll = float(self.selected_accounts.get(best_sportsbook, 0))
                        kelly_amount_text = f"${bankroll * best_kelly:,.2f}"
                    except Exception:
                        kelly_amount_text = "N/A"
                self.table.setItem(row, kelly_col, QTableWidgetItem(kelly_amount_text))
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

    def go_back(self):
        self.startup_window = StartupWindow()
        self.startup_window.show()
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
