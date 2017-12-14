import logging

from sse import Sse as PySse
from flask import (
    json, current_app, Blueprint,
    request, session, Response)
from flask import jsonify, abort
from gevent.queue import Queue
from gevent import spawn, sleep
from datetime import datetime

from openprocurement.auction.utils import prepare_extra_journal_fields, get_bidder_id


LOGGER = logging.getLogger(__name__)
CHUNK = ' ' * 2048 + '\n'


def sse_timeout(queue, sleep_seconds):
    sleep(sleep_seconds)
    if queue:
        queue.put({"event": "StopSSE"})


class SseStream(object):
    def __init__(self, queue, bidder_id=None, client_id=None, timeout=None):
        self.queue = queue
        self.client_id = client_id
        self.bidder_id = bidder_id
        if timeout:
            self.sse = PySse(default_retry=0)
            spawn(sse_timeout, queue, timeout)
        else:
            self.sse = PySse(default_retry=2000)

    def __iter__(self):
        self.sse = PySse()
        # TODO: https://app.asana.com/0/17412748309135/22939294056733
        yield CHUNK
        for data in self.sse:
            yield data.encode('u8')

        while True:
            message = self.queue.get()
            if message["event"] == "StopSSE":
                return
            LOGGER.debug(' '.join([
                'Event Message to bidder:', str(self.bidder_id), ' Client:',
                str(self.client_id), 'MSG:', str(repr(message))
            ]))
            self.sse.add_message(message['event'], json.dumps(message['data']))
            for data in self.sse:
                yield data.encode('u8')


sse = Blueprint('sse', __name__)


@sse.route("/set_sse_timeout", methods=['POST'])
def set_sse_timeout():
    current_app.logger.info(
        'Handle set_sse_timeout request with session {}'.format(repr(dict(session))),
        extra=prepare_extra_journal_fields(request.headers)
    )
    if 'remote_oauth' in session and 'client_id' in session:
        bidder_data = get_bidder_id(current_app, session)
        if bidder_data:
            current_app.logger.info("Bidder {} with client_id {} set sse_timeout".format(
                                    bidder_data['bidder_id'], session['client_id'],
                                    ), extra=prepare_extra_journal_fields(request.headers))
            bidder = bidder_data['bidder_id']
            if 'timeout' in request.json:
                session["sse_timeout"] = int(request.json['timeout'])
                send_event_to_client(
                    bidder, session['client_id'], '',
                    event='StopSSE'
                )
                return jsonify({'timeout': session["sse_timeout"]})

    return abort(401)


@sse.route("/event_source")
def event_source():
    current_app.logger.debug(
        'Handle event_source request with session {}'.format(repr(dict(session))),
        extra=prepare_extra_journal_fields(request.headers)
    )
    if 'remote_oauth' in session and 'client_id' in session:
        bidder_data = get_bidder_id(current_app, session)
        if bidder_data:
            valid_bidder = False
            client_hash = session['client_id']
            bidder = bidder_data['bidder_id']
            for bidder_info in current_app.config['auction'].bidders_data:
                if bidder_info['id'] == bidder:
                    valid_bidder = True
                    break
            if valid_bidder:
                if bidder not in current_app.auction_bidders:
                    current_app.auction_bidders[bidder] = {
                        "clients": {},
                        "channels": {}
                    }

                if client_hash not in current_app.auction_bidders[bidder]:
                    real_ip = request.environ.get('HTTP_X_REAL_IP', '')
                    if real_ip.startswith('172.'):
                        real_ip = ''
                    current_app.auction_bidders[bidder]["clients"][client_hash] = {
                        'ip': ','.join(
                            [request.headers.get('X-Forwarded-For', ''), real_ip]
                        ),
                        'User-Agent': request.headers.get('User-Agent'),
                    }
                    current_app.auction_bidders[bidder]["channels"][client_hash] = Queue()

                current_app.logger.info(
                    'Send identification for bidder: {} with client_hash {}'.format(bidder, client_hash),
                    extra=prepare_extra_journal_fields(request.headers)
                )
                identification_data = {"bidder_id": bidder,
                                       "client_id": client_hash,
                                       "return_url": session.get('return_url', '')}
                if current_app.config['auction'].features:
                    identification_data["coeficient"] = str(current_app.config['auction'].bidders_coeficient[bidder])

                send_event_to_client(bidder, client_hash, identification_data,
                                     "Identification")
                if 'amount' in session:
                    send_event_to_client(bidder, client_hash,
                                         {"last_amount": session['amount']},
                                         "RestoreBidAmount")
                    current_app.logger.debug('Send RestoreBidAmount')
                    del session['amount']

                if not session.get("sse_timeout", 0):
                    current_app.logger.debug('Send ClientsList')
                    send_event(
                        bidder,
                        current_app.auction_bidders[bidder]["clients"],
                        "ClientsList"
                    )
                response = Response(
                    SseStream(
                        current_app.auction_bidders[bidder]["channels"][client_hash],
                        bidder_id=bidder,
                        client_id=client_hash,
                        timeout=session.get("sse_timeout", 0)
                    ),
                    direct_passthrough=True,
                    mimetype='text/event-stream',
                    content_type='text/event-stream'
                )
                response.headers['Cache-Control'] = 'no-cache'
                response.headers['X-Accel-Buffering'] = 'no'
                return response
            else:
                current_app.logger.info(
                    'Not valid bidder: bidder_id {} with client_hash {}'.format(bidder, client_hash),
                    extra=prepare_extra_journal_fields(request.headers)
                )

    current_app.logger.debug(
        'Disable event_source for unauthorized user.',
        extra=prepare_extra_journal_fields(request.headers)
    )
    events_close = PySse()
    events_close.add_message("Close", "Disable")
    response = Response(
        iter([bytearray(''.join([x for x in events_close]), 'UTF-8')]),
        direct_passthrough=True,
        mimetype='text/event-stream',
        content_type='text/event-stream'
    )
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response


def send_event_to_client(bidder, client, data, event=""):
    if bidder in current_app.auction_bidders and client in current_app.auction_bidders[bidder]["channels"]:
        return current_app.auction_bidders[bidder]["channels"][client].put({
            "event": event,
            "data": data
        })


def send_event(bidder, data, event=""):
    for client in current_app.auction_bidders[bidder]["channels"]:
        send_event_to_client(bidder, client, data, event)
    return True


def remove_client(bidder_id, client):
    if bidder_id in current_app.auction_bidders:
        if client in current_app.auction_bidders[bidder_id]["channels"]:
            del current_app.auction_bidders[bidder_id]["channels"][client]
        if client in current_app.auction_bidders[bidder_id]["clients"]:
            del current_app.auction_bidders[bidder_id]["clients"][client]


def push_timestamps_events(app):
    with app.app_context():
        while True:
            sleep(5)
            time = datetime.now(app.config['timezone']).isoformat()
            for bidder_id in app.auction_bidders:
                send_event(bidder_id, {"time": time}, "Tick")


def check_clients(app):
    with app.app_context():
        while True:
            sleep(30)

            for bidder_id in app.auction_bidders:
                removed_clients = []
                for client in app.auction_bidders[bidder_id]["channels"]:
                    if app.auction_bidders[bidder_id]["channels"][client].qsize() > 3:
                        removed_clients.append(client)
                if removed_clients:
                    for client in removed_clients:
                        remove_client(bidder_id, client)
                    send_event(
                        bidder_id,
                        app.auction_bidders[bidder_id]["clients"],
                        "ClientsList"
                    )
