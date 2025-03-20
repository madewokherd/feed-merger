#!/usr/bin/env python

import datetime
import html
import html.parser
import json
import os
import os.path
import readline
import sys
import traceback
import urllib.parse

import core

entry_template = """<h1><a name="item{e['fm:counter']}"></a><?if e.get('fm:link')><a href="{e['fm:link']}"><?endif><?if e.get('fm:avatar')><img src="{e['fm:avatar']}" height=48><?endif>{' - '.join(x for x in (e.get('fm:feedname') or f.get('fm:title'), e.get('fm:author'), e.get('fm:title')) if x) or e.get('fm:source')}<?if e.get('fm:link')></a><?endif> {e['fm:timestamp']} <a href="#item{e['fm:counter']}">[anchor]</a></h1>

<?html <!-->
<?html {json.dumps(e, indent=2).replace('--' + chr(62), '--\\\\' + chr(62))}>
<?html --{chr(62)}>

<?if e.get('fm:thumbnail')><p><img src="{e['fm:thumbnail']}" height="240"></p><?endif>

<?if e.get('fm:html')><?html {translate_html(f, e, e['fm:html'])}><?endif>
"""

class HtmlTemplateFiller(html.parser.HTMLParser):
    def __init__(self, locals_dict):
        super().__init__()
        self.locals_dict = locals_dict
        self.strs = []
        self.stack = []
        self.output_enabled = True

    def get_contents(self):
        return ''.join(self.strs)

    def handle_starttag(self, tag, attrs, close=False):
        if not self.output_enabled:
            return

        self.strs.append('<')
        self.strs.append(tag)

        for (key, value) in attrs:
            self.strs.append(' ')
            self.strs.append(key)
            self.strs.append('="')
            self.strs.append(html.escape(str(eval(f'f"""{value}"""', globals(), self.locals_dict))))
            self.strs.append('"')

        if close:
            self.strs.append('/>')
        else:
            self.strs.append('>')

    def handle_endtag(self, tag):
        if not self.output_enabled:
            return

        self.strs.append('</')
        self.strs.append(tag)
        self.strs.append('>')

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs, close=True)

    def handle_data(self, data):
        if not self.output_enabled:
            return

        self.strs.append(html.escape(str(eval(f'f"""{data}"""', globals(), self.locals_dict))))

    def handle_pi(self, data):
        if ' ' in data:
            name, rest = data.split(' ', 1)
        else:
            name = data
            rest = ''

        if name == 'if':
            self.stack.append(('if', self.output_enabled))
            if self.output_enabled:
                self.output_enabled = bool(eval(rest, globals(), self.locals_dict))
        elif name == 'endif':
            name, output_enabled = self.stack.pop()
            if name != 'if':
                raise Exception("template has <?endif> without <?if>")
            self.output_enabled = output_enabled
        elif name == 'html':
            if not self.output_enabled:
                return

            self.strs.append(str(eval(f'f"""{rest}"""', globals(), self.locals_dict)))
        else:
            raise Exception(f"template has unknown processing instruction {name}")

def item_from_json(entry):
    template_filler = HtmlTemplateFiller({
        'e': entry,
        'f': entry.get('fm:feed', {}),
    })
    template_filler.feed(entry_template)
    template_filler.close()

    return template_filler.get_contents(), entry['fm:timestamp']

def items_from_entries(items):
    for entry in entries:
        try:
            items.append(item_from_json(entry))
        except:
            print("Failed processing json")
            print(json.dumps(entry, indent=2))
            traceback.print_exc()

_BODY_STYLES = {
    'alink': 'div.styleID a:active { color: VAL; } ',
    'vlink': 'div.styleID a:visited { color: VAL; } ',
    'link': 'div.styleID a { color: VAL; } ',
    'background': 'div.styleID { background: url("VAL"); }',
    'bgcolor': 'div.styleID { background-color: VAL; }',
    'bottommargin': 'div.styleID { margin-bottom: VAL; }',
    'leftmargin': 'div.styleID { margin-left: VAL; }',
    'topmargin': 'div.styleID { margin-top: VAL; }',
    'rightmargin': 'div.styleID { margin-right: VAL; }',
    'text': 'div.styleID { color: VAL; }',
}

