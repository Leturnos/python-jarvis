import openwakeword
from openwakeword.model import Model

import pyaudio
import subprocess
import numpy as np
import time
import pyautogui
import pyperclip
import psutil
import pygetwindow as gw
import win32gui
import win32con

import yaml

# Load configuration from config.yaml
def load_config():
    try:
        with open("config.yaml", "r") as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading config.yaml: {e}")
        return {
            'warp_path': r"C:\Users\Leandro\AppData\Local\Programs\Warp\Warp.exe",
            'threshold': 0.4,
            'cooldown_seconds': 5,
            'commands': [r"cd C:\Programacao\MVP", "gemini"]
        }

config = load_config()

# carregar modelo (baixa automaticamente se necessário)
import openwakeword
model_paths = openwakeword.get_pretrained_model_paths()
hey_jarvis_path = [p for p in model_paths if "hey_jarvis" in p]
model = Model(wakeword_model_paths=hey_jarvis_path)

# iniciar microfone
pa = pyaudio.PyAudio()

def start_stream():
    return pa.open(
        rate=16000,
        channels=1,
        format=pyaudio.paInt16,
        input=True,
        frames_per_buffer=1280
    )

stream = start_stream()

print("Ouvindo por 'hey jarvis'...")

warp_path = config['warp_path']

def warp_aberto():
    try:
        for p in psutil.process_iter(['name']):
            if p.info['name'] and "warp" in p.info['name'].lower():
                return True
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass
    return False

import win32process

def encontrar_janela_warp():
    try:
        # 1. Pegar todos os PIDs de processos que são "warp"
        warp_pids = set()
        for p in psutil.process_iter(['pid', 'name']):
            if p.info['name'] and "warp" in p.info['name'].lower():
                warp_pids.add(p.info['pid'])
        
        if not warp_pids:
            return None

        # 2. Procurar uma janela que pertença a um desses PIDs
        for w in gw.getAllWindows():
            if w._hWnd:
                try:
                    _, pid = win32process.GetWindowThreadProcessId(w._hWnd)
                    if pid in warp_pids and w.title:
                        # Filtra janelas fantasmas ou sem título (opcional)
                        return w
                except:
                    continue
    except Exception as e:
        print(f"Error searching for Warp window: {e}")
                
    # fallback para busca por título se o método por PID falhar
    palavras_chave = ('warp', 'ready', 'working', 'mvp')
    for w in gw.getAllWindows():
        if w.title and any(kw in w.title.lower() for kw in palavras_chave):
            return w
            
    return None

def ativar_janela(win):
    try:
        # Usar win32gui diretamente para restaurar — mais confiável que win.restore()
        hwnd = win._hWnd
        
        # Se estiver minimizada, restaura
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        else:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        
        time.sleep(0.5)

        try:
            # Truque para permitir SetForegroundWindow: simular pressionar a tecla ALT
            import win32com.client
            shell = win32com.client.Dispatch("WScript.Shell")
            shell.SendKeys('%') 
            
            win32gui.SetForegroundWindow(hwnd)
        except Exception as e:
            print(f"Aviso: Erro ao dar foco via SetForegroundWindow: {e}")
            win.activate()

        time.sleep(0.4)

        # Clicar no centro para garantir foco no terminal
        centro_x = win.left + win.width // 2
        centro_y = win.top + win.height // 2
        pyautogui.click(centro_x, centro_y)
        time.sleep(0.3)
    except Exception as e:
        print(f"Error activating window: {e}")

def digitar(texto):
    """Cola texto via clipboard — resolve problemas com caracteres especiais como \\"""
    try:
        pyperclip.copy(texto)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.2)
    except Exception as e:
        print(f"Error typing text: {e}")

cooldown = 0

while True:
    try:
        # Ler áudio do microfone
        try:
            audio_data = stream.read(1280, exception_on_overflow=False)
            pcm = np.frombuffer(audio_data, dtype=np.int16)
        except Exception as e:
            print(f"Microphone stream error: {e}. Attempting to reconnect...")
            try:
                stream.stop_stream()
                stream.close()
            except:
                pass
            time.sleep(2)
            stream = start_stream()
            continue

        prediction = model.predict(pcm)

        # O openwakeword costuma usar o nome do arquivo (sem extensão) como chave.
        hey_jarvis_key = next((k for k in prediction.keys() if "hey_jarvis" in k), None)

        if hey_jarvis_key and prediction[hey_jarvis_key] > config['threshold'] and time.time() > cooldown:
            print(f"Jarvis detectado! (Score: {prediction[hey_jarvis_key]:.2f})")

            if not warp_aberto():
                print("Abrindo Warp...")
                subprocess.Popen(warp_path)
                time.sleep(4)

            if warp_aberto():
                win = encontrar_janela_warp()

                if win:
                    print(f"Ativando janela: {win.title}")
                    ativar_janela(win)

                    # Abrir nova aba
                    pyautogui.hotkey('ctrl', 'shift', 't')
                    time.sleep(0.8)

                    try:
                        for cmd in config['commands']:
                            digitar(cmd)
                            pyautogui.press("enter")
                            time.sleep(0.5)
                        print("Comandos executados com sucesso.")
                    except Exception as e:
                        print(f"Erro ao executar comandos no Warp: {e}")
                else:
                    print("Janela do Warp não encontrada.")
            else:
                print("Warp não abriu a tempo, pulando comandos.")

            cooldown = time.time() + config['cooldown_seconds']
            
    except KeyboardInterrupt:
        print("\nStopping Jarvis...")
        break
    except Exception as e:
        print(f"Unexpected error in main loop: {e}")
        time.sleep(1)

# Limpeza ao fechar
try:
    stream.stop_stream()
    stream.close()
    pa.terminate()
except:
    pass
