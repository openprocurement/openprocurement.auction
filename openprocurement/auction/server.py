from flask import Flask, render_template, request, jsonify

app = Flask(__name__, static_url_path='', template_folder='static')

from gevent.wsgi import WSGIServer
from datetime import datetime
from pytz import timezone

from openprocurement.auction.forms import BidsForm


@app.route('/')
def index():
    return render_template(
        'index.html',
        db_url=getattr(app.config.get('auction', None), 'database_url', 'http://localhost:9000/auction'),
        auction_doc_id=getattr(app.config.get('auction', None), 'auction_doc_id', 'ua1')
    )


@app.route('/get_corrent_server_time')
def current_server_time():
    return datetime.now(timezone('Europe/Kiev')).isoformat()


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


def run_server(auction):
    app.config['auction'] = auction
    server = WSGIServer((auction.host, auction.port, ), app)
    server.start()
    return server
