from engine.diagnostic_doctors.runtime_doctor import RuntimeDoctor


class BridgeDoctor:
    @classmethod
    def check(cls):
        return RuntimeDoctor.check_bridge()

    @classmethod
    def is_control_available(cls):
        try:
            from engine.control import execute_control_action
            return True
        except ImportError:
            return False
