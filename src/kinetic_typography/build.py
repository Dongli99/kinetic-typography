"""Build a scene from groups of words and a choice of effect for each slot."""

from .effects import SLOTS, resolve
from .scene import Camera, Group, GroupSpec, Look, Node, Scene

RETIRE_BEFORE_NEXT = 0.1  # seconds a group starts leaving before the group that replaces it
RETIRE_BEFORE_SECTION = 0.45


class Context:
    """What effects may know beyond their own element."""

    def __init__(self, look: Look, duration: float, groups: list[Group]):
        self.size = (look.width, look.height)
        self.duration = duration
        self.groups = groups

    def retire_time(self, g: Group, after: int, hold: float | None = None) -> float | None:
        """When a group starts leaving: `after` groups later, at the next section, or `hold`
        seconds after its last word, whichever is first. None if it stays to the end."""
        i = self.groups.index(g)
        times = []
        if after >= 1 and i + after < len(self.groups):
            times.append(self.groups[i + after].start - RETIRE_BEFORE_NEXT)
        later = next((h for h in self.groups[i + 1 :] if h.spec.section), None)
        if later is not None:
            times.append(later.start - RETIRE_BEFORE_SECTION)
        if hold is not None:
            times.append(g.end + hold)
        return min(times) if times else None


def build(specs: list[GroupSpec], slots: dict, look: Look, duration: float) -> Scene:
    """Lay out every group, then let each slot's effect write its keys.

    slots maps each of place, arrive, retire and camera to an effect name or {"type": name, ...}.
    """
    missing = set(SLOTS) - set(slots)
    if missing:
        raise ValueError(f"No effect chosen for {', '.join(sorted(missing))}")
    if not specs or not all(spec.words for spec in specs):
        raise ValueError("Every group needs at least one word")
    chosen = {slot: resolve(slot, slots[slot]) for slot in SLOTS}

    world = Node()
    groups = [Group(world, spec, look) for spec in specs]
    ctx = Context(look, duration, groups)

    place, params = chosen["place"]
    place(ctx, groups, **params)
    for index, g in enumerate(groups):
        arrive, params = resolve("arrive", g.spec.arrive, f"groups[{index}].arrive") if g.spec.arrive else chosen["arrive"]
        for word in g.words:
            arrive(ctx, word, **params)
        retire, params = resolve("retire", g.spec.retire, f"groups[{index}].retire") if g.spec.retire else chosen["retire"]
        retire(ctx, g, **params)
    camera = Camera()
    move, params = chosen["camera"]
    move(ctx, camera, groups, **params)
    return Scene(world, camera, groups, look, duration)
