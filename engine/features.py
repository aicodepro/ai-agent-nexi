# features.py
import hugchat
import os
import re
import requests
import openai
from PIL import Image
import sqlite3
import struct
import subprocess
import time
import webbrowser
import pyaudio
import pyautogui
import speech_recognition as sr
from engine.config import ASSISTANT_NAME
from engine.helper import extract_yt_term, remove_words
from engine.command import speak, takecommand


_clap_listener_instance = None


def start_clap_if_enabled():
    global _clap_listener_instance
    if _clap_listener_instance is not None:
        return
    if os.getenv("CLAP_DETECTION_ENABLED", "false").lower() != "true":
        print("[CLAP] disabled")
        return
    from engine.clap_detector import start_clap_listener, stop_clap_listener
    from engine.hotword_helper import set_hotword_awake
    def on_clap_wake():
        print("[CLAP] wake detected")
        set_hotword_awake(True)
        speak("Yes sir?")
        print("[VOICE] listening_for_command source=clap")
        try:
            cmd = takecommand()
            if cmd:
                print(f"[VOICE] received: {cmd}")
                from engine.command_bus import submit_user_command
                submit_user_command(cmd, source="clap", mode="voice")
        except Exception as e:
            print(f"[VOICE] clap command error: {e}")
        set_hotword_awake(False)
        print("[CLAP] returning to listening")
    _clap_listener_instance = start_clap_listener(on_wake_callback=on_clap_wake)


def stop_clap_if_running():
    global _clap_listener_instance
    if _clap_listener_instance is not None:
        from engine.clap_detector import stop_clap_listener
        stop_clap_listener(_clap_listener_instance)
        _clap_listener_instance = None
from email.message import EmailMessage
import smtplib
try:
    import pywhatkit as kit
except Exception as e:
    print(f"[FEATURES] pywhatkit unavailable reason={type(e).__name__}")

    class _PyWhatKitFallback:
        def playonyt(self, search_term):
            from urllib.parse import quote_plus
            webbrowser.open("https://www.youtube.com/results?search_query=" + quote_plus(str(search_term)))

    kit = _PyWhatKitFallback()
from hugchat import hugchat
from pipes import quote
from time import sleep
import eel
con = sqlite3.connect("nexi.db")
cursor = con.cursor()
openai.api_key = os.getenv("OPENAI_API_KEY")
HUGCHAT_COOKIE_PATH = os.path.join(os.path.dirname(__file__), "cookies.json")
dictapp = {"commandprompt":"cmd","paint":"paint","word":"winword","excel":"excel","chrome":"chrome","vscode":"code","powerpoint":"powerpnt"}

@eel.expose
def playAssistantSound():
    music_dir = "www\\assets\\audio\\start_sound.mp3"
    try:
        from playsound import playsound as _ps
        _ps(music_dir)
    except ImportError:
        print("[SOUND] playsound not available, skipping startup sound")

    
def openCommand(query):
    query = query.replace(ASSISTANT_NAME, "")
    query = query.replace("open", "")
    query.lower()

    app_name = query.strip()

    if app_name != "":

        try:
            cursor.execute(
                'SELECT path FROM sys_command WHERE name IN (?)', (app_name,))
            results = cursor.fetchall()

            if len(results) != 0:
                speak("Opening "+query)
                os.startfile(results[0][0])

            elif len(results) == 0: 
                cursor.execute(
                'SELECT url FROM web_command WHERE name IN (?)', (app_name,))
                results = cursor.fetchall()
                
                if len(results) != 0:
                    speak("Opening "+query)
                    webbrowser.open(results[0][0])

                else:
                    speak("Opening "+query)
                    try:
                        os.system('start '+query)
                    except:
                        speak("not found")
        except:
            speak("some thing went wrong")

       

def PlayYoutube(query):
    search_term = extract_yt_term(query)
    if not search_term:
        search_term = query
    speak("Playing "+search_term+" on YouTube")
    kit.playonyt(search_term)


