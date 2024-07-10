import datetime
import email.utils
import html.parser
import urllib.error
import urllib.request

import core

# token values:
STARTTAG = 'STARTTAG'
ENDTAG = 'ENDTAG'
DATA = 'DATA'
COMMENT = 'COMMENT'
DECL = 'DECL'
PI = 'PI'
UNKNOWN = 'UNKNOWN'

class HtmlTokenizer(html.parser.HTMLParser):
    def __init__(self, convert_charrefs=True):
        self.tokens = []
        super().__init__(convert_charrefs=convert_charrefs)

    def handle_starttag(self, tag, attrs):
        self.tokens.append((STARTTAG, tag, attrs))
    
    def handle_endtag(self, tag):
        self.tokens.append((ENDTAG, tag, False))

    def handle_startendtag(self, tag, attrs):
        self.tokens.append((STARTTAG, tag, attrs))
        self.tokens.append((ENDTAG, tag, True))

    def handle_data(self, data):
        self.tokens.append((DATA, data, None))

    def handle_comment(self, data):
        self.tokens.append((DATA, data, None))

    def handle_decl(self, decl):
        self.tokens.append((DECL, decl, None))

    def handle_pi(self, data):
        self.tokens.append((PI, data, None))

def handle_soundgasm(url, js, state, data, data_str, tokens):
    import agegate
    agegate.check(state)

    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.path.startswith('/u/') and parsed_url.path.strip('/').count('/') == 1:
        # User page
        js['fm:author'] = parsed_url.path.strip('/').split('/')[1]
        js['fm:entries'] = entries = []

        prev_mtime = state.get(('soundgasm', url, 'latest_mtime'))
        prev_url = state.get(('soundgasm', url, 'latest_url'))

        new_mtime = None
        new_url = None

        found_any = False

        for i in range(len(tokens)):
            if tokens[i][0] == STARTTAG and tokens[i][1] == 'div' and dict(tokens[i][2]).get('class') == 'sound-details':
                entry = {}
                found_any = True
                entry['fm:author'] = js['fm:author']
                j = i + 1

                # parse html data
                assert tokens[j][0] == STARTTAG and tokens[j][1] == 'a'
                entry['fm:link'] = urllib.parse.urljoin(url, dict(tokens[j][2])['href'])
                j += 1

                if entry['fm:link'] == prev_url:
                    break

                new_url = entry['fm:link']

                assert tokens[j][0] == DATA and tokens[j][1].strip()
                entry['fm:title'] = tokens[j][1]
                j += 1

                while not (tokens[j][0] == ENDTAG and tokens[j][1] == 'div'):
                    if tokens[j][0] == STARTTAG and tokens[j][1] == 'span' and dict(tokens[j][2]).get('class') == 'soundDescription':
                        j += 1
                        if tokens[j][0] == DATA:
                            if tokens[j][1].strip():
                                entry['fm:text'] = tokens[j][1]
                            j += 1
                    elif tokens[j][0] == STARTTAG and tokens[j][1] == 'span' and dict(tokens[j][2]).get('class') == 'playCount':
                        j += 1

                        assert tokens[j][0] == DATA and tokens[j][1].strip()
                        entry['play_count'] = int(tokens[j][1].rsplit(' ', 1)[-1])
                        j += 1
                    else:
                        j += 1

                entry_html = urllib.request.urlopen(entry['fm:link']).read().decode('utf-8')

                entry['media_url'] = entry_html.split('            m4a: "', 1)[1].split('"', 1)[0]

                req = urllib.request.Request(entry['media_url'], method='HEAD', headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0',
                })
                html_mtime = urllib.request.urlopen(req).headers['Last-Modified']
                entry['fm:timestamp'] = email.utils.parsedate_to_datetime(html_mtime).isoformat()

                if prev_mtime and entry['fm:timestamp'] <= prev_mtime:
                    break

                if new_mtime is None:
                    new_mtime = entry['fm:timestamp']

                entries.append(entry)
        
                if not prev_mtime:
                    break

        if not found_any:
            raise Exception("Didn't find any uploads")

        state['soundgasm', url, 'latest_mtime'] = new_mtime or prev_mtime
        state['soundgasm', url, 'latest_url'] = new_url or prev_url
        return core.JSON, js

    return core.UNHANDLED, None

