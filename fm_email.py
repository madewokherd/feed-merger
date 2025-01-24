import base64
import datetime
import email.policy
import html
import json

import core
import web

def format_part(part):
    part_type = part.get_content_type()
    if part_type == 'text/html':
        return part.get_content()
    elif part_type == 'text/plain':
        return f'''<p style="white-space: pre-wrap;">{html.escape(part.get_content())}</p>'''
    elif part_type == 'image/png':
        return f'''<p><img src="data:{part_type};base64,{base64.b64encode(part.get_content()).decode('ascii')}"></p>'''
    elif part_type == 'multipart/alternative':
        return format_content(part)
    else:
        print(f"Unknown body content type {part_type}")
        return ''

def format_content(msg):
    html_parts = []

    body = msg.get_body()

    if not body:
        return ''

    if body.is_multipart():
        parts = [part for part in body.iter_parts() if not part.is_attachment()]
    else:
        parts = (body,)

    for part in parts:
        html_parts.append(format_part(part))

    # TODO: attachments - use a tag with href as a data: url and download="filename"

    return '\n'.join(html_parts)

def format_message(msg, format_html=False):
    result = {}

    result['email:headers'] = headers = {}

    for key in msg.keys():
        headers[key.lower()] = msg.get_all(key)

    if headers.get('from'):
        result['fm:author'] = headers['from'][0].split(' <', 1)[0]

    if headers.get('subject'):
        result['fm:title'] = headers['subject'][0]

    if headers.get('date'):
        result['fm:timestamp'] = email.utils.parsedate_to_datetime(headers['date'][0]).astimezone(datetime.timezone.utc).isoformat()

    result['email:content_type'] = msg.get_content_type()

    if msg.get_filename():
        result['email:filename'] = msg.get_filename()

    result['email:is_attachment'] = msg.is_attachment()

    if msg.is_multipart():
        result['email:parts'] = parts = []
        for part in msg.iter_parts():
            parts.append(format_message(part))

    if format_html:
        result['fm:html'] = format_content(msg)

        parser = web.HtmlTokenizer()
        parser.feed(result['fm:html'])
        tokens = parser.tokens

        in_inboxmarkup = False
        for token in tokens:
            if token[0] == web.STARTTAG and token[1] == 'script':
                attrs = dict(token[2])
                if attrs.get('data-scope') == 'inboxmarkup' and attrs.get('type') == 'application/json':
                    in_inboxmarkup = True
            elif in_inboxmarkup:
                if token[0] == web.ENDTAG:
                    in_inboxmarkup = False
                elif token[0] == web.DATA:
                    result['email:inboxmarkup'] = json.loads(html.unescape(token[1]))

    if result.get('email:inboxmarkup'):
        if result['email:inboxmarkup'].get('entity') and result['email:inboxmarkup']['entity'].get('avatar_image_url'):
            result['fm:avatar'] = result['email:inboxmarkup']['entity']['avatar_image_url']

    return result

def format_email(raw_mail):
    msg = email.message_from_bytes(raw_mail, policy=email.policy.default)

    return format_message(msg, True)

def process_mbox(line, state):
    import mailbox

    filename = line.split(':', 1)[1]

    prev_last_seen = state.get(('mbox', filename, 'last_seen'))
    new_last_seen = None

    prev_last_ofs, prev_last_from = state.get(('mbox', filename, 'last_from'), (None, None))
    new_last_ofs = new_last_from = None

    result = {}
    entries = result['fm:entries'] = []

    data = []
    use = False
    with open(filename, 'rb') as f:
        # try skipping to the last seen email
        if prev_last_ofs:
            f.seek(prev_last_ofs)
            fr = f.read(len(prev_last_from))
            if prev_last_from != fr:
                f.seek(0)

        for line in f:
            if line.startswith(b'From '):
                new_last_from = line
                new_last_ofs = f.tell() - len(line)

                if use:
                    entries.append(format_email(b''.join(data)))
                    data = []

                sortdate = email.utils.parsedate_to_datetime(
                    line.decode('ascii').split(' ', 2)[2]).isoformat()

                if prev_last_seen and prev_last_seen >= sortdate:
                    use = False
                else:
                    use = True

                if not new_last_seen or sortdate > new_last_seen:
                    new_last_seen = sortdate
                
            elif use:
                data.append(line)

    if use:
        entries.append(format_email(b''.join(data)))

    if new_last_seen:
        state[('mbox', filename, 'last_seen')] = new_last_seen

    if new_last_ofs:
        state[('mbox', filename, 'last_from')] = (new_last_ofs, new_last_from)

    return core.JSON, result

