import tkinter as tk
from tkinter import ttk
import threading
import keyboard
import queue
import win32gui
import win32con
from core.logger_config import logger
from core.plugin_manager import plugin_manager

class CommandPalette:
    def __init__(self, dispatcher):
        self.dispatcher = dispatcher
        self.root = None
        self.search_var = None
        self.listbox = None
        self.all_commands = []
        self.filtered_commands = []
        
        # We use a queue to safely communicate from the keyboard hook thread to the Tkinter thread
        self.cmd_queue = queue.Queue()
        self._is_visible = False
        
    def _fetch_commands(self):
        """Loads available commands from plugins and configurations."""
        self.all_commands = []
        # Load plugin intents
        intents = plugin_manager.get_intents()
        for i in intents:
            self.all_commands.append({
                "label": f"[Plugin] {i['intent']} - {i['description']}",
                "action_type": "plugin",
                "intent": i['intent'],
                "risk_level": i['risk_level']
            })
            
        # You could also load static wakewords/commands from config here if needed
        # For now, we focus on the newly created DSL intents.
        self.filtered_commands = self.all_commands.copy()

    def _create_ui(self):
        self.root = tk.Tk()
        self.root.title("Jarvis Command Palette")
        self.root.overrideredirect(True) # No title bar
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#1e1e1e")
        
        # Center the window
        window_width = 600
        window_height = 400
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        center_x = int(screen_width / 2 - window_width / 2)
        center_y = int(screen_height / 3 - window_height / 2) # Slightly higher than center
        self.root.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
        
        # Styling
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TFrame", background="#1e1e1e")
        style.configure("TEntry", fieldbackground="#2d2d2d", foreground="white", insertcolor="white", padding=10)
        
        frame = ttk.Frame(self.root, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        # Search Bar
        self.search_var = tk.StringVar()
        self.search_var.trace("w", self._on_search_change)
        
        search_entry = ttk.Entry(frame, textvariable=self.search_var, font=("Consolas", 14), width=50)
        search_entry.pack(fill=tk.X, pady=(0, 10))
        search_entry.focus_set()
        
        # Listbox for results
        self.listbox = tk.Listbox(
            frame, 
            font=("Consolas", 12), 
            bg="#2d2d2d", 
            fg="white", 
            selectbackground="#007acc", 
            selectforeground="white",
            borderwidth=0, 
            highlightthickness=0,
            activestyle='none'
        )
        self.listbox.pack(fill=tk.BOTH, expand=True)
        
        # Event Bindings
        self.root.bind("<Escape>", lambda e: self.hide())
        search_entry.bind("<Down>", lambda e: self._move_selection(1))
        search_entry.bind("<Up>", lambda e: self._move_selection(-1))
        self.root.bind("<Return>", lambda e: self._execute_selected())
        self.listbox.bind("<Double-Button-1>", lambda e: self._execute_selected())
        self.root.bind("<FocusOut>", lambda e: self.hide()) # Hide if user clicks away

        self._update_listbox()
        self._is_visible = True

    def _on_search_change(self, *args):
        query = self.search_var.get().lower()
        if not query:
            self.filtered_commands = self.all_commands.copy()
        else:
            self.filtered_commands = [
                cmd for cmd in self.all_commands 
                if query in cmd['label'].lower()
            ]
        self._update_listbox()

    def _update_listbox(self):
        self.listbox.delete(0, tk.END)
        for cmd in self.filtered_commands:
            self.listbox.insert(tk.END, cmd['label'])
        if self.filtered_commands:
            self.listbox.selection_set(0)
            
    def _move_selection(self, direction):
        if not self.filtered_commands:
            return
            
        current_selection = self.listbox.curselection()
        if not current_selection:
            new_index = 0
        else:
            new_index = current_selection[0] + direction
            
        # Wrap around
        if new_index < 0:
            new_index = len(self.filtered_commands) - 1
        elif new_index >= len(self.filtered_commands):
            new_index = 0
            
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(new_index)
        self.listbox.see(new_index)

    def _execute_selected(self):
        selection = self.listbox.curselection()
        if not selection:
            return
            
        index = selection[0]
        selected_cmd = self.filtered_commands[index]
        logger.info(f"Command Palette executing: {selected_cmd['label']}")
        
        self.hide()
        
        # Dispatch the command in a separate thread so we don't block the UI loop (if it was still alive)
        def run_action():
            if selected_cmd["action_type"] == "plugin":
                action_config = {
                    "action": "plugin",
                    "intent": selected_cmd["intent"],
                    "risk_level": selected_cmd["risk_level"]
                }
                # Directly call the handler to bypass wakeword logic
                self.dispatcher.last_input_text = selected_cmd["label"]
                self.dispatcher.last_input_source = "command_palette"
                self.dispatcher.last_confidence = 1.0
                self.dispatcher._handle_plugin(action_config)
                
        threading.Thread(target=run_action, daemon=True).start()

    def show(self):
        """Called from the hotkey thread to signal the UI thread to show."""
        self.cmd_queue.put("show")

    def hide(self):
        if self.root:
            self.root.destroy()
            self.root = None
            self._is_visible = False

    def _check_queue(self):
        """Periodically checks if the hotkey thread requested to show the UI."""
        try:
            while True:
                msg = self.cmd_queue.get_nowait()
                if msg == "show" and not self._is_visible:
                    self._fetch_commands()
                    self._create_ui()
                    
                    # Force window to foreground (Windows specific tricks)
                    if self.root:
                        self.root.update_idletasks()
                        hwnd = int(self.root.frame(), 16)
                        # Sometimes windows need a little help coming to the true front
                        try:
                            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
                            win32gui.SetForegroundWindow(hwnd)
                        except Exception:
                            pass
        except queue.Empty:
            pass
            
        # Only reschedule if root exists (UI is active)
        if self.root:
            self.root.after(100, self._check_queue)

    def _ui_loop(self):
        """The main Tkinter loop. Runs in its own thread."""
        # Create a hidden dummy root so the after() loop can run even when the palette is hidden
        dummy_root = tk.Tk()
        dummy_root.withdraw()
        
        def master_check():
            self._check_queue()
            dummy_root.after(100, master_check)
            
        master_check()
        dummy_root.mainloop()

    def start_background_loop(self):
        """Starts the Tkinter UI loop in a dedicated background thread and registers the hotkey."""
        ui_thread = threading.Thread(target=self._ui_loop, daemon=True)
        ui_thread.start()
        
        # Register global hotkey (Ctrl + Alt + P)
        hotkey = "ctrl+alt+p"
        keyboard.add_hotkey(hotkey, self.show)
        logger.info(f"Command Palette initialized. Hotkey: {hotkey}")
