from engine.diagnostic_doctors.runtime_doctor import RuntimeDoctor


class HotwordDoctor:
    @classmethod
    def check(cls):
        return RuntimeDoctor.check_hotword()

    @classmethod
    def is_speech_recognition_available(cls):
        try:
            import speech_recognition
            return True
        except ImportError:
            return False
