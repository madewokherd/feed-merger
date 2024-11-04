import datetime
import email.policy

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
        body = msg.get_body()

        if body:
            body_type = body.get_content_type()
            if body_type == 'text/html':
                result['fm:html'] = body.get_content()
            elif body_type == 'text/plain':
                result['fm:text'] = body.get_content()
            else:
                print(f"Unknown body content type {body_type}")

        # TODO: attachments - use a tag with href as a data: url and download="filename"

    return result

def format_email(raw_mail):
    msg = email.message_from_bytes(raw_mail, policy=email.policy.default)

    return format_message(msg, True)

