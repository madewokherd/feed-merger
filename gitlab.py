import json
import urllib.error
import urllib.parse
import urllib.request

import core

from html import escape as e

def get_token(url, state, force = False):
    host = urllib.parse.urlparse(url)._replace(fragment="", query="", path="").geturl()

    if not force:
        return state.get(('gitlab', host, 'token'))

    token_pref_url = urllib.parse.urlparse(url)._replace(fragment="", query="", path="/-/user_settings/personal_access_tokens").geturl()

    print(f"Please generate a token at {token_pref_url}")
    print("It should have the read_api scope")
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
        elif e.code == 404:
            response = input(f"{url} returned 404 error. This could either be because the resource really doesn't exist, or because it's private and you don't have permission to view it. Attempt to log in?[Y/n] ")
            if response.lower() in ('', 'y', 'yes'):
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

def process_projects(line, state, items):
    host = urllib.parse.urlparse(line)._replace(fragment="", query="", path="").geturl()

    query_dict = urllib.parse.parse_qs(urllib.parse.urlparse(line).query)

    since = state.get(('gitlab', 'projects', line, 'since'))

    if since:
        query_dict['id_after'] = since

    new_since = None

    page = 1

    json_result = {'fm:entries': []}

    while True:
        url = urllib.parse.urlparse(host)._replace(path="/api/v4/projects", query=
            urllib.parse.urlencode(query_dict)).geturl()
        j = json.load(api_request(state, url))

        if not j:
            break

        json_result['fm:entries'].extend(j)

        if new_since is None:
            new_since = j[0]['id']

        if since is None:
            break

        page += 1

        query_dict['page'] = page

    for e in json_result['fm:entries']:
        e['fm:title'] = e['name_with_namespace']
        e['fm:timestamp'] = e['created_at']
        if e.get('description'):
            e['fm:text'] = e['description']
        e['fm:link'] = e['web_url']

    state['gitlab', 'projects', line, 'since'] = new_since or since

    return core.JSON, json_result

def process(line, state, items):
    prefix, line = line.split(':', 1)

    if prefix == 'gitlab-branch':
        process_branch(line, state, items)
        return core.SUCCESS, None
    elif prefix == 'gitlab-projects':
        return process_projects(line, state, items)

