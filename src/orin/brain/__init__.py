from src.orin.brain.intent_brain import IntentBrain
from src.orin.brain.bilingual_normalizer import BilingualNormalizer
from src.orin.brain.speech_recovery import SpeechRecovery
from src.orin.brain.action_planner import ActionPlanner
from src.orin.brain.action_verifier import ActionVerifier
from src.orin.brain.task_state import AutonomyTask, AutonomyStep, create_task, create_step
from src.orin.brain.self_reflection import summarize_goal, should_ask_followup
from src.orin.brain.recovery_planner import create_recovery_plan, classify_failure, suggest_next_action
from src.orin.brain.autonomy_loop import AutonomyLoop

brain = IntentBrain()

def process_query(raw_query):
    return brain.process(raw_query)
