from PySide6.QtWidgets import QVBoxLayout
from qfluentwidgets import BodyLabel, ProgressBar, SimpleCardWidget, TitleLabel


class StatusCardWidget(SimpleCardWidget):
    def __init__(self, wakeword_name, parent=None):
        super().__init__(parent)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(10)

        self.title = TitleLabel("Jarvis Status")
        self.layout.addWidget(self.title)

        self.wakeword_label = BodyLabel(f"Listening for: {wakeword_name}")
        self.wakeword_label.setObjectName("WakeWordLabel")
        self.layout.addWidget(self.wakeword_label)

        self.state_label = BodyLabel("State: IDLE")
        self.state_label.setObjectName("StateLabel")
        self.layout.addWidget(self.state_label)

        self.status_label = BodyLabel("Status: Initializing...")
        self.layout.addWidget(self.status_label)

        self.score_label = BodyLabel("Wake Word Score: 0.00")
        self.layout.addWidget(self.score_label)

        self.vol_progress = ProgressBar()
        self.vol_progress.setRange(0, 100)
        self.vol_progress.setValue(0)
        self.layout.addWidget(self.vol_progress)

    def update_from_snapshot(self, snapshot):
        self.status_label.setText(f"Status: {snapshot['status']}")
        self.score_label.setText(f"Wake Word Score: {snapshot['score']:.2f}")
        self.vol_progress.setValue(snapshot["volume"])

        # State Colors handling
        state = snapshot["state"]
        self.state_label.setText(f"State: {state.name}")

        # Use inline color override ONLY for dynamic state colors, standard styles go in QSS
        state_colors = {
            "IDLE": "#00ff00",
            "LISTENING": "#ffff00",
            "THINKING": "#ff00ff",
            "CONFIRMING_DRY_RUN": "#0000ff",
            "EXECUTING": "#ff0000",
            "MUTED": "#888888",
            "ERROR": "#ff5555",
        }
        color = state_colors.get(state.name, "white")
        self.state_label.setStyleSheet(f"color: {color};")
