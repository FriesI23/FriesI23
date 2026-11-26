"""Exercise PyGithub pagination against fixture responses."""

from urllib.parse import urlencode, urljoin

from github import Github


def github_with_responses(base_url, respond):
    client = Github(base_url=base_url, lazy=True, per_page=100)

    def request(method, url, parameters=None, **kwargs):
        assert method == "GET"
        url = urljoin(base_url, url)
        if parameters:
            url += "?" + urlencode(parameters)
        result = respond(url)
        # Supply the next page through GitHub's Link header.
        if isinstance(result, tuple):
            data, next_url = result
            return {"link": f'<{next_url}>; rel="next"'}, data
        return {}, result

    client.requester.requestJsonAndCheck = request
    return client
