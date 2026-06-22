"""Simple voice games."""

import random

_CHOICES = ["rock", "paper", "scissors"]
_BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}


def start_rps() -> dict:
    from workflow.manager import start_workflow
    start_workflow("rps")
    return {"handled": True, "message": "Let's play! Rock, paper, or scissors?"}


def play_rps(user_choice: str) -> str:
    choice = ""
    low = user_choice.lower()
    for c in _CHOICES:
        if c in low:
            choice = c
            break
    if not choice:
        return "Pick rock, paper, or scissors."

    mine = random.choice(_CHOICES)
    if mine == choice:
        outcome = "It's a tie!"
    elif _BEATS[choice] == mine:
        outcome = "You win!"
    else:
        outcome = "I win!"
    return f"You chose {choice}, I chose {mine}. {outcome}"
