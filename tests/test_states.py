from itertools import product

import pytest

from hubd.model import State, Step
from hubd.states import Actor, Event, InvalidTransition, transition

# Written out by hand from the diagram, not read from TABLE, so a wrong TABLE fails here.
ALLOWED = {
    (State.todo, Event.start, Actor.daemon): State.doing,
    (State.changes, Event.start, Actor.daemon): State.doing,
    (State.doing, Event.run_ended, Actor.daemon): State.done,
    (State.done, Event.approve, Actor.me): State.approved,
    (State.done, Event.request_changes, Actor.me): State.changes,
}
# Pairs that are moves, but only for the other actor.
WRONG_ACTOR = {(s, e) for s, e, _ in ALLOWED}

ALL = list(product(State, Event, Actor))


@pytest.mark.parametrize(("state", "event", "actor"), ALL)
def test_every_combination(state: State, event: Event, actor: Actor) -> None:
    step = Step(step="106", title="x", state=state)
    if (state, event, actor) in ALLOWED:
        moved = transition(step, event, actor)
        assert moved.state == ALLOWED[(state, event, actor)]
        assert moved.model_dump(exclude={"state"}) == step.model_dump(exclude={"state"})
    else:
        with pytest.raises(InvalidTransition) as err:
            transition(step, event, actor)
        if (state, event) in WRONG_ACTOR:
            assert f"'{actor}' cannot '{event}'" in err.value.reason
        else:
            assert f"no '{event}' from '{state}'" in err.value.reason
    assert step.state == state  # input never changed
