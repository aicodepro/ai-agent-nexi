from src.orin.diagnostics.runtime_doctor import RuntimeDoctor, _check, run_all_checks


class HotwordDoctor:
    @classmethod
    def check(cls):
        results = run_all_checks()
        for r in results:
            if r["name"] == "Hotword/Speech":
                return r
        return {"name": "Hotword/Speech", "ok": False, "problem": "Hotword check not available"}

    @classmethod
    def is_speech_recognition_available(cls):
        try:
            import speech_recognition
            return True
        except ImportError:
            return False
