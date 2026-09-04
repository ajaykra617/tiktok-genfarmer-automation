from genfarmer_automation.flow import FlowDocument, find_flow, infer_node_kind


def sample_flow():
    return {
        "nodes": [
            {
                "id": "n1",
                "type": "example",
                "position": {"x": 10, "y": 20},
                "data": {"nested": {"value": 123}, "unknown": [1, 2, 3]},
                "vendorField": "preserve-me",
            },
            {
                "id": "n2",
                "data": {"nodeType": "wait", "duration": 2},
            },
        ],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n2", "sourceHandle": "out"}
        ],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }


def test_find_nested_flow():
    flow = sample_flow()
    payload = {"data": {"app": {"script": {"flow": flow}}}}
    assert find_flow(payload) == flow


def test_lossless_roundtrip():
    flow = sample_flow()
    doc = FlowDocument.from_flow(flow)
    assert doc.to_dict() == flow
    assert doc.validate_basic() == []


def test_node_kind_detection():
    flow = sample_flow()
    assert infer_node_kind(flow["nodes"][0]) == ("example", "type")
    assert infer_node_kind(flow["nodes"][1]) == ("wait", "data.nodeType")


def test_clone_and_patch_preserves_unknown_fields():
    doc = FlowDocument.from_flow(sample_flow())
    clone = doc.clone_node(
        "n1",
        new_id="n3",
        patch={"data": {"nested": {"value": 456}}},
    )
    assert clone["vendorField"] == "preserve-me"
    assert clone["data"]["unknown"] == [1, 2, 3]
    assert clone["data"]["nested"]["value"] == 456


def test_remove_node_removes_incident_edges():
    doc = FlowDocument.from_flow(sample_flow())
    doc.remove_node("n2")
    assert [node["id"] for node in doc.nodes] == ["n1"]
    assert doc.edges == []
