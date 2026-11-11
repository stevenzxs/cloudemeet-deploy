"""Actual BOSH SASL/bind/MUC host and guest assertions, injected strict TLS transport."""
import json
import secrets
import urllib.parse
import xml.etree.ElementTree as ET


class Session:
    def __init__(self, room, token=None):
        self.room = room
        self.path = '/http-bind?' + urllib.parse.urlencode({'room': room, **({'token': token} if token else {})})
        self.rid, self.sid = 400000, None
        initial = self.send('', "to='meet.jitsi' wait='2' hold='1' ver='1.6' xmlns:xmpp='urn:xmpp:xbosh' xmpp:version='1.0'")
        self.sid = initial.attrib['sid']
        auth = self.send("<auth xmlns='urn:ietf:params:xml:ns:xmpp-sasl' mechanism='ANONYMOUS'/>")
        if auth.find('{urn:ietf:params:xml:ns:xmpp-sasl}success') is None:
            raise RuntimeError('Product SASL rejected')
        self.send('', "to='meet.jitsi' xmlns:xmpp='urn:xmpp:xbosh' xmpp:restart='true'")
        bound = self.send("<iq type='set' id='bind1' xmlns='jabber:client'><bind xmlns='urn:ietf:params:xml:ns:xmpp-bind'><resource>probe</resource></bind></iq>")
        if bound.find('.//{urn:ietf:params:xml:ns:xmpp-bind}jid') is None:
            raise RuntimeError('Product resource bind failed')
        self.nick = secrets.token_hex(6)

    def send(self, payload, extra=''):
        self.rid += 1
        sid = " sid='" + self.sid + "'" if self.sid else ''
        return ET.fromstring(request(self.path,
            f"<body xmlns='http://jabber.org/protocol/httpbind' rid='{self.rid}'{sid} {extra}>{payload}</body>"))

    def join(self, expected):
        node = self.send(f"<presence xmlns='jabber:client' to='{self.room}@muc.meet.jitsi/{self.nick}'><x xmlns='http://jabber.org/protocol/muc'/></presence>")
        for _ in range(10):
            for presence in node.findall('{jabber:client}presence'):
                if presence.attrib.get('type') == 'error':
                    raise RuntimeError('Product MUC join rejected')
                if not presence.attrib.get('from', '').endswith('/' + self.nick):
                    continue
                item = presence.find('.//{http://jabber.org/protocol/muc#user}item')
                if item is not None:
                    if expected == 'owner' and item.get('affiliation') == 'owner' and item.get('role') == 'moderator':
                        return
                    if expected == 'participant' and item.get('role') == 'participant' and item.get('affiliation') not in ('owner', 'admin'):
                        return
            node = self.send('')
        raise RuntimeError('Expected product role not observed: ' + expected)


def verify_roles(checks):
    room = str(secrets.randbelow(900000000) + 100000000)
    hostkey = secrets.token_hex(24)
    route = '/mapi/open/desktop/meetings'
    sessions = []
    try:
        request(route, json.dumps({'roomName': room, 'subject': 'CI product role probe',
            'hostKey': hostkey, 'creatorId': 'ci-role'}), 'application/json')
        issued = json.loads(request(route + '/' + room + '/host-token',
            json.dumps({'hostKey': hostkey, 'displayName': 'CI host'}), 'application/json'))
        host = Session(room, issued['token'])
        sessions.append(host)
        focus = host.send(f"<iq xmlns='jabber:client' to='focus.meet.jitsi' type='set' id='focus1'><conference xmlns='http://jitsi.org/protocol/focus' room='{room}@muc.meet.jitsi' machine-uid='{secrets.token_hex(16)}'/></iq>")
        if focus.find(".//{jabber:client}iq[@type='error']") is not None:
            raise RuntimeError('Product focus conference rejected')
        host.join('owner')
        guest = Session(room)
        sessions.append(guest)
        guest.join('participant')
        checks.append('real API JWT host OWNER/moderator and guest PARTICIPANT')
    finally:
        for session in reversed(sessions):
            try:
                session.send('', "type='terminate'")
            except Exception:
                pass
