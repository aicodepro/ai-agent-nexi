import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.lightning_gateway import ask_lightning

answer = ask_lightning("what is 2+2")
print(f"answer: {answer}")
