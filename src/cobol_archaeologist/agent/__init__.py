"""Agent loop and stub tool layer (Track C, T3.5)."""

from cobol_archaeologist.agent.loop import InvestigationLoop
from cobol_archaeologist.agent.policy import HUNT_REGISTRY, HuntOutcome, get_hunt
from cobol_archaeologist.agent.stub_tools import StubToolLayer
from cobol_archaeologist.agent.trajectory import BudgetSpec, ToolCall, Trajectory

__all__ = [
    "HUNT_REGISTRY",
    "BudgetSpec",
    "HuntOutcome",
    "InvestigationLoop",
    "StubToolLayer",
    "ToolCall",
    "Trajectory",
    "get_hunt",
]
