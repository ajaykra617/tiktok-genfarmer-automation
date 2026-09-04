from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest

from genfarmer_automation.genfarmer_client import GenFarmerClient, MutationDisabledError


def test_build_url_filters_none_and_encodes_query():
    client = GenFarmerClient("http://127.0.0.1:55554")
    url = client._build_url(
        "/automation/apps",
        {"userId": 3, "page": 1, "empty": None, "orderBy": "updatedAt"},
    )
    assert url == (
        "http://127.0.0.1:55554/automation/apps?"
        "userId=3&page=1&orderBy=updatedAt"
    )


def test_mutation_is_fail_closed_by_default():
    client = GenFarmerClient("http://127.0.0.1:55554")
    with pytest.raises(MutationDisabledError):
        client.create_run(user_id=3, task_id="task", app_id="app")


def test_mutation_opt_in_is_explicit():
    client = GenFarmerClient("http://127.0.0.1:55554", allow_mutations=True)
    assert client.allow_mutations is True
