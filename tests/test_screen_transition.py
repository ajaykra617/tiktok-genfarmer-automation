from genfarmer_automation.screen_state import RawScreenFrame, sampling_grid
from genfarmer_automation.screen_transition import TransitionDecision, assess_visual_transition


def frame(width: int, height: int, rgb: tuple[int, int, int]) -> RawScreenFrame:
    pixel = bytes([rgb[0], rgb[1], rgb[2], 255])
    return RawScreenFrame(width, height, 1, pixel * (width * height))


def test_proves_large_persistent_change():
    before = [frame(40, 60, (20, 30, 40)), frame(40, 60, (21, 30, 40))]
    after = [frame(40, 60, (120, 130, 140)), frame(40, 60, (122, 130, 141))]
    report = assess_visual_transition(before, after, points=sampling_grid(40, 60, columns=8, rows=10))
    assert report.decision is TransitionDecision.PROVEN_CHANGED
    assert report.changed_ratio_of_stable == 1.0
    assert report.changed_cells >= 4


def test_rejects_no_change():
    before = [frame(40, 60, (20, 30, 40)), frame(40, 60, (21, 30, 40))]
    after = [frame(40, 60, (22, 30, 40)), frame(40, 60, (23, 30, 40))]
    report = assess_visual_transition(before, after, points=sampling_grid(40, 60, columns=8, rows=10))
    assert report.decision is TransitionDecision.INCONCLUSIVE_CHANGE
    assert report.changed_points == 0


def test_rejects_unstable_baseline():
    before = [frame(40, 60, (0, 0, 0)), frame(40, 60, (100, 100, 100))]
    after = [frame(40, 60, (200, 200, 200)), frame(40, 60, (210, 210, 210))]
    report = assess_visual_transition(before, after, points=sampling_grid(40, 60, columns=8, rows=10))
    assert report.decision is TransitionDecision.INCONCLUSIVE_BASELINE


def test_requires_persistent_post_change_not_one_frame_spike():
    before = [frame(40, 60, (20, 30, 40)), frame(40, 60, (20, 30, 40))]
    after = [frame(40, 60, (150, 160, 170)), frame(40, 60, (22, 31, 41))]
    report = assess_visual_transition(before, after, points=sampling_grid(40, 60, columns=8, rows=10))
    assert report.decision is TransitionDecision.INCONCLUSIVE_CHANGE
    assert report.changed_points == 0