def handle_mcstories(url, js, state, data, data_str, tokens):
    import agegate
    agegate.check(state)

    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.path.startswith('/Authors/') and 'html:meta:name:dcterms.creator' in js:
        # Author page
        js['fm:author'] = js['html:meta:name:dcterms.creator']
        js['fm:entries'] = entries = []

        prev_latest = state.get(('mcstories', url, 'latest'))

        new_latest = None

        found_any = False

        for i in range(len(tokens)):
            if tokens[i][0] == STARTTAG and tokens[i][1] == 'tr' and \
                tokens[i+1][0] == STARTTAG and tokens[i+1][1] == 'td':
                entry = {}
                found_any = True
                entry['fm:author'] = js['fm:author']
                j = i+2
                td = 0
                in_cite = False
                while not (tokens[j][0] == ENDTAG and tokens[j][1] == 'tr'):
                    if tokens[j][0] == STARTTAG and tokens[j][1] == 'td':
                        td += 1
                    elif tokens[j][0] == STARTTAG and tokens[j][1] == 'a':
                        entry['fm:link'] = urllib.parse.urljoin(url, dict(tokens[j][2])['href'])
                    elif tokens[j][0] == STARTTAG and tokens[j][1] == 'cite':
                        in_cite = True
                    elif tokens[j][0] == DATA and tokens[j][1].strip():
                        if td == 0 and in_cite:
                            entry['fm:title'] = tokens[j][1]
                            in_cite = False
                        elif td == 1:
                            entry['codes'] = tokens[j][1]
                        elif td == 2:
                            entry['ctime'] = tokens[j][1]
                        elif td == 3:
                            entry['mtime'] = tokens[j][1]
                    j += 1

                entry_ts = entry.get('mtime', entry['ctime'])
                entry_ts = datetime.datetime.strptime(entry_ts, '%d %b %Y').isoformat()

                if prev_latest and entry_ts <= prev_latest:
                    continue

                if not new_latest or new_latest < entry_ts:
                    new_latest = entry_ts

                entry['fm:timestamp'] = entry_ts

                if prev_latest:
                    entry_html_json, entry_tokens = fetch_html(entry['fm:link'])
                    entry['fm:timestamp'] = entry_html_json['http:mtime_iso']
                    entry['fm:text'] = entry_html_json['html:meta:name:dcterms.description']

                entries.append(entry)

        if not found_any:
            raise Exception("Didn't find any stories")

        state['mcstories', url, 'latest'] = new_latest or prev_latest
        return core.JSON, js

    return core.UNHANDLED, None


html_host_handlers = {
    'com': {
        'mcstories': handle_mcstories,
    },
    'net': {
        'soundgasm': handle_soundgasm,
    },
}

def find_host_handler(url, host_handlers):
    for segment in urllib.parse.urlparse(url).hostname.split('.')[::-1]:
        if segment not in host_handlers:
            return None
        host_handlers = host_handlers[segment]
        if not isinstance(host_handlers, dict):
            return host_handlers

def handle_html(url, js, state, data, data_str, tokens, use_handlers=True):
    old_charset = js.get('http:charset', 'utf-8')

    # look for a charset declaration
    html_charset = None
    for i in range(len(tokens)):
        if tokens[i][0] == STARTTAG and tokens[i][1] == 'meta':
            attrs = dict(tokens[i][2])
            if 'charset' in attrs:
                html_charset = attrs['charset']
                break
            if 'http-equiv' in attrs and attrs.get('http-equiv').lower() == 'content-type' and \
                'content' in attrs and 'charset=' in attrs['content'].lower():
                html_charset = attrs['content'].lower().split('charset=', 1)[1].split(';', 1)[0]
                break

    if html_charset and html_charset != old_charset:
        data_str = data.decode(html_charset, errors='replace')
        parser = HtmlTokenizer()
        parser.feed(data_str)
        tokens = parser.tokens

    for i in range(len(tokens)):
        if tokens[i][0] == STARTTAG and tokens[i][1] == 'meta':
            attrs = dict(tokens[i][2])
            if 'name' in attrs and 'content' in attrs:
                js[f'html:meta:name:{attrs["name"].lower()}'] = attrs['content']
            elif 'http-equiv' in attrs and 'content' in attrs:
                js[f'html:meta:http-equiv:{attrs["http-equiv"].lower()}'] = attrs['content']
            elif 'charset' in attrs:
                js['html:meta:charset'] = attrs['charset']
            elif 'itemprop' in attrs and 'content' in attrs:
                js[f'html:meta:itemprop:{attrs["itemprop"].lower()}'] = attrs['content']
        elif tokens[i][0] == STARTTAG and tokens[i][1] == 'title':
            try:
                if tokens[i+1][0] == DATA:
                    js['html:title'] = tokens[i+1][1]
            except IndexError:
                pass

    if use_handlers:
        host_handler = find_host_handler(url, html_host_handlers)
        if host_handler:
            result = host_handler(url, js, state, data, data_str, tokens)
            if result[0] != core.UNHANDLED:
                return result

    # defaults:
    entry = {}
    js['fm:entries'] = [entry]

    if 'html:title' in js:
        entry['fm:title'] = js['html:title']

    if 'html:meta:name:author' in js:
        entry['fm:author'] = js['html:meta:name:author']

    entry['fm:html'] = data_str

    return core.JSON, js

