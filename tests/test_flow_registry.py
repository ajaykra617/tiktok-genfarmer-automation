import json

from genfarmer_automation.flow_registry import TemplateRegistry, semantic_kind


def test_semantic_kind_prefers_data_action():
    node = {"type": "custom", "data": {"action": "wait"}}
    assert semantic_kind(node) == "custom:wait"


def test_registry_deduplicates_structural_variants_and_clones(tmp_path):
    corpus = [
        {
            "app_id": "a",
            "flow": {
                "nodes": [
                    {
                        "id": "n1",
                        "type": "custom",
                        "data": {
                            "action": "wait",
                            "options": {"timeout": "2", "disabled": False},
                        },
                    },
                    {
                        "id": "n2",
                        "type": "custom",
                        "data": {
                            "action": "wait",
                            "options": {"timeout": "9", "disabled": True},
                        },
                    },
                ],
                "edges": [],
            },
        }
    ]
    path = tmp_path / "raw.json"
    path.write_text(json.dumps(corpus), encoding="utf-8")

    registry = TemplateRegistry.from_raw_corpus(path)
    assert registry.available_kinds() == ["custom:wait"]
    # Same field/type schema -> one structural variant.
    assert len(registry.variants("custom:wait")) == 1

    clone = registry.clone(
        "custom:wait",
        new_id="new-node",
        patch={"data": {"options": {"timeout": "5"}}},
    )
    assert clone["id"] == "new-node"
    assert clone["data"]["action"] == "wait"
    assert clone["data"]["options"]["timeout"] == "5"
