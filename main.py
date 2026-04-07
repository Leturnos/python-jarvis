import time
import numpy as np
from core.logger_config import logger
from core.config import config
from core.automator import WarpAutomator
from core.audio_engine import get_audio_stream, load_wakeword_model

def main():
    # Initialize components
    automator = WarpAutomator(config)
    model, wakeword_name = load_wakeword_model()
    pa, stream = get_audio_stream()
    
    logger.info(f"Jarvis is listening for '{wakeword_name}'...")
    
    cooldown = 0
    volume_multiplier = config.get('volume_multiplier', 1.0)
    threshold = config.get('threshold', 0.4)
    cooldown_seconds = config.get('cooldown_seconds', 5)

    try:
        while True:
            try:
                # Read audio from microphone
                try:
                    audio_data = stream.read(1280, exception_on_overflow=False)
                    pcm = np.frombuffer(audio_data, dtype=np.int16)

                    # Apply volume multiplier
                    if volume_multiplier != 1.0:
                        pcm = (pcm * volume_multiplier).clip(-32768, 32767).astype(np.int16)

                except Exception as e:
                    logger.error(f"Microphone stream error: {e}. Attempting to reconnect...")
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

                if hey_jarvis_key and prediction[hey_jarvis_key] > threshold and time.time() > cooldown:
                    logger.info(f"Wake word detected! (Score: {prediction[hey_jarvis_key]:.2f})")
                    automator.run_workflow()
                    cooldown = time.time() + cooldown_seconds
                    
            except Exception as e:
                logger.error(f"Unexpected error in loop: {e}")
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