def hotword():
    import pvporcupine
    porcupine=None
    paud=None
    audio_stream=None
    access_key = os.getenv("PICOVOICE_ACCESS_KEY") or os.getenv("PORCUPINE_ACCESS_KEY")
    if not access_key:
        print("[HOTWORD] Picovoice key missing. Using SpeechRecognition fallback.")
        return
    try:
        porcupine=pvporcupine.create(access_key=access_key, keywords=[ASSISTANT_NAME])
        paud=pyaudio.PyAudio()
        audio_stream=paud.open(rate=porcupine.sample_rate,channels=1,format=pyaudio.paInt16,input=True,frames_per_buffer=porcupine.frame_length)
        
        while True:
            keyword=audio_stream.read(porcupine.frame_length, exception_on_overflow=False)
            keyword=struct.unpack_from("h"*porcupine.frame_length,keyword)

            keyword_index=porcupine.process(keyword)

            if keyword_index>=0:
                print("hotword detected")
                speak("Hello, I am Nexi")
                break
    except Exception as e:
        print(f"Hotword error: {e}")
    finally:
        if porcupine is not None:
            porcupine.delete()
        if audio_stream is not None:
            audio_stream.close()
        if paud is not None:
            paud.terminate()


def hotword_no_key():
    from engine.hotword_helper import is_nexi_hotword, check_hotword_cooldown, set_hotword_awake
    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    recognizer.energy_threshold = int(os.getenv("MIC_ENERGY_THRESHOLD", "250"))
    recognizer.pause_threshold = float(os.getenv("MIC_PAUSE_THRESHOLD", "0.5"))
    recognizer.phrase_threshold = 0.15
    recognizer.non_speaking_duration = 0.25

    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.6)
        backend = "porcupine" if (os.getenv("PICOVOICE_ACCESS_KEY") or os.getenv("PORCUPINE_ACCESS_KEY")) else "speech_recognition"
        print(f"[HOTWORD] backend={backend}")
        print(f"[HOTWORD] energy_threshold={recognizer.energy_threshold}")
        while True:
            try:
                audio = recognizer.listen(source, timeout=None, phrase_time_limit=2)
                query = recognizer.recognize_google(audio, language='en-in').lower()
                match = is_nexi_hotword(query)
                print(f"[HOTWORD] heard={query} match={match}")
                if match:
                    if not check_hotword_cooldown():
                        continue
                    print("[HOTWORD] detected=nexi")
                    set_hotword_awake(True)
                    speak("Hello, I am Nexi")
                    print("[VOICE] listening_for_command")
                    try:
                        max_record_seconds = float(os.getenv("ASR_MAX_RECORD_SECONDS", "6") or "6")
                        recognizer.pause_threshold = max(0.2, int(os.getenv("ASR_SILENCE_TIMEOUT_MS", "900") or "900") / 1000.0)
                        audio = recognizer.listen(source, timeout=10, phrase_time_limit=max_record_seconds)
                        cmd = ""
                        if (os.getenv("ASR_PROVIDER", "") or "").strip().lower() == "groq":
                            try:
                                from engine.groq_asr import transcribe_audio_bytes
                                cmd = transcribe_audio_bytes(audio.get_wav_data())
                            except Exception as e:
                                print(f"[ASR] hotword_groq_failed reason={type(e).__name__}", flush=True)
                        if not cmd:
                            cmd = recognizer.recognize_google(audio, language='en-in')
                        cmd = cmd.lower().strip()
                        if cmd:
                            print(f"[VOICE] received: {cmd}")
                            from engine.command_bus import submit_user_command
                            submit_user_command(cmd, source="hotword", mode="voice")
                    except sr.UnknownValueError:
                        print("[VOICE] no command heard")
                    except Exception as e:
                        print(f"[VOICE] command error: {e}")
                    recognizer.pause_threshold = float(os.getenv("MIC_PAUSE_THRESHOLD", "0.5"))
                    set_hotword_awake(False)
                    print("[HOTWORD] returning to listening")
            except sr.UnknownValueError:
                continue
            except Exception as e:
                print(f"Hotword listener error: {e}")
                time.sleep(0.5)



# find contacts
def findContact(query):
    
    words_to_remove = [ASSISTANT_NAME, 'make', 'a', 'to', 'phone', 'call', 'send', 'message', 'wahtsapp', 'video']
    query = remove_words(query, words_to_remove)

    try:
        query = query.strip().lower()
        cursor.execute("SELECT mobile_no FROM contacts WHERE LOWER(name) LIKE ? OR LOWER(name) LIKE ?", ('%' + query + '%', query + '%'))
        results = cursor.fetchall()
        print(results[0][0])
        mobile_number_str = str(results[0][0])

        if not mobile_number_str.startswith('+91'):
            mobile_number_str = '+91' + mobile_number_str

        return mobile_number_str, query
    except:
        speak('not exist in contacts')
        return 0, 0
    
