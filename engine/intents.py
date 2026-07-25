from difflib import SequenceMatcher
import re


def _contains_phrase(text, phrase):
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None

class Intent:
    __slots__ = ('name', 'patterns', 'handler', 'module', 'priority', 'negative_patterns')

    def __init__(self, name, patterns, handler=None, module=None, priority=0, negative_patterns=None):
        self.name = name
        self.patterns = [p.lower().strip() for p in patterns]
        self.handler = handler
        self.module = module
        self.priority = priority
        self.negative_patterns = [p.lower().strip() for p in negative_patterns] if negative_patterns else []

    def score(self, query):
        q = query.lower().strip()
        if not q:
            return 0.0
        for neg in self.negative_patterns:
            if _contains_phrase(q, neg):
                return 0.0
        q_words = set(q.split())
        best = 0.0
        for pattern in self.patterns:
            if _contains_phrase(q, pattern):
                return 1.0
            p_words = set(pattern.split())
            if p_words:
                overlap = len(q_words & p_words) / len(p_words)
                best = max(best, overlap)
            ratio = SequenceMatcher(None, q, pattern, autojunk=False).ratio()
            best = max(best, ratio * 0.65)
        return best

    def specificity(self, query):
        q = query.lower().strip()
        return max((len(pattern) for pattern in self.patterns if _contains_phrase(q, pattern)), default=0)

