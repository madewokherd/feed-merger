import json
import urllib.error
import urllib.parse
import urllib.request

from html import escape as e

def get_token(url, state, force = False):
    host = urllib.parse.urlparse(url)._replace(fragment="", query="", path="").geturl()

    if not force:
        return state.get(('gitlab', host, 'token'))

    token_pref_url = urllib.parse.urlparse(url)._replace(fragment="", query="", path="/-/user_settings/personal_access_tokens").geturl()

    print(f"Please generate a token at {token_pref_url}")
    print("It should have the read_repository scope")
    token = input("Enter token: ")

    state['gitlab', host, 'token'] = token
    return token

def api_request(state, url, data = None):
    token = get_token(url, state)

    try:
        if token:
            req = urllib.request.Request(url, data = data, headers = {
                'Authorization': 'Bearer ' + token,
            })
        else:
            req = urllib.request.Request(url, data = data)
        return urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            token = get_token(url, state, force = True)

            req = urllib.request.Request(url, data = data, headers = {
                'Authorization': 'Bearer ' + token,
            })
            return urllib.request.urlopen(req)
        raise

def process_branch(line, state, items):
    host = urllib.parse.urlparse(line)._replace(fragment="", query="", path="").geturl()

    path = urllib.parse.urlparse(line).path

    owner, repo, branch = path.lstrip('/').split('/')

    project = urllib.parse.quote(f'{owner}/{repo}').replace('/', '%2F')

    since = state.get(('gitlab', 'branch', host, owner, repo, branch, 'since'))
    since_sha = state.get(('gitlab', 'branch', host, owner, repo, branch, 'since_sha'))

    if since:
        url = urllib.parse.urlparse(line)._replace(
            path=f"/api/v4/projects/{project}/repository/commits",
            query=urllib.parse.urlencode({
                'ref_name': branch,
                'since': since,
                'per_page': 100,
            }),
            fragment="").geturl()
    else:
        url = urllib.parse.urlparse(line)._replace(
            path=f"/api/v4/projects/{project}/repository/commits",
            query=urllib.parse.urlencode({
                'ref_name': branch,
                'per_page': 1,
            }),
            fragment="").geturl()

    recent = None
    recent_sha = None

    page = 1

    while True:
        j = json.load(api_request(state, url))

        for commit in j:
            if recent is None:
                recent = commit['created_at']
                recent_sha = commit['id']

            if commit['id'] == since_sha:
                break

            message = e(commit['message']).replace('\n','<br>')

            content = f"""

<h1><a href="{e(commit['web_url'])}">{e(commit['author_name'])}: {e(commit['title'])}</a> {commit['created_at']} <a name="{commit['id']}" href="#{commit['id']}">[anchor]</a></h1>

<p>{message}</p>"""

            items.append((content, commit['created_at']))

        if not since or len(j) < 100:
            break

        page += 1

        url = urllib.parse.urlparse(line)._replace(
            path=f"/api/v4/projects/{project}/repository/commits",
            query=urllib.parse.urlencode({
                'ref_name': branch,
                'since': since,
                'per_page': 100,
                'page': page,
            }),
            fragment="").geturl()

    state['gitlab', 'branch', host, owner, repo, branch, 'since'] = recent or since
    state['gitlab', 'branch', host, owner, repo, branch, 'since_sha'] = recent_sha or since_sha

def process(line, state, items):
    prefix, line = line.split(':', 1)

    if prefix == 'gitlab-branch':
        process_branch(line, state, items)

