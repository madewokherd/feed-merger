import base64
import datetime
import email.policy
import html

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

    return result

def format_email(raw_mail):
    msg = email.message_from_bytes(raw_mail, policy=email.policy.default)

    return format_message(msg, True)