def whatsApp(mobile_no, message, flag, name):
    

    if flag == 'message':
        target_tab = 12
        nexi_message = "message send successfully to "+name

    elif flag == 'call':
        target_tab = 7
        message = ''
        nexi_message = "calling to "+name

    else:
        target_tab = 6
        message = ''
        nexi_message = "staring video call with "+name


    # Encode the message for URL
    encoded_message = quote(message)
    print(encoded_message)
    # Construct the URL
    whatsapp_url = f"whatsapp://send?phone={mobile_no}&text={encoded_message}"

    # Construct the full command
    full_command = f'start "" "{whatsapp_url}"'

    # Open WhatsApp with the constructed URL using cmd.exe
    subprocess.run(full_command, shell=True)
    time.sleep(5)
    subprocess.run(full_command, shell=True)
    
    pyautogui.hotkey('ctrl', 'f')

    for i in range(1, target_tab):
        pyautogui.hotkey('tab')

    pyautogui.hotkey('enter')
    speak(nexi_message)

# chat bot 
def strip_reasoning(text):
    text = re.sub(r'<thinking>.*?</thinking>', '', text, flags=re.DOTALL)
    text = re.sub(r'<T\$\$.*?</T\$\$>', '', text, flags=re.DOTALL)
    text = re.sub(r'<.*?</.*?>', '', text, flags=re.DOTALL)
    lines = text.splitlines()
    cleaned = []
    in_thinking = False
    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith('...'):
            if in_thinking:
                in_thinking = False
                continue
            in_thinking = True
            continue
        if in_thinking:
            if stripped.endswith('...') or stripped.endswith('...'):
                in_thinking = False
            continue
        cleaned.append(line)
    result = '\n'.join(cleaned).strip()
    return result if result else text.strip()

def ask_hugchat(prompt):
    if not os.path.exists(HUGCHAT_COOKIE_PATH):
        raise FileNotFoundError(f"Missing HugChat cookies file: {HUGCHAT_COOKIE_PATH}")

    chatbot = hugchat.ChatBot(
        cookie_path=HUGCHAT_COOKIE_PATH,
        system_prompt="You are Nexi, a concise desktop assistant. Answer directly in one or two sentences with no reasoning preamble."
    )
    conversation_id = chatbot.new_conversation()
    chatbot.change_conversation(conversation_id)
    response = chatbot.chat(prompt)
    return strip_reasoning(str(response)).strip()


def chatWithGPT(prompt):
    try:
        response_text = ask_hugchat(prompt)
        speak(response_text)
        return response_text
    except Exception as e:
        print(f"Error: {e}")
        speak("Sorry, I couldn't connect to the AI service.")
        return "I'm having trouble accessing the AI service right now."
def generateImageFromPrompt(prompt):
    """Generate an image from a prompt using OpenAI's API."""
    try:
        speak("Generating image, please wait...")
        # Using the available DALL-E model (e.g., dall-e-3)
        response = openai.Image.create(
            model="dall-e-3",  # You can switch this to dall-e-2 if needed
            prompt=prompt,
            n=1,
            size="1024x1024",
            response_format="url"  # Ensures the response is a URL
        )
        image_url = response['data'][0]['url']
        res = requests.get(image_url)
        
        # Save the image locally
        with open("generated_image.png", "wb") as image:
            image.write(res.content)
        
        # Open and display the image
        img = Image.open("generated_image.png")
        img.show()
        
        speak("Here is the image you requested.")
    except Exception as e:
        print(f"Error: {e}")
        speak("Sorry, I couldn't generate the image.")
# android automation



