from genfarmer_automation.upload_surface import sanitized_upload_rows


def _node(**attrs) -> str:
    base = {
        "text": "",
        "content-desc": "",
        "resource-id": "",
        "class": "android.view.View",
        "package": "com.zhiliaoapp.musically",
        "clickable": "true",
        "enabled": "true",
        "bounds": "[0,0][100,100]",
    }
    base.update(attrs)
    return "<node " + " ".join(f'{k}="{v}"' for k, v in base.items()) + " />"


def test_probe_keeps_upload_terms_and_duration_but_redacts_arbitrary_titles():
    xml = '<hierarchy>' + ''.join(
        [
            _node(text="Upload"),
            _node(**{"content-desc": "Video 00:03"}),
            _node(text="private holiday title"),
        ]
    ) + '</hierarchy>'
    rows = sanitized_upload_rows(xml)
    values = [(row.text, row.content_desc) for row in rows]
    assert ("Upload", "") in values
    assert ("", "Video 00:03") in values
    assert all("holiday" not in (text + desc).casefold() for text, desc in values)


def test_probe_keeps_dedicated_album_name():
    xml = '<hierarchy>' + _node(text="GenFarmerBoost") + '</hierarchy>'
    rows = sanitized_upload_rows(xml)
    assert len(rows) == 1
    assert rows[0].text == "GenFarmerBoost"
