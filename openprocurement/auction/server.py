from flask import Flask, request, jsonify, Response, abort
from gevent.wsgi import WSGIServer
from datetime import datetime
from pytz import timezone
from openprocurement.auction.forms import BidsForm
from gevent.queue import Queue
from .utils import prepare_sse_msg
import json


app = Flask(__name__, static_url_path='', template_folder='static')
app.auction_bidders = {}


def event_sub(bidder_id, hash_id):
    while True:
        msg = app.auction_bidders[bidder_id][hash_id].get()
        yield prepare_sse_msg('new_user', json.dumps(msg))


@app.route('/postbid', methods=['POST'])
def postBid():
    auction = app.config['auction']
    with auction.bids_actions:
        form = BidsForm.from_json(request.json)
        form.document = auction.db.get(auction.auction_doc_id)
        if form.validate():
            # write data
            current_time = datetime.now(timezone('Europe/Kiev'))
            auction.add_bid(form.document['current_stage'],
                            {'amount': request.json['bid'],
                             'bidder_id': request.json['bidder_id'],
                             'time': current_time.isoformat()})
            response = {'status': 'ok', 'data': request.json}
        else:
            response = {'status': 'failed', 'errors': form.errors}
        return jsonify(response)


@app.route("/event_source")
def event_source():
    if request.args.get('hash') and request.args.get('bidder_id'):
        if request.args.get('bidder_id') not in app.auction_bidders:
            app.auction_bidders[request.args.get('bidder_id')] = {}
        if request.args.get('hash') not in app.auction_bidders[request.args.get('bidder_id')]:
            app.auction_bidders[request.args.get('bidder_id')][request.args.get('hash')] = Queue()
        new_client = {'ip': request.headers.get('X-Forwarded-For'),
                      'User-Agent': request.headers.get('User-Agent'),
                      'client_hash': request.args.get('hash')}
        for keys in app.auction_bidders[request.args.get('bidder_id')]:
            if keys != request.args.get('hash'):
                app.auction_bidders[request.args.get('bidder_id')][keys].put(new_client)

        return Response(event_sub(request.args.get('bidder_id'), request.args.get('hash')), mimetype="text/event-stream")
    else:
        return abort(404)


def run_server(auction):
    app.config['auction'] = auction
    server = WSGIServer((auction.host, auction.port, ), app)
    server.start()
    return server