_style_counter = 0

class HtmlTranslator(html.parser.HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.strs = []
        self.stack = []
        self.base = base
        self.location = None
        self.output_enabled = True
        self.in_divs = 0

    def handle_starttag(self, tag, attrs):
        body_to_div = False

        if tag == 'html':
            self.stack.append((self.location, self.output_enabled))
            self.location = 'html'
            self.output_enabled = False
            return
        if tag == 'head':
            self.stack.append((self.location, self.output_enabled))
            self.location = 'head'
            self.output_enabled = False
            return
        if tag == 'body':
            self.stack.append((self.location, self.output_enabled))
            self.location = 'body'
            self.output_enabled = True
            tag = 'div'
            body_to_div = True
            style_str = []
            global _style_counter
            _style_counter += 1
            style_id = _style_counter

        if self.location == 'head' and tag == 'base':
            attrs = dict(attrs)
            if 'href' in attrs:
                self.base = attrs['href']
            return

        if self.output_enabled:
            if tag == 'div':
                self.in_divs += 1
            if not self.in_divs:
                self.strs.append('<div>')
                self.in_divs = 1
            self.strs.append('<')
            self.strs.append(tag)
            for key, value in attrs:
                if value and key in ('src', 'href'):
                    value = urllib.parse.urljoin(self.base, value)
                self.strs.append(' ')
                self.strs.append(key)
                if value:
                    self.strs.append('="')
                    self.strs.append(html.escape(value))
                    self.strs.append('"')
                    if body_to_div:
                        if key in _BODY_STYLES:
                            style_str.append(_BODY_STYLES[key].replace('VAL', value).replace('ID', str(style_id)))
            if body_to_div and style_str:
                self.strs.append(f' class="style{style_id}"')
            self.strs.append('>')
            if body_to_div and style_str:
                self.strs.append('<style>')
                self.strs.append(html.escape('\n'.join(style_str)))
                self.strs.append('</style>')

    def handle_endtag(self, tag):
        output_was_enabled = self.output_enabled
        if tag == self.location:
            self.location, self.output_enabled = self.stack.pop()

        if tag == 'body':
            tag = 'div'

        if output_was_enabled:
            if tag == 'div':
                if self.in_divs:
                    self.in_divs -= 1
                else:
                    return
            self.strs.append('</')
            self.strs.append(tag)
            self.strs.append('>')

    def handle_data(self, data):
        if self.output_enabled:
            self.strs.append(html.escape(data))

    def get_contents(self):
        while self.in_divs:
            self.in_divs -= 1
            self.strs.append('</div>')
        return ''.join(self.strs)

def translate_html(feed, entry, data):
    parser = HtmlTranslator(entry.get('fm:base', feed.get('fm:base', '')))
    parser.feed(data)
    return parser.get_contents()

def handle_line(line):
    global entries
    if line.startswith('mastodon:'):
        import mastodon
        return mastodon.process(line, state)
    elif line.startswith('gmail:'):
        import gmail
        return gmail.process(line, state)
    elif line.startswith('nebula:'):
        import nebula
        return nebula.process(line, state, items)
    elif line.startswith(('github-branch:', 'github-issue-search')):
        import github
        return github.process(line, state, items)
    elif line.startswith(('gitlab-branch:', 'gitlab-projects:', 'gitlab-mirror-push-failures:')):
        import gitlab
        return gitlab.process(line, state, items)
    elif line.startswith('reddit:'):
        import reddit
        return reddit.process(line, state, items)
    elif line.startswith('include:'):
        process_file(line.split(':', 1)[1])
        return core.SUCCESS, None
    elif line.startswith(('http:', 'https:')):
        import web
        return web.process(line, state)
    elif line.startswith('manual:'):
        prefix, rest = line.split(':', 1)
        timestamp, title = rest.split(' ', 1)
        if timestamp > datetime.datetime.now(datetime.timezone.utc).isoformat():
            # ignore times in the future
            return core.SUCCESS, None
        return core.JSON, {
            'fm:entries': [{
                'fm:title': title,
                'fm:timestamp': timestamp,
            }]
        }
    elif line.startswith('custom:'):
        modulename = line.split(':', 2)[1]
        return __import__(modulename).process(line, state)
    elif line.startswith('filter-out:'):
        fun = eval(f'lambda e: {line[11:]}')
        entries = [entry for entry in entries if not fun(entry)]
        return core.SUCCESS, None
    elif line.startswith('bluesky:'):
        import bluesky
        return bluesky.process(line, state)
    elif line.startswith('bluesky-notifications:'):
        import bluesky
        return bluesky.process(line, state)
    elif line.startswith('mbox:'):
        import fm_email
        return fm_email.process_mbox(line, state)
    elif line.endswith('.txt'):
        process_file(line)
        return core.SUCCESS, None
    else:
        raise NotImplementedError

item_counter = 0

def add_defaults(line, j):
    favicon = None
    favicon_checked = False
    for entry in j.get('fm:entries', ()):
        entry['fm:source'] = line
        if 'fm:timestamp' not in entry:
            entry['fm:timestamp'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if 'fm:id' not in entry and 'fm:link' in entry:
            entry['fm:id'] = entry['fm:link']
        if 'fm:text' in entry and 'fm:html' not in entry:
            entry['fm:html'] = f'<div style="white-space: pre-wrap;">{html.escape(entry["fm:text"])}</div>'
        if 'fm:avatar' not in entry and line.startswith('https:'):
            if not favicon_checked:
                favicon = urllib.parse.urljoin(line, '/favicon.ico')
                try:
                    urllib.request.urlopen(urllib.request.Request(favicon, method='HEAD'))
                except:
                    favicon = None
                favicon_checked = True
            if favicon:
                entry['fm:avatar'] = favicon

        global item_counter
        item_counter += 1
        entry['fm:counter'] = item_counter

def entries_from_json(j):
    if not 'fm:entries' in j:
        return
    feed = j
    entry_list = j['fm:entries']
    del j['fm:entries']
    for entry in entry_list:
        if j:
            entry['fm:feed'] = j
        entries.append(entry)

def process_line(line):
    disposition, data = handle_line(line)
    while disposition == core.REDIRECT:
        disposition, data = handle_line(data)
    if disposition == core.JSON:
        add_defaults(line, data)
        entries_from_json(data)
    elif disposition != core.SUCCESS:
        raise Exception("unrecognized disposition")

def process_file(descfilename):
    with open(descfilename) as f:
        for line in f:
            try:
                line = line.strip()
                process_line(line)
            except:
                print("Failed processing line: ", line)
                traceback.print_exc()

descfilename = sys.argv[1]
output_filename = sys.argv[2]

entries = []
items = []

try:
    with open('feed-merger-state') as f:
        state = eval(f.read())
except FileNotFoundError:
    state = {}

if output_filename == 'debug':
    line = descfilename
    disposition, data = handle_line(line)
    while disposition == core.REDIRECT:
        print("redirected to", data)
        line = data
        disposition, data = handle_line(line)

    if disposition == core.SUCCESS:
        print("handler returned success")
    elif disposition == core.JSON:
        json.dump(data, sys.stdout, indent=2)
        add_defaults(line, data)
        print()
        print()
        entries_from_json(data)

    items_from_entries(items)

    print("stored data:", state)
    print()

    print('items:')
    for item in items:
        print(item[1], item[0])
else:
    process_line(descfilename)

    items_from_entries(items)

    items.sort(key = lambda i: i[1])

    with open(output_filename, 'w') as f:
        f.write(
        """<!DOCTYPE html>
        <html lang="en">
          <head>
            <meta charset="utf-8">
            <title>""")

        f.write(descfilename)

        f.write("""</title>
          <style>img { max-height: 100vh; max-width: 100vw; }</style>
          </head>
          <body>
        """)

        for (item, timestamp) in items:
            f.write(item)

        f.write("</body></html>")

    state_str = repr(state)
    eval(state_str)

    with open('feed-merger-state.new', 'w') as f:
        f.write(state_str)

    os.replace('feed-merger-state.new', 'feed-merger-state')

