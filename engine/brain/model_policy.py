TASK_TYPES = [
    "fast_intent",
    "deep_planning",
    "coding",
    "review",
    "long_context",
    "experimental",
]

ROUTING_POLICY = {
    "fast_intent": {
        "preferred": "qwen3",
        "fallback": "deepseek_v3_2",
        "description": "Simple command handling, fast intent mapping, Hindi/Hinglish variants",
        "timeout_seconds": 15,
        "max_tokens": 1024,
    },
    "deep_planning": {
        "preferred": "deepseek_v4_pro",
        "fallback": "deepseek_r1",
        "description": "Deep planning, architecture, high-level reasoning",
        "timeout_seconds": 120,
        "max_tokens": 4096,
    },
    "coding": {
        "preferred": "glm_5_1",
        "fallback": "kimi_2_6",
        "description": "Main coding and build implementation",
        "timeout_seconds": 60,
        "max_tokens": 4096,
    },
    "review": {
        "preferred": "minimax_2_7",
        "fallback": "deepseek_r1",
        "description": "Debugging, review, QA, security review",
        "timeout_seconds": 45,
        "max_tokens": 2048,
    },
    "long_context": {
        "preferred": "kimi_2_6",
        "fallback": "glm_5_1",
        "description": "Long-context review, repo or document analysis",
        "timeout_seconds": 90,
        "max_tokens": 8192,
    },
    "experimental": {
        "preferred": "mimo",
        "fallback": "qwen3",
        "description": "Experimental models, only when explicitly enabled",
        "timeout_seconds": 30,
        "max_tokens": 2048,
    },
}

ROUTING_POLICY_BY_MODEL = {}
for task_type, policy in ROUTING_POLICY.items():
    for role in ("preferred", "fallback"):
        model = policy[role]
        if model not in ROUTING_POLICY_BY_MODEL:
            ROUTING_POLICY_BY_MODEL[model] = []
        ROUTING_POLICY_BY_MODEL[model].append((task_type, role))


def get_policy(task_type):
    return ROUTING_POLICY.get(task_type)


def is_valid_task_type(task_type):
    return task_type in TASK_TYPES


def get_default_policy():
    return ROUTING_POLICY["fast_intent"]


def list_task_types():
    return list(TASK_TYPES)


def list_model_names():
    return sorted(ROUTING_POLICY_BY_MODEL.keys())
