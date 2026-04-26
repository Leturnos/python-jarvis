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
        
        # Window size and position (Dynamic based on content)
        self.root.resizable(True, True) # Allow manual resize if needed
        self.root.configure(bg='#2c3e50')

        # Style
        label_font = ("Arial", 12, "bold")
        button_font = ("Arial", 10, "bold")

        # Container Frame to help with padding/centering
        container = tk.Frame(self.root, bg='#2c3e50', padx=20, pady=20)
        container.pack(expand=True, fill="both")

        # Label
        label = tk.Label(
            container, 
            text=f"Deseja executar:\n\n{self.action_desc}?", 
            font=label_font,
            bg='#2c3e50',
            fg='white',
            wraplength=500, # Increased width limit
            justify="center"
        )
        label.pack(pady=(0, 20))

        # Buttons Frame
        btn_frame = tk.Frame(container, bg='#2c3e50')
        btn_frame.pack()

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
            width=12,
            bg='#27ae60',
            fg='white',
            font=button_font,
            activebackground='#2ecc71'
        )
        sim_btn.pack(side=tk.LEFT, padx=10)

        nao_btn = tk.Button(
            btn_frame, 
            text="NÃO", 
            command=on_nao,
            width=12,
            bg='#c0392b',
            fg='white',
            font=button_font,
            activebackground='#e74c3c'
        )
        nao_btn.pack(side=tk.LEFT, padx=10)

        # Center window on screen after layout is calculated
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry('{}x{}+{}+{}'.format(width, height, x, y))

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

    def approve(self):
        """Externally approves the dialog."""
        self.result = True
        self.close()

    def reject(self):
        """Externally rejects the dialog."""
        self.result = False
        self.close()

    def close(self):
        """Closes the dialog programmatically."""
        if self.root:
            try:
                self.root.after(0, self.root.destroy)
            except Exception:
                pass
            self.confirmed_event.set()
