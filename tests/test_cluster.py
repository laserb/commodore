"""
Unit-tests for catalog compilation
"""

import click
from unittest.mock import patch
import pytest

from commodore import compile
from commodore.cluster import Cluster
from commodore.config import Config


@pytest.fixture
def data():
    return {
        "config": Config(
            "https://syn.example.com", "token", "ssh://git@git.example.com", False
        ),
        "cluster": {"tenant": "t-foo"},
        "tenant": {"id": "t-foo"},
    }


def lieutenant_query(api_url, api_token, api_endpoint, api_id):
    if api_endpoint == "clusters":
        return {"id": api_id}

    if api_endpoint == "tenants":
        return {"id": api_id}

    raise click.ClickException(f"call to unexpected API endpoint '#{api_endpoint}'")


@patch("commodore.cluster.lieutenant_query")
def test_no_tenant_reference(test_patch):
    customer_id = "t-wild-fire-234"
    config = Config(
        "https://syn.example.com", "token", "ssh://git@git.example.com", False
    )
    test_patch.side_effect = lieutenant_query
    with pytest.raises(click.ClickException) as err:
        compile.load_cluster_from_api(config, customer_id)
    assert "cluster does not have a tenant reference" in str(err)


def test_cluster_global_git_repo_url(data):
    cluster = Cluster(data["config"], data["cluster"], data["tenant"])
    assert (
        "ssh://git@git.example.com/commodore-defaults.git"
        == cluster.global_git_repo_url
    )

    set_on_tenant = data.copy()
    set_on_tenant["tenant"]["globalGitRepoURL"] = "ssh://git@example.com/tenant.git"
    cluster = Cluster(
        set_on_tenant["config"], set_on_tenant["cluster"], set_on_tenant["tenant"]
    )
    assert "ssh://git@example.com/tenant.git" == cluster.global_git_repo_url