def closeappweb(query):
    speak("Closing, sir")
    if "one tab" in query or "1 tab" in query:
        pyautogui.hotkey("ctrl", "w")
        speak("Tab closed")
    elif "2 tab" in query:
        pyautogui.hotkey("ctrl", "w")
        sleep(0.5)
        pyautogui.hotkey("ctrl", "w")
        speak("Tabs closed")
    elif "3 tab" in query:
        pyautogui.hotkey("ctrl", "w")
        sleep(0.5)
        pyautogui.hotkey("ctrl", "w")
        sleep(0.5)
        pyautogui.hotkey("ctrl", "w")
        speak("Tabs closed")
    elif "4 tab" in query:
        pyautogui.hotkey("ctrl", "w")
        sleep(0.5)
        pyautogui.hotkey("ctrl", "w")
        sleep(0.5)
        pyautogui.hotkey("ctrl", "w")
        sleep(0.5)
        pyautogui.hotkey("ctrl", "w")
        speak("Tabs closed")
    elif "5 tab" in query:
        pyautogui.hotkey("ctrl", "w")
        sleep(0.5)
        pyautogui.hotkey("ctrl", "w")
        sleep(0.5)
        pyautogui.hotkey("ctrl", "w")
        sleep(0.5)
        pyautogui.hotkey("ctrl", "w")
        sleep(0.5)
        pyautogui.hotkey("ctrl", "w")
        speak("Tabs closed")
    else:
        # Route every close through kill_process so the browser-protection guard
        # applies here too (never force-kill Chrome and lose the user's tabs).
        from engine.control.process_controller import kill_process
        dictapp = {"commandprompt":"cmd", "paint":"paint", "word":"winword", "excel":"excel", "chrome":"chrome", "vscode":"code", "powerpoint":"powerpnt"}
        keys = list(dictapp.keys())
        for app in keys:
            if app in query:
                result = kill_process(app)
                speak(getattr(result, "message", None) or f"Closed {app}")


# --- Brain provider chain --------------------------------------------------
#
# Default: Gemini Flash only. HugChat and Lightning stay opt-in so stale
# cookies or old Lightning credentials cannot hijack judge-demo Q&A.

BRAIN_FAILURE_USER_MESSAGE = "I can't connect to my brain right now, but local actions are working."
_ALL_PROVIDERS_FAILED = BRAIN_FAILURE_USER_MESSAGE
_brain_fail_until = 0.0

# Substrings that mark a stale "error" response we should treat as a failure
# even when the provider returned 200 / no exception.
_FAILURE_MARKERS = (
    "not configured",
    "not ready",
    "could not connect",
    "can't connect",
    "couldn't connect",
    "trouble reaching",
    "i don't have an answer",
)


def _is_failure_text(text):
    if text is None:
        return True
    s = str(text).strip()
    if not s:
        return True
    low = s.lower()
    return any(marker in low for marker in _FAILURE_MARKERS)


def _try_hugchat(prompt):
    """Return (text, ok). ok=False on any failure."""
    try:
        print("[BRAIN] provider=hugchat request_started")
        text = ask_hugchat(prompt)
        if _is_failure_text(text):
            print("[BRAIN] provider=hugchat failed reason=empty_response")
            return "", False
        print("[BRAIN] provider=hugchat success")
        return str(text).strip(), True
    except FileNotFoundError:
        print("[BRAIN] provider=hugchat failed reason=missing_cookies")
        return "", False
    except Exception as e:
        # Log exception type only; never the message (may include URLs/tokens).
        print(f"[BRAIN] provider=hugchat failed reason={type(e).__name__}")
        return "", False


def _try_lightning(prompt):
    """Return (text, ok). ok=False on any failure."""
    try:
        from engine.lightning_gateway import ask_lightning
        print("[BRAIN] provider=lightning fallback_started")
        text = ask_lightning(prompt)
        if _is_failure_text(text):
            print("[BRAIN] provider=lightning failed reason=empty_or_unconfigured")
            return "", False
        print("[BRAIN] provider=lightning success")
        return str(text).strip(), True
    except Exception as e:
        print(f"[BRAIN] provider=lightning failed reason={type(e).__name__}")
        return "", False


