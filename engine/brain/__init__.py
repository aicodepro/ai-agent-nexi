from engine.brain.intent_brain import IntentBrain
from engine.brain.bilingual_normalizer import BilingualNormalizer
from engine.brain.speech_recovery import SpeechRecovery
from engine.brain.action_planner import ActionPlanner
from engine.brain.action_verifier import ActionVerifier
from engine.brain.task_state import AutonomyTask, AutonomyStep, create_task, create_step
from engine.brain.self_reflection import summarize_goal, should_ask_followup
from engine.brain.recovery_planner import create_recovery_plan, classify_failure, suggest_next_action
from engine.brain.autonomy_loop import AutonomyLoop

brain = IntentBrain()

def process_query(raw_query):
    return brain.process(raw_query)
