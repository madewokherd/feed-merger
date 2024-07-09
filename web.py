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

def handle_html(url, js, state, data, data_str, tokens):
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

def fetch_http(url, data=None, headers=None):
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
