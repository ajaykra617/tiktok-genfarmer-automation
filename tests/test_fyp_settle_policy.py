from genfarmer_automation.fyp_settle_policy import settle_policy


def test_normal_fyp_settle_allows_slow_physical_card_render():
    policy = settle_policy(post_restart=False)
    assert policy.checks == 8
    assert policy.interval_seconds == 0.75
    assert policy.stable_observations == 2


def test_post_restart_fyp_settle_keeps_longer_budget():
    policy = settle_policy(post_restart=True)
    assert policy.checks == 15
    assert policy.interval_seconds == 1.0
    assert policy.stable_observations == 3