def handle_sgml(url, js, state, response):
    data = response.read()

    data_str = data.decode(js.get('http:charset', 'utf-8'), errors='replace')
    parser = HtmlTokenizer()
    parser.feed(data_str)

    for token in parser.tokens:
        token_type, tag, tdata = token

        if token_type == DECL:
            tag, rest = tag.split(' ', 1)
            if tag.lower() == 'doctype':
                if rest.split(' ', 1)[0] == 'html':
                    return handle_html(url, js, state, data, data_str, parser.tokens)
                else:
                    break
        elif token_type == STARTTAG:
            if tag == 'html':
                return handle_html(url, js, state, data, data_str, parser.tokens)
            else:
                break
        elif token_type == DATA:
            break

    if js.get('http:mimetype') in ('text/html', 'text/xhtml+xml'):
        return handle_html(url, js, state, data, data_str, parser.tokens)

    # Don't know how to parse this, just use the defaults
    js['fm:entries'] = [{}]
    return core.JSON, js

mimetype_handlers = {
    'text/html': handle_sgml,
    'text/xhtml+xml': handle_sgml,
    'text/xml': handle_sgml,
    'application/xml': handle_sgml,
}

def fetch_html(url, *args, **kwargs):
    # returns json, tokens
    js, headers, response = fetch_http(url, *args, **kwargs)

    data = response.read()
    data_str = data.decode('utf-8', errors='replace')
    parser = HtmlTokenizer()
    parser.feed(data_str)

    _disposition, js = handle_html(url, js, {}, data, data_str, parser.tokens, False)

    fill_http_defaults(js)

    return js, parser.tokens

def fetch_http(url, data=None, headers={}):
    # returns json, headers, response
    req = urllib.request.Request(url, data=data, headers=headers)

    try:
        response = urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return None, e.headers, e.fp
        raise

    j = {}
    # fill in http fields
    if 'http:headers' not in j:
        headers = {}
        for key, value in response.getheaders():
            key = key.lower()
            if key in headers:
                if isinstance(headers[key], list):
                    headers[key].append(value)
                else:
                    headers[key] = [headers[key], value]
            else:
                headers[key] = value
        j['http:headers'] = headers
    if 'http:url' not in j:
        j['http:url'] = url

    return j, response.headers, response

def fill_http_defaults(json):
    j = json
    if 'fm:base' not in j and 'http:url' in j:
        j['fm:base'] = j['http:url']

    if 'http:headers' in j:
        if "last-modified" in j['http:headers']:
            mtime_iso = email.utils.parsedate_to_datetime(j['http:headers']['last-modified']).isoformat()

            if 'http:mtime_iso' not in j:
                j['http:mtime_iso'] = mtime_iso

            if 'fm:entries' in j:
                for entry in j['fm:entries']:
                    if 'fm:timestamp' not in entry:
                        entry['fm:timestamp'] = mtime_iso

    if 'fm:entries' in j and 'http:url' in j:
        for entry in j['fm:entries']:
            if 'fm:link' not in entry:
                entry['fm:link'] = j['http:url']

def process(line, state):
    etag = state.get(('web', line, 'etag'))
    mtime = state.get(('web', line, 'mtime'))

    headers = {}
    if etag:
        headers['If-None-Match'] = etag
    if mtime:
        headers['If-Modified-Since'] = mtime

    json, headers, response = fetch_http(line, headers=headers)
    if json is None:
        # 304 status
        return core.SUCCESS, None

    if 'content-type' in headers:
        ct = headers['content-type']
        if not isinstance(ct, list):
            ct = ct.lower()
            if 'boundary=' not in ct:
                json['http:mimetype'] = ct.split(';', 1)[0]
                if 'charset=' in ct:
                    json['http:charset'] = ct.split('charset=', 1)[1].split(';', 1)[0]

    if json.get('http:headers', {}).get('content-type', '').split(';', 1)[0].lower() in mimetype_handlers:
        result = mimetype_handlers[json['http:mimetype']](line, json, state, response)
    else:
        # Don't know how to parse this, just use the defaults
        result = core.JSON, json
        json['fm:entries'] = [{}]

    if result[0] == core.JSON:
        j = result[1]

        fill_http_defaults(j)

    state['web', line, 'etag'] = response.headers.get('ETag')
    state['web', line, 'mtime'] = response.headers.get('Last-Modified')

    return result
