import tkinter as tk
from threading import Event
from core.logger_config import logger

class SecurityDialog:
    def __init__(self, action_desc):
        self.action_desc = action_desc
        self.result = False
        self.confirmed_event = Event()
        self.root = None

    def _setup_ui(self):
        self.root = tk.Tk()
        self.root.title("Jarvis - Autorização de Segurança")
        
        # Stay on top
        self.root.attributes("-topmost", True)
        
        # Window size and position
        window_width = 400
        window_height = 200
        
        try:
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
        except Exception:
            # Fallback if winfo_screenwidth fails (e.g. in some headless environments)
            screen_width = 1920
            screen_height = 1080
        
        center_x = int(screen_width/2 - window_width / 2)
        center_y = int(screen_height/2 - window_height / 2)
        
        self.root.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
        self.root.resizable(False, False)

        # Style
        self.root.configure(bg='#2c3e50')
        label_font = ("Arial", 12, "bold")
        button_font = ("Arial", 10, "bold")

        # Label
        label = tk.Label(
            self.root, 
            text=f"Deseja executar:\n\n'{self.action_desc}'?", 
            font=label_font,
            bg='#2c3e50',
            fg='white',
            wraplength=350,
            justify="center"
        )
        label.pack(pady=30)

        # Buttons Frame
        btn_frame = tk.Frame(self.root, bg='#2c3e50')
        btn_frame.pack(pady=10)

        def on_sim():
            self.result = True
            self.confirmed_event.set()
            self.root.destroy()

        def on_nao():
            self.result = False
            self.confirmed_event.set()
            self.root.destroy()

        sim_btn = tk.Button(
            btn_frame, 
            text="SIM", 
            command=on_sim,
            width=10,
            bg='#27ae60',
            fg='white',
            font=button_font,
            activebackground='#2ecc71'
        )
        sim_btn.pack(side=tk.LEFT, padx=20)

        nao_btn = tk.Button(
            btn_frame, 
            text="NÃO", 
            command=on_nao,
            width=10,
            bg='#c0392b',
            fg='white',
            font=button_font,
            activebackground='#e74c3c'
        )
        nao_btn.pack(side=tk.LEFT, padx=20)

        # Handle window close button (X)
        self.root.protocol("WM_DELETE_WINDOW", on_nao)

    def ask(self):
        """Shows the dialog and blocks until the user responds."""
        try:
            self._setup_ui()
            logger.info(f"Showing security dialog for action: {self.action_desc}")
            self.root.mainloop()
        except Exception as e:
            logger.error(f"Error in SecurityDialog: {e}")
            self.result = False
            self.confirmed_event.set()
        
        return self.result

    def close(self):
        """Closes the dialog programmatically."""
        if self.root:
            try:
                self.root.after(0, self.root.destroy)
            except Exception:
                pass
            self.confirmed_event.set()