def _try_gemini(prompt):
    """Return (text, ok). ok=False on any Gemini failure."""
    try:
        from engine.gemini_brain import ask_gemini
        context = ""
        try:
            from engine.memory_store import get_brain_memory_context
            parts = []
            memory_context = get_brain_memory_context()
            if memory_context:
                parts.append(memory_context)
                try:
                    import eel
                    eel.setContextIndicator(True)
                except Exception:
                    pass
            try:
                # Bounded autonomous context: rolling summary + last 10 exchanges.
                from engine.context_budget_manager import build_context as build_budget_context
                budget_context = build_budget_context(prompt, include_long_term=False)
                if budget_context:
                    parts.append(budget_context)
            except Exception:
                try:
                    from engine.conversation_context import build_compact_context
                    recent = build_compact_context(limit=int(os.getenv("BRAIN_HISTORY_TURNS", "10")))
                    if recent:
                        parts.append("Recent turns:\n" + recent)
                except Exception:
                    pass
            try:
                from engine.intent_context_builder import build_intent_context
                intent_context = build_intent_context(prompt, source="brain").get("memory_context", {})
                context_lines = []
                for key in ("session", "semantic", "reflection"):
                    value = intent_context.get(key)
                    if value:
                        context_lines.append(f"{key}:\n{value}")
                episodes = intent_context.get("episodic") or []
                if episodes:
                    context_lines.append("episodic:\n" + "\n".join(str(item)[:180] for item in episodes[:3]))
                if context_lines:
                    parts.append("Nexi memory context:\n" + "\n".join(context_lines))
            except Exception:
                pass
            context = "\n\n".join(parts)
        except Exception:
            context = ""
        text = ask_gemini(prompt, context=context)
        if _is_failure_text(text):
            print("[BRAIN] provider=gemini failed reason=empty_response")
            return "", False
        return str(text).strip(), True
    except Exception as e:
        print(f"[BRAIN] provider=gemini failed reason={type(e).__name__}")
        return "", False


_PROVIDER_FUNCS = {
    "gemini": _try_gemini,
    "hugchat": _try_hugchat,
    "lightning": _try_lightning,
}

_LEGACY_PROVIDERS = {"hugchat", "lightning"}


def _env_flag(name: str, default: str = "false") -> bool:
    return (os.getenv(name, default) or "").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_provider_chain():
    """Return provider names in try order.

    Gemini is the default. Legacy providers are skipped unless
    NEXI_ENABLE_LEGACY_BRAIN_PROVIDERS is explicitly enabled.
    """
    legacy_enabled = _env_flag("NEXI_ENABLE_LEGACY_BRAIN_PROVIDERS")
    primary = (os.getenv("NEXI_BRAIN_PRIMARY", "") or "").lower().strip()
    fallback = (os.getenv("NEXI_BRAIN_FALLBACK", "") or "").lower().strip()
    legacy_provider = (os.getenv("NEXI_BRAIN_PROVIDER", "") or "").lower().strip()

    if not primary and legacy_provider in _PROVIDER_FUNCS:
        primary = legacy_provider
    if primary not in _PROVIDER_FUNCS or (primary in _LEGACY_PROVIDERS and not legacy_enabled):
        primary = "gemini"

    chain = [primary]
    if fallback and fallback != "none" and fallback in _PROVIDER_FUNCS:
        if fallback not in _LEGACY_PROVIDERS or legacy_enabled:
            if fallback != primary:
                chain.append(fallback)
    return chain


def ask_brain(prompt: str) -> str:
    """Provider chain: Gemini Flash default -> explicit opt-in fallbacks.

    Pure function: does NOT call speak(). Caller is responsible for speaking.
    """
    if (os.getenv("BRAIN_ENABLED", "true") or "").strip().lower() in {"0", "false", "no", "off"}:
        print("[BRAIN] disabled")
        return _ALL_PROVIDERS_FAILED
    if not prompt or not str(prompt).strip():
        return _ALL_PROVIDERS_FAILED

    for provider in _resolve_provider_chain():
        text, ok = _PROVIDER_FUNCS[provider](prompt)
        if ok:
            return text

    print("[BRAIN] brain_unavailable")
    return _ALL_PROVIDERS_FAILED


def chatBot(query):
    """Public entry point. Runs the provider chain and speaks the answer once."""
    global _brain_fail_until
    try:
        fail_fast_seconds = float(os.getenv("BRAIN_FAIL_FAST_SECONDS", "60"))
    except (TypeError, ValueError):
        fail_fast_seconds = 60.0
    now = time.time()
    if _brain_fail_until and now < _brain_fail_until:
        print("[BRAIN] fail_fast_active")
        speak(_ALL_PROVIDERS_FAILED)
        return _ALL_PROVIDERS_FAILED
    response_text = ask_brain(query)
    try:
        from engine.assistant_response import guard_unverified_action_message
        response_text = guard_unverified_action_message(response_text)
    except Exception:
        pass
    if _is_failure_text(response_text):
        _brain_fail_until = time.time() + max(0.0, fail_fast_seconds)
    speak(response_text)
    return response_text
