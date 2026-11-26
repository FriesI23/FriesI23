from unittest.mock import Mock

import pytest

from profile_badges import cli


@pytest.mark.parametrize("env", ["GH_TOKEN", "GITHUB_TOKEN"])
def test_github_token_is_only_used_with_github_com(monkeypatch, env):
    client = Mock()
    gh_login = Mock()
    monkeypatch.setattr(cli, "Github", client)
    monkeypatch.setattr(cli.subprocess, "check_output", gh_login)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv(env, "workflow-test-token")

    cli.github_client("https://api.github.com")
    assert client.call_args.kwargs["auth"].token == "workflow-test-token"
    cli.github_client("https://github.example/api/v3")
    assert client.call_args.kwargs["auth"] is None
    gh_login.assert_not_called()


def test_local_github_login_is_optional(monkeypatch):
    client = Mock()
    gh_login = Mock(side_effect=["local-test-token\n", FileNotFoundError()])
    monkeypatch.setattr(cli, "Github", client)
    monkeypatch.setattr(cli.subprocess, "check_output", gh_login)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    cli.github_client("https://api.github.com")
    assert client.call_args.kwargs["auth"].token == "local-test-token"
    cli.github_client("https://api.github.com")
    assert client.call_args.kwargs["auth"] is None
