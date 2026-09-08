from genfarmer_automation.ui_xml import (
    UiXmlError,
    filter_against_negative_xml,
    learn_selector_candidates,
)


def xml(*nodes):
    body = "".join(nodes)
    return f'<?xml version="1.0" encoding="UTF-8"?><hierarchy rotation="0">{body}</hierarchy>'


def node(**attrs):
    encoded = " ".join(f'{key}="{value}"' for key, value in attrs.items())
    return f"<node {encoded} />"


def test_resource_id_is_preferred_and_stable():
    values = [
        xml(node(package="pkg", **{"class": "android.view.View", "resource-id": "pkg:id/feed"})),
        xml(node(package="pkg", **{"class": "android.view.View", "resource-id": "pkg:id/feed"})),
    ]
    candidates = learn_selector_candidates(values, package="pkg")
    assert candidates
    assert candidates[0].kind == "resource-id"
    assert candidates[0].unique_in_all is True
    assert "pkg:id/feed" in candidates[0].xpath


def test_dynamic_content_is_not_used_as_default_selector():
    values = [
        xml(node(package="pkg", **{"class": "android.widget.TextView", "content-desc": "12345 likes", "text": "@user"})),
        xml(node(package="pkg", **{"class": "android.widget.TextView", "content-desc": "12345 likes", "text": "@user"})),
    ]
    assert learn_selector_candidates(values, package="pkg", include_text=True) == []


def test_candidate_must_exist_in_all_positive_snapshots():
    values = [
        xml(node(package="pkg", **{"class": "android.view.View", "resource-id": "pkg:id/feed"})),
        xml(node(package="pkg", **{"class": "android.view.View", "resource-id": "pkg:id/other"})),
    ]
    assert learn_selector_candidates(values, package="pkg") == []


def test_negative_state_filters_global_selector():
    positives = [
        xml(
            node(package="pkg", **{"class": "android.view.View", "resource-id": "pkg:id/feed"}),
            node(package="pkg", **{"class": "android.view.View", "resource-id": "pkg:id/global"}),
        ),
        xml(
            node(package="pkg", **{"class": "android.view.View", "resource-id": "pkg:id/feed"}),
            node(package="pkg", **{"class": "android.view.View", "resource-id": "pkg:id/global"}),
        ),
    ]
    negatives = [
        xml(node(package="pkg", **{"class": "android.view.View", "resource-id": "pkg:id/global"}))
    ]
    candidates = learn_selector_candidates(positives, package="pkg")
    filtered = filter_against_negative_xml(candidates, negatives, package="pkg")
    assert len(filtered) == 1
    assert "pkg:id/feed" in filtered[0].xpath


def test_requires_two_positive_snapshots():
    try:
        learn_selector_candidates([xml()], package="pkg")
    except UiXmlError:
        pass
    else:
        raise AssertionError("expected fail-closed requirement for repeated snapshots")
