from flask import Flask, request, jsonify
from gevent.pywsgi import WSGIServer
from datetime import datetime
from pytz import timezone
from openprocurement.auction.forms import BidsForm
from openprocurement.auction.event_source import sse, send_event
from pytz import timezone as tz
from gevent import spawn, sleep


app = Flask(__name__, static_url_path='', template_folder='static')
app.auction_bidders = {}
app.register_blueprint(sse)


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
                        del app.auction_bidders[bidder_id]["channels"][client]
                        del app.auction_bidders[bidder_id]["clients"][client]
                    send_event(
                        bidder_id,
                        app.auction_bidders[bidder_id]["clients"],
                        "ClientsList"
                    )


def run_server(auction, timezone='Europe/Kiev'):
    app.config['auction'] = auction
    app.config['timezone'] = tz(timezone)
    server = WSGIServer((auction.host, auction.port, ), app)
    server.start()
    spawn(push_timestamps_events, app,)
    spawn(check_clients, app, )
    return server
