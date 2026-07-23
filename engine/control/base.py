class ControlResult:
    def __init__(self, ok=True, message="", data=None, error=None):
        self.ok = ok
        self.message = message
        self.data = data if data is not None else {}
        self.error = error

    @classmethod
    def success(cls, message="", data=None):
        return cls(ok=True, message=message, data=data or {})

    @classmethod
    def failure(cls, message="Action failed.", code="", error_message=""):
        return cls(ok=False, message=message, error={"code": code, "message": error_message})

    def to_dict(self):
        return {
            "ok": self.ok,
            "message": self.message,
            "data": self.data,
            "error": self.error
        }


class ControlFunction:
    def __init__(self, name, intent, description, risk_level="MEDIUM",
                 privacy_sensitivity="LOW", requires_confirmation=False,
                 required_entities=None, optional_entities=None, handler=None):
        self.name = name
        self.intent = intent
        self.description = description
        self.risk_level = risk_level
        self.privacy_sensitivity = privacy_sensitivity
        self.requires_confirmation = requires_confirmation
        self.required_entities = required_entities or []
        self.optional_entities = optional_entities or []
        self.handler = handler

    def __call__(self, **kwargs):
        if self.handler:
            return self.handler(**kwargs)
        return ControlResult.failure(code="NO_HANDLER", error_message="No handler registered")

    def to_contract(self):
        return {
            "name": self.name,
            "intent": self.intent,
            "description": self.description,
            "risk_level": self.risk_level,
            "privacy_sensitivity": self.privacy_sensitivity,
            "requires_confirmation": self.requires_confirmation,
            "required_entities": self.required_entities,
            "optional_entities": self.optional_entities
        }
