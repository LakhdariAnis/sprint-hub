"""Step state machine (docs/HUB-DESIGN.md section 4). Pure: no files, no clock."""

from enum import StrEnum

from hubd.model import State, Step


class Event(StrEnum):
    start = "start"
    run_ended = "run_ended"
    approve = "approve"
    request_changes = "request_changes"


class Actor(StrEnum):
    daemon = "daemon"
    me = "me"


# (state, event) -> (new state, who may cause it). Any pair not listed is not a move.
TABLE: dict[tuple[State, Event], tuple[State, frozenset[Actor]]] = {
    (State.todo, Event.start): (State.doing, frozenset({Actor.daemon})),
    (State.changes, Event.start): (State.doing, frozenset({Actor.daemon})),
    (State.doing, Event.run_ended): (State.done, frozenset({Actor.daemon})),
    (State.done, Event.approve): (State.approved, frozenset({Actor.me})),
    (State.done, Event.request_changes): (State.changes, frozenset({Actor.me})),
}


class InvalidTransition(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def transition(step: Step, event: Event, actor: Actor) -> Step:
    """Return a copy of `step` in its new state; `step` itself is not changed."""
    move = TABLE.get((step.state, event))
    if move is None:
        raise InvalidTransition(f"step {step.step}: no '{event}' from '{step.state}'")
    new_state, actors = move
    if actor not in actors:
        allowed = ", ".join(sorted(actors))
        raise InvalidTransition(
            f"step {step.step}: '{actor}' cannot '{event}' from '{step.state}' (only {allowed})"
        )
    return step.model_copy(update={"state": new_state})