REGISTRY = [
    Intent("open_app", ["open", "launch", "start", "run app", "open application"]),
    Intent("youtube", ["on youtube", "play on youtube", "play youtube", "youtube video", "search youtube", "youtube search"], negative_patterns=["essay", "story", "article", "paragraph", "content", "write"]),
    Intent("create_folder", ["create folder", "make folder", "new folder", "create a folder", "folder named"], negative_patterns=["essay", "story", "article", "paragraph", "content", "write"]),
    Intent("create_file", ["create file", "make file", "new file in", "create a new file"], negative_patterns=["essay", "story", "article", "paragraph", "content", "write"]),
    Intent("read_selected", ["read selected", "read selection", "read my clipboard", "read selected data", "read what i selected"]),
    Intent("image_to_text", ["image to text", "extract text", "ocr", "read image text", "text from image"]),
    Intent("message", ["send message", "message to", "whatsapp message", "text message"]),
    Intent("phone_call", ["phone call", "call to", "make a call", "call someone"]),
    Intent("video_call", ["video call", "video chat", "face call", "video call to"]),
    Intent("weather", ["weather", "temperature", "todays weather", "whats the weather", "weather today", "how is the weather"]),
    Intent("music", ["play music", "play song", "play a song", "start music", "play some music", "play a track"]),
    Intent("auto_type", ["automatic typing", "auto type", "activate typing", "start typing", "enable typing"]),
    Intent("joke", ["tell joke", "tell a joke", "make me laugh", "joke", "crack a joke", "say a joke"]),
    Intent("time", ["what is the time", "what time", "current time", "time now", "tell me the time", "time please", "whats the time"]),
    Intent("eye_mouse", ["eye mouse", "eye control", "eye tracking", "eye mouse controller", "eye mouse system", "look control", "gaze control", "blink click"]),
    Intent("camera_hand", ["hand mode", "hand gesture mode", "enable hand mode", "switch to hand", "start hand tracking", "enable hand tracking"]),
    Intent("camera_eye", ["eye mode", "eye control mode", "enable eye mode", "switch to eye", "start eye tracking", "enable eye tracking", "look mode"]),
    Intent("camera_status", ["camera status", "camera control status", "is camera running", "camera info", "camera control info"]),
    Intent("camera_pause", ["pause camera control", "pause gesture", "pause hand", "freeze camera", "freeze control", "hold gesture"]),
    Intent("camera_resume", ["resume camera control", "resume gesture", "resume hand", "unfreeze camera", "unfreeze control", "continue gesture", "continue tracking"]),
    Intent("volume_up", ["volume up", "increase volume", "turn up volume", "louder", "raise volume", "increase the volume"]),
    Intent("volume_down", ["volume down", "decrease volume", "lower volume", "quieter", "turn down volume", "decrease the volume"]),
    Intent("game", ["play game", "start game", "launch game", "open game", "play a game"]),
    Intent("chess", ["play chess", "open chess", "start chess", "chess game", "chess board"]),
    Intent("hand_gesture", ["hand gesture", "gesture system", "enable gesture", "hand control", "gesture scrolling", "hand scrolling", "hand gesture system", "enable hand gesture", "gesture control"]),
    Intent("face_recognition", ["face recognition", "face detect", "who am i", "recognize face", "face recognition system", "enable face recognition", "start face recognition", "who is this", "identify face", "face detection"]),
    Intent("face_register", ["register face", "train face", "new face", "add face", "learn my face", "teach face", "register new face", "train my face", "save face"]),
    Intent("camera_stop", ["stop camera control", "disable camera control", "stop gesture control", "stop eye mouse", "disable gesture", "stop hand gesture"]),
    Intent("camera_hybrid", ["hybrid control", "hybrid camera", "hybrid mode", "camera hybrid", "eye and hand", "hand and eye"]),
    Intent("alarm", ["set alarm", "create alarm", "alarm for", "new alarm", "wake me up"]),
    Intent("schedule", ["remind me", "tell me to", "set reminder", "schedule", "reminder for", "remember to"]),
    Intent("pause_media", ["pause", "pause video", "stop video", "pause music", "stop playing"]),
    Intent("resume_media", ["play video", "resume video", "resume playing", "play again", "continue playing"]),
    Intent("mute_media", ["mute", "mute video", "mute sound", "turn off sound", "silence"]),
    Intent("internet_speed", ["internet speed", "speed test", "check speed", "network speed", "check internet", "test internet"]),
    Intent("object_detection", ["object detection", "detect objects", "start detection", "enable detection", "object detect", "camera detection"]),
    Intent("generate_image", ["generate image", "create image", "make image", "draw picture", "generate picture", "paint image", "create a picture"]),
    Intent("browser_task_manager", ["chrome task manager", "task manager chrome", "browser task manager"]),
    Intent("minimize_window", ["minimize window", "minimize", "hide window", "minimize current", "minimize this"]),
    Intent("new_tab", ["open new tab", "new tab", "create tab", "open a new tab"]),
    Intent("close_tab", ["close tab", "close current tab", "close this tab", "close the tab"]),
    Intent("browser_menu", ["browser menu", "open menu", "chrome menu", "show menu", "settings menu"]),
    Intent("zoom_in", ["zoom in", "zoom-in", "magnify", "increase zoom", "make bigger"]),
    Intent("zoom_out", ["zoom out", "zoom-out", "decrease zoom", "reduce zoom", "make smaller"]),
    Intent("refresh", ["refresh", "reload", "refresh page", "reload page", "refresh browser"]),
    Intent("next_tab", ["next tab", "switch tab", "next tab please", "go to next tab", "move to next tab"]),
    Intent("prev_tab", ["previous tab", "back tab", "go back tab", "switch to previous", "previous tab please"]),
    Intent("history", ["open history", "show history", "browser history", "view history", "show my history"]),
    Intent("bookmarks", ["open bookmarks", "show bookmarks", "favorites", "browser bookmarks", "view bookmarks"]),
    Intent("go_back", ["go back", "navigate back", "back page", "previous page", "go to previous page"]),
    Intent("go_forward", ["go forward", "navigate forward", "forward page", "next page", "go to next page"]),
    Intent("dev_tools", ["open dev tools", "developer tools", "inspect element", "open inspector", "browser tools"]),
    Intent("fullscreen", ["full screen", "fullscreen", "toggle fullscreen", "go fullscreen", "maximize screen"]),
    Intent("private_window", ["private window", "incognito", "private browsing", "open incognito", "private mode"]),
    Intent("search_google", ["search google for", "google search", "search the web", "look up", "search for"]),
    Intent("close_app", ["close", "exit", "quit", "close application", "kill", "stop app"]),

    Intent("control_open_chrome", ["open chrome", "launch chrome", "start chrome", "open browser", "launch browser"]),
    Intent("control_open_url", ["go to", "open url", "navigate to", "take me to"]),
    Intent("control_open_youtube", ["open youtube", "go to youtube", "launch youtube", "start youtube"]),
    Intent("control_search_youtube", ["search youtube for", "search you tube for", "youtube search", "on youtube"], negative_patterns=["essay", "story", "article", "paragraph", "content", "write"]),
    Intent("control_search_google", ["search google for", "google search", "search the web for", "google "]),
    Intent("control_new_tab", ["open new tab", "new tab", "create new tab"]),
    Intent("control_close_tab", ["close tab", "close current tab", "close this tab"]),
    Intent("control_tab_info", ["what is this tab", "current tab info", "what tab am i on", "get tab title"]),
    Intent("control_show_apps", ["show running apps", "list running apps", "running applications", "what apps are open"]),
    Intent("control_focus_app", ["focus", "switch to", "bring to front", "focus window"]),
    Intent("control_active_window", ["what window is active", "active window", "current window", "what is on my screen", "show current window"]),
    Intent("control_create_folder", ["create folder", "make folder", "new folder", "create a folder", "folder on desktop"]),
    Intent("control_create_file", ["create file", "make file", "new file", "create text file"]),
    Intent("control_open_folder", ["open my downloads", "open my documents", "open my desktop", "open downloads folder"]),
    Intent("control_search_files", ["search files", "find file", "search for file", "look for file"]),
    Intent("control_emergency_stop", ["stop everything", "emergency stop", "stop all actions", "abort", "halt", "freeze", "cancel everything"]),
    Intent("stop_speaking", ["stop speaking", "stop talking", "enough", "cancel speech", "bas", "band karo", "chup", "chup ho jao", "ruk jao"]),
    Intent("control_status", ["what can you do", "your capabilities", "control status", "what can you control", "what commands"]),
    Intent("control_emergency_stop_hi", ["sab band karo", "sab rok do", "sab freeze karo"]),
    Intent("diagnose_jarvi", ["diagnose jarvi", "check yourself", "jarvi diagnose", "diagnose karo", "jarvi check karo", "apne aap ko check karo"]),
    Intent("check_hotword", ["check hotword", "hotword check karo", "hotword status"]),
    Intent("check_bridge", ["check bridge", "bridge check karo", "bridge status"]),
    Intent("check_playwright", ["check playwright", "playwright check karo", "playwright status"]),
    Intent("control_open_chrome_hi", ["chrome kholo", "browser kholo", "krom kholo", "browzer kholo"]),
    Intent("control_open_youtube_hi", ["youtube kholo", "yutub kholo", "you tube kholo"]),
    Intent("control_search_google_hi", ["google pe search karo", "google pe dhoondo", "google pe khojo", "google search karo", "google pe dhundho"]),
    Intent("control_search_youtube_hi", ["youtube pe search karo", "youtube pe dhoondo", "youtube pe khojo", "youtube search karo", "youtube pe dhundho"]),
    Intent("control_show_apps_hi", ["apps dikhao", "running apps dikhao", "chalti apps dikhao"]),
    Intent("control_active_window_hi", ["active window dikhao", "window dikhao", "kaunsi window chal rahi hai"]),
    Intent("control_focus_app_hi", ["focus karo", "window lao", "front me lao"]),
    Intent("control_create_folder_hi", ["folder banao", "naya folder banao", "folder create karo"]),
    Intent("control_open_folder_hi", ["downloads kholo", "documents kholo", "desktop kholo", "folder kholo"]),
    Intent("control_status_hi", ["kya kar sakte ho", "tumhari capabilities kya hain", "status do"]),
]

def match_intent(query, threshold=0.35):
    q = query.lower().strip()
    if not q:
        return None, 0.0
    best, best_score, best_specificity = None, 0.0, 0
    for intent in REGISTRY:
        s = intent.score(q)
        specificity = intent.specificity(q)
        if s > best_score or (s == best_score and specificity > best_specificity):
            best_score, best, best_specificity = s, intent, specificity
    return (best, best_score) if best_score >= threshold else (None, 0.0)
