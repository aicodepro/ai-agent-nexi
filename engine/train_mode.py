from __future__ import annotations

import re

from engine.training_rules import format_rule_summary, parse_training_instruction, save_training_rule


_training_mode = False


def is_plausible_training_instruction(text: str) -> bool:
    q = (text or "").strip().lower().rstrip(".?!")
    if not q:
        return False
    if q in {"open", "open app", "search", "cancel", "stop", "sleep", "wake", "zzzz"}:
        return False
    if q.startswith(("open ", "search ", "create ", "make ", "find ", "remember ", "show ", "what ", "who ", "why ", "how ")):
        return False
    return q.startswith((
        "when ", "if ", "for ", "always ", "never ", "use ", "avoid ", "prefer ", "i prefer ",
        "next time ", "good example", "bad example", "ideal example", "save this response style",
        "teach ", "learn this", "rule:", "example:", "not like this",
    )) or any(phrase in q for phrase in ("ideal example", "bad example", "next time", "you misunderstood", "not like this"))


def start_training_mode() -> str:
    global _training_mode
    _training_mode = True
    return "Training mode online. What should I learn?"


def start_need_training_mode(need: str) -> str:
    global _training_mode
    _training_mode = True
    from engine.need_training_manager import start_need_training
    result = start_need_training(need)
    return result.get("message", f"{need} training active.")


def stop_training_mode() -> str:
    global _training_mode
    _training_mode = False
    try:
        from engine.need_training_manager import get_active_need, stop_need_training
        if get_active_need():
            return stop_need_training().get("message", "Training saved.")
    except Exception:
        pass
    return "Training mode stopped."


def is_training_mode() -> bool:
    return bool(_training_mode)


def _learned_message(rule: dict) -> str:
    trigger = str(rule.get("trigger") or "that").strip()
    action = str(rule.get("action") or "the saved action").strip()
    pretty_trigger = trigger[:1].upper() + trigger[1:]
    return f"Learned. Next time you say {pretty_trigger}, I'll {action}."


def _need_from_suffix(text: str, prefix: str) -> str:
    value = str(text or "").strip()
    if value.lower().startswith(prefix):
        return value[len(prefix):].strip(" .?!")
    return ""


def _format_profile_message(result: dict) -> str:
    need = result.get("need") or "general"
    return f"Cognitive training active for {need}. I can learn your patterns."


def _handle_need_or_ultra_command(text: str, q: str) -> str | None:
    global _training_mode
    if q.startswith("train nexi deeply for "):
        _training_mode = True
        need = _need_from_suffix(text, "train nexi deeply for ")
        from engine.deep_training_engine import start_ultra_training
        from engine.need_training_manager import start_need_training
        start_need_training(need)
        result = start_ultra_training(need)
        return result.get("message", f"Ultra training active for {need}.")
    if q.startswith("train nexi for "):
        _training_mode = True
        need = _need_from_suffix(text, "train nexi for ")
        from engine.need_training_manager import start_need_training
        return _format_profile_message(start_need_training(need))
    if q.startswith("start ultra training for "):
        _training_mode = True
        need = _need_from_suffix(text, "start ultra training for ")
        from engine.deep_training_engine import start_ultra_training
        return start_ultra_training(need).get("message", f"Ultra training active for {need}.")
    if q in {"show training profiles", "show need profiles", "show nexi profiles"}:
        from engine.need_training_manager import format_need_profiles
        return format_need_profiles()
    if q.startswith("forget training profile about "):
        from engine.need_training_manager import disable_need_profile
        result = disable_need_profile(text[30:].strip())
        return "Training profile disabled." if int(result.get("disabled", 0)) else "I did not find a matching training profile."
    if q.startswith("create training dataset for "):
        need = _need_from_suffix(text, "create training dataset for ")
        from engine.training_dataset import build_dataset_from_profile
        created = build_dataset_from_profile(need)
        return f"Training dataset created for {need}. Items: {len(created)}."
    if q.startswith("simulate training for "):
        need = _need_from_suffix(text, "simulate training for ")
        from engine.training_simulator import simulate_and_store
        stored = simulate_and_store(need, 10)
        return f"Simulated training scenarios saved for {need}. Items: {len(stored)}."
    if q.startswith("run training evaluation"):
        match = re.search(r"\bfor\s+(.+)$", text, flags=re.I)
        need = match.group(1).strip(" .?!") if match else None
        from engine.training_evaluator import run_training_evaluation
        result = run_training_evaluation(need)
        return f"Training evaluation complete for {result.get('need')}. Score: {result.get('overall_score')}. Items: {result.get('count')}."
    if q.startswith("show training score"):
        match = re.search(r"\bfor\s+(.+)$", text, flags=re.I)
        need = match.group(1).strip(" .?!") if match else None
        from engine.training_evaluator import get_training_score
        result = get_training_score(need)
        return f"Training score for {result.get('need')}: {result.get('overall_score')} across {result.get('evaluation_count')} evaluations."
    if q.startswith("show weak areas"):
        match = re.search(r"\bfor\s+(.+)$", text, flags=re.I)
        need = match.group(1).strip(" .?!") if match else None
        from engine.training_evaluator import get_weak_areas
        weak = get_weak_areas(need)
        if not weak:
            return "No weak areas recorded yet. Run training evaluation first."
        return "Weak areas: " + "; ".join(f"{item.get('area')} ({item.get('count')})" for item in weak[:5])
    if q.startswith("show training curriculum for "):
        need = _need_from_suffix(text, "show training curriculum for ")
        from engine.training_curriculum import recommend_next_training_step
        result = recommend_next_training_step(need)
        return f"Next training step for {need}: {result.get('next_step')}."
    return None


def handle_training_command(text: str) -> str | None:
    q = (text or "").strip().lower().rstrip(".?!")
    routed = _handle_need_or_ultra_command(text, q)
    if routed:
        return routed
    if q in {"train nexi", "start training", "start training mode", "training mode"}:
        return start_training_mode()
    if q in {"stop training", "stop training mode", "end training"}:
        return stop_training_mode()
    if q in {"show training rules"}:
        return format_rule_summary()
    parsed = parse_training_instruction(text)
    if parsed.get("parsed"):
        result = save_training_rule(parsed)
        if result.get("stored"):
            return _learned_message(result["rule"])
    try:
        from engine.need_training_manager import capture_training_instruction, get_active_need
        active_need = get_active_need()
        if active_need and is_training_mode() and is_plausible_training_instruction(q):
            captured = capture_training_instruction(text, active_need)
            if captured.get("captured"):
                return f"Learned for {captured.get('need')}. I can apply this profile next time."
            return f"I could not save that training item: {captured.get('reason', 'not safe to store')}."
    except Exception:
        pass
    if is_training_mode() and q and q in {"help training", "training help", "how do i train you"}:
        return "Tell me the rule as: when I say X, do Y."
    return None
