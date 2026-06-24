import pyttsx3

print("[TTS_DEBUG] starting")
engine = pyttsx3.init()
engine.say("Nexi voice test.")
engine.runAndWait()
print("[TTS_DEBUG] finished")
