import datetime
import urllib.parse

import pytz

import core
import web

def fetch(url, state):
    headers = {}
    headers['User-Agent'] = 'feed-merger/1.0 +https://github.com/madewokherd/feed-merger'
    if ('codeweavers', 'token') in state:
        headers['Cookie'] = f'cw={state['codeweavers', 'token']}'
    js, tokens = web.fetch_html(url, headers=headers)

    if js['html:title'] == 'Sign In | CodeWeavers':
        token = input('Enter your login token (contents of cw= cookie) for www.codeweavers.com: ')
        if token:
            headers['Cookie'] = f'cw={token}'
            js, tokens = web.fetch_html(url, headers=headers)
            if js['html:title'] == 'Sign In | CodeWeavers':
                raise Exception("login invalid")
            state['codeweavers', 'token'] = token
    return js, tokens

def process(line, state):
    url = line

    js, tokens = fetch(url, state)

    in_table = False
    in_header = False
    in_heading = False
    in_data = False
    in_level = False
    columns = []
    data_index = 0
    entry = None
    favicon = None

    for i in range(len(tokens)):
        # <link rel="shortcut icon" href="...">
        if tokens[i][0] == web.STARTTAG and tokens[i][1] == 'link':
            attrs = dict(tokens[i][2])
            if attrs.get('rel') in ("icon", "shortcut icon", "apple-touch-icon"):
                favicon = attrs['href']
        # <table id="teTable">
        elif tokens[i][0] == web.STARTTAG and tokens[i][1] == 'table' and 'teTable' in dict(tokens[i][2]).get('class', ''):
            in_table = True
            in_header = True
            in_heading = False
            js['fm:entries'] = entries = []
        # <th>
        elif in_header and tokens[i][0] == web.STARTTAG and tokens[i][1] == 'th':
            in_heading = True
        # <th>DATA</th>
        elif in_heading and tokens[i][0] == web.DATA and not tokens[i][1].isspace():
            columns.append(tokens[i][1].strip())
            in_heading = False
        # </thead>
        elif in_header and tokens[i][0] == web.ENDTAG and tokens[i][1] == 'thead':
            in_header = False
            in_heading = False
        # <tr>
        elif in_table and tokens[i][0] == web.STARTTAG and tokens[i][1] == 'tr':
            entry = {}
            data_index = 0
        # <td>
        elif in_table and tokens[i][0] == web.STARTTAG and tokens[i][1] == 'td':
            in_data = True
        # <a href="...">
        elif in_data and tokens[i][0] == web.STARTTAG and tokens[i][1] == 'a':
            attrs = dict(tokens[i][2])
            if 'href' in attrs:
                entry[f'codeweavers:link:{columns[data_index]}'] = urllib.parse.urljoin(url, attrs['href'])
        # <img src="...">
        elif in_data and tokens[i][0] == web.STARTTAG and tokens[i][1] == 'img':
            attrs = dict(tokens[i][2])
            if 'src' in attrs:
                entry[f'codeweavers:img:{columns[data_index]}'] = urllib.parse.urljoin(url, attrs['src'])
        # <span class="cust-level">
        elif in_data and tokens[i][0] == web.STARTTAG and tokens[i][1] == 'span':
            attrs = dict(tokens[i][2])
            if 'cust-level' in attrs.get('class', ''):
                in_level = True
        # </span>
        elif in_level and tokens[i][0] == web.ENDTAG and tokens[i][1] == 'span':
            in_level = False
        # <td>DATA</td>
        elif in_data and not in_level and tokens[i][0] == web.DATA and not tokens[i][1].isspace():
            attr = f'codeweavers:{columns[data_index]}'
            if attr not in entry:
                entry[attr] = tokens[i][1].strip()
        # </td>
        elif in_data and tokens[i][0] == web.ENDTAG and tokens[i][1] == 'td':
            in_data = False
            data_index += 1
        # </tr>
        elif entry and tokens[i][0] == web.ENDTAG and tokens[i][1] == 'tr':
            entries.append(entry)
            entry = None
        # </table>
        elif in_table and tokens[i][0] == web.ENDTAG and tokens[i][1] == 'table':
            break

    if not in_table:
        return core.UNHANDLED, None

    for entry in entries:
        if 'codeweavers:Forum' in entry and 'codeweavers:Thread' in entry:
            entry['fm:title'] = f'{entry['codeweavers:Forum']} - {entry['codeweavers:Thread']}'
        elif 'codeweavers:Thread' in entry:
            entry['fm:title'] = entry['codeweavers:Thread']
        elif 'codeweavers:Summary' in entry:
            entry['fm:title'] = entry['codeweavers:Summary']
        if 'codeweavers:link:Thread' in entry:
            entry['fm:link'] = entry['codeweavers:link:Thread']
        elif 'codeweavers:link:Id' in entry:
            entry['fm:link'] = entry['codeweavers:link:Id']
        if 'codeweavers:Author' in entry:
            entry['fm:author'] = entry['codeweavers:Author']
        elif 'codeweavers:Posted By' in entry:
            entry['fm:author'] = entry['codeweavers:Posted By']
        if 'codeweavers:link:Author' in entry:
            entry['fm:author_link'] = entry['codeweavers:link:Author']
        elif 'codeweavers:link:Posted By' in entry:
            entry['fm:author_link'] = entry['codeweavers:link:Posted By']
        if 'codeweavers:img:Author' in entry:
            entry['fm:avatar'] = entry['codeweavers:img:Author']
        elif 'codeweavers:img:Posted By' in entry:
            entry['fm:avatar'] = entry['codeweavers:img:Posted By']
        elif favicon:
            entry['fm:avatar'] = favicon
        if 'codeweavers:Last Post Time' in entry:
            entry['codeweavers:timestamp'] = entry['codeweavers:Last Post Time']
        elif 'codeweavers:Last Update' in entry:
            entry['codeweavers:timestamp'] = entry['codeweavers:Last Update']
        if 'codeweavers:timestamp' in entry:
            dt = datetime.datetime.strptime(entry['codeweavers:timestamp'], '%Y-%m-%d %H:%M')
            dt = pytz.timezone('US/Central').localize(dt).astimezone(datetime.timezone.utc)
            entry['fm:timestamp'] = dt.isoformat()

    js['fm:title'] = js['html:title'].split(' | ', 1)[0]
    js['codeweavers:columns'] = columns

    prev_latest = state.get(('codeweavers', url, 'latest'))
    if prev_latest:
        js['fm:entries'] = [entry for entry in js['fm:entries'] if entry['fm:timestamp'] > prev_latest]

    if js['fm:entries']:
        state['codeweavers', url, 'latest'] = max(entry['fm:timestamp'] for entry in js['fm:entries'])

    return core.JSON, js
