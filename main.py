import time
import numpy as np
from core.logger_config import logger
from core.config import config
from core.automator import WarpAutomator
from core.audio_engine import get_audio_stream, load_wakeword_model
from core.ui import JarvisUI

def main():
    # Initialize components
    automator = WarpAutomator(config)
    model, wakeword_name = load_wakeword_model()
    pa, stream = get_audio_stream()
    ui = JarvisUI(wakeword_name)
    
    logger.info(f"Jarvis is listening for '{wakeword_name}'...")
    
    cooldown = 0
    volume_multiplier = config.get('volume_multiplier', 1.0)
    threshold = config.get('threshold', 0.4)
    cooldown_seconds = config.get('cooldown_seconds', 5)

    try:
        with ui.get_live() as live:
            while True:
                try:
                    # Update UI status
                    current_status = "Listening" if time.time() > cooldown else "Cooldown"
                    ui.update(status=current_status)

                    # Read audio from microphone
                    try:
                        audio_data = stream.read(1280, exception_on_overflow=False)
                        pcm = np.frombuffer(audio_data, dtype=np.int16)

                        # Apply volume multiplier
                        if volume_multiplier != 1.0:
                            pcm = (pcm * volume_multiplier).clip(-32768, 32767).astype(np.int16)

                        # Update UI volume
                        ui.update(volume=pcm)

                    except Exception as e:
                        logger.error(f"Microphone stream error: {e}. Attempting to reconnect...")
                        ui.update(status="Stream Error")
                        try:
                            stream.stop_stream()
                            stream.close()
                        except:
                            pass
                        time.sleep(2)
                        _, stream = get_audio_stream()
                        continue

                    # Prediction
                    prediction = model.predict(pcm)
                    hey_jarvis_key = next((k for k in prediction.keys() if wakeword_name in k), None)
                    
                    score = 0.0
                    if hey_jarvis_key:
                        score = float(prediction[hey_jarvis_key])
                    
                    ui.update(score=score)

                    if hey_jarvis_key and score > threshold and time.time() > cooldown:
                        logger.info(f"Wake word detected! (Score: {score:.2f})")
                        ui.update(status="Detected!", score=score)
                        automator.run_workflow()
                        cooldown = time.time() + cooldown_seconds
                        
                except Exception as e:
                    logger.error(f"Unexpected error in loop: {e}")
                    ui.update(status="Loop Error")
                    time.sleep(1)

    except KeyboardInterrupt:
        logger.info("Stopping Jarvis...")
    finally:
        # Cleanup
        try:
            stream.stop_stream()
            stream.close()
            pa.terminate()
        except:
            pass

if __name__ == "__main__":
    main()
