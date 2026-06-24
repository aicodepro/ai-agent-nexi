import speech_recognition as sr
import pyautogui

def automaticTyping():
    symbol_mapping = {
        "dot": ".",
        "comma": ",",
        "open bracket": "(",
        "close bracket": ")",
        "open curly bracket": "{",
        "close curly bracket": "}",
        "open square bracket": "[",
        "close square bracket": "]",
        "colon": ":",
        "semicolon": ";",
        "quote": "\"",
        "single quote": "'",
        "backslash": "\\",
        "forward slash": "/",
        "star": "*",
        "hash": "#",
        "dollar": "$",
        "percent": "%",
        "caret": "^",
        "and": "&",
        "underscore": "_",
        "equal": "=",
        "plus": "+",
        "minus": "-",
        "greater than": ">",
        "less than": "<",
        "pipe": "|",
        "exclamation": "!",
        "question": "?"
    }

    r = sr.Recognizer()
    
    while True:
        with sr.Microphone() as source:
            print('Listening...')
            r.pause_threshold = 0.8  # Faster response to pauses in speech
            r.energy_threshold = 300  # Adjust to reduce background noise
            r.adjust_for_ambient_noise(source, duration=1)
            audio = r.listen(source, 10, 6)

        try:
            print('Recognizing...')
            query = r.recognize_google(audio, language='en-in')
            print(f"User said: {query}")
            
            # Replace spoken words with corresponding symbols
            for word, symbol in symbol_mapping.items():
                query = query.replace(word, symbol)
            
            # Type the result at the current cursor position
            pyautogui.write(query.lower())

            # Exit the loop if the user says "quit"
            if "quit" in query.lower():
                break

        except sr.UnknownValueError:
            print("Sorry, I did not understand the audio.")
            continue
        except sr.RequestError as e:
            print(f"Could not request results; {e}")
            break

