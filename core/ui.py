from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.live import Live
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table
from rich import box
import numpy as np
from core.state import state_manager, JarvisState

class JarvisUI:
    def __init__(self, wakeword_name):
        self.console = Console()
        if isinstance(wakeword_name, list):
            self.wakeword_name = ", ".join(wakeword_name)
        else:
            self.wakeword_name = wakeword_name
        self.status = "Initializing..."
        self.score = 0.0
        self.volume = 0
        self.layout = self.make_layout()

    def make_layout(self) -> Layout:
        layout = Layout(name="root")
        layout.split(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=3),
        )
        return layout

    def update_renderable(self):
        # Current State from StateManager
        current_state = state_manager.get_state()
        
        # Header
        self.layout["header"].update(
            Panel(
                f"[bold cyan]Jarvis AI Assistant[/bold cyan] - Listening for: [bold green]'{self.wakeword_name}'[/bold green]",
                box=box.ROUNDED,
                style="cyan"
            )
        )

        # Main Content
        main_table = Table.grid(expand=True)
        main_table.add_column(ratio=1)
        main_table.add_column(ratio=1)

        # Status and Score mapping
        state_colors = {
            JarvisState.IDLE: "green",
            JarvisState.LISTENING: "bold yellow",
            JarvisState.THINKING: "bold magenta",
            JarvisState.CONFIRMING_DRY_RUN: "bold blue",
            JarvisState.EXECUTING: "bold red",
            JarvisState.MUTED: "dim white",
            JarvisState.ERROR: "bold white on red"
        }
        
        color = state_colors.get(current_state, "white")
        
        status_panel = Panel(
            f"State: [{color}]{current_state.name}[/{color}]\n"
            f"Status: [white]{self.status}[/white]\n"
            f"Wake Word Score: [bold white]{self.score:.2f}[/bold white]",
            title="Monitoring",
            box=box.ROUNDED
        )

        # Volume Meter
        vol_progress = Progress(
            TextColumn("[bold blue]Volume"),
            BarColumn(bar_width=None),
            TextColumn("{task.percentage:>3.0f}%"),
        )
        vol_task = vol_progress.add_task("volume", total=100)
        vol_progress.update(vol_task, completed=min(self.volume, 100))

        volume_panel = Panel(vol_progress, title="Microphone", box=box.ROUNDED)

        main_table.add_row(status_panel, volume_panel)
        self.layout["main"].update(main_table)

        # Footer
        self.layout["footer"].update(
            Panel(
                "Press [bold red]Ctrl+C[/bold red] to stop.",
                box=box.ROUNDED,
                style="dim"
            )
        )

    def update(self, status=None, score=None, volume=None):
        if status is not None:
            self.status = status
        if score is not None:
            self.score = score
        if volume is not None:
            # Convert raw audio volume to 0-100 scale (rough approximation)
            self.volume = int(np.abs(volume).mean() / 500 * 100) if volume is not None else 0
        
        self.update_renderable()

    def get_live(self):
        self.update_renderable()
        return Live(self.layout, refresh_per_second=10, screen=True)
