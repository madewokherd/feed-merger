import json
import urllib.request
import urllib.parse
import urllib.error

from html import escape as e

def get_token(state, force=False):
    if not force and state.get(('github', 'token')):
        return state['github', 'token']

    print("Please visit https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-fine-grained-personal-access-token and follow the instructions to create an access token")
    print("The token doesn't need any permissions beyond read-only access to any repositories you want to follow.")
    token = input("Enter token: ")

    state['github', 'token'] = token
    return token

def api_request(state, url, data=None):
    token = get_token(state)

    try:
        req = urllib.request.Request(url, data = data, headers = {
            'Authorization': 'Bearer ' + token,
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
        })
        return urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            token = get_token(state, force = True)

            req = urllib.request.Request(url, data = data, headers = {
                'Authorization': 'Bearer ' + token,
                'Accept': 'application/vnd.github+json',
                'X-GitHub-Api-Version': '2022-11-28',
            })
            return urllib.request.urlopen(req)
        raise

def process_branch(line, state, items):
    owner, repo, branchname = line.split('/')

    since = state.get(('github', 'branch', owner, repo, branchname, 'since'))
    since_sha = state.get(('github', 'branch', owner, repo, branchname, 'since_sha'))

    if since:
        url = urllib.parse.urlparse(f"https://api.github.com/repos/{owner}/{repo}/commits")._replace(
            query = urllib.parse.urlencode({
                'sha': branchname,
                'since': since,
                'per_page': 100,
            })).geturl()
    else:
        url = urllib.parse.urlparse(f"https://api.github.com/repos/{owner}/{repo}/commits")._replace(
            query = urllib.parse.urlencode({
                'sha': branchname,
                'per_page': 1,
            })).geturl()

    recent = None
    recent_sha = None

    page = 1

    while True:
        list_response = api_request(state, url)

        j = json.load(list_response)

        for commit in j:
            if recent is None:
                recent = commit['commit']['committer']['date']
                recent_sha = commit['sha']

            if commit['sha'] == since_sha:
                break

            content = f"""

<h1><a href="{e(commit['html_url'])}">{e(commit['commit']['author']['name'])}: {e(commit['commit']['message'].splitlines()[0].strip())}</a> {commit['commit']['committer']['date']} <a name="{commit['sha']}" href="#{commit['sha']}">[anchor]</a></h1>"""

            for line in commit['commit']['message'].splitlines()[1:]:
                content += f"<p>{e(line)}</p>"

            items.append((content, commit['commit']['committer']['date']))

        if not since or len(j) < 100:
            break

        page += 1

        url = urllib.parse.urlparse(f"https://api.github.com/repos/{owner}/{repo}/commits")._replace(
            query = urllib.parse.urlencode({
                'sha': branchname,
                'since': since,
                'per_page': 100,
                'page': page,
            })).geturl()

    state['github', 'branch', owner, repo, branchname, 'since'] = recent or since
    state['github', 'branch', owner, repo, branchname, 'since_sha'] = recent_sha or since_sha

def process(line, state, items):
    prefix, line = line.split(':', 1)

    if prefix == 'github-branch':
        process_branch(line, state, items)
