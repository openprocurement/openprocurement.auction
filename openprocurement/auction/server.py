from flask_oauthlib.client import OAuth
from flask import Flask, request, jsonify, url_for, session, abort, redirect
import os
from urlparse import urljoin

from gevent.pywsgi import WSGIServer
from datetime import datetime
from pytz import timezone
from openprocurement.auction.forms import BidsForm
from openprocurement.auction.utils import get_lisener, create_mapping
from openprocurement.auction.event_source import (
    sse, send_event, send_event_to_client, remove_client,
    push_timestamps_events, check_clients
)

from pytz import timezone as tz
from gevent import spawn


app = Flask(__name__, static_url_path='', template_folder='static')
app.auction_bidders = {}
app.register_blueprint(sse)
app.secret_key = os.urandom(24)


@app.route('/login')
def login():
    if 'remote_oauth' in session:
        resp = app.remote_oauth.get('me')
        if resp.status == 200:
            response = redirect(
                urljoin(request.headers['X-Forwarded-Path'], '.').rstrip('/')
            )
    if 'bidder_id' in request.args and 'hash' in request.args:
        next_url = request.args.get('next') or request.referrer or None
        if 'X-Forwarded-Path' in request.headers:
            callback_url = urljoin(
                request.headers['X-Forwarded-Path'],
                'authorized'
            )
        else:
            callback_url = url_for('authorized', next=next_url, _external=True)
        response = app.remote_oauth.authorize(
            callback=callback_url,
            bidder_id=request.args['bidder_id'],
            hash=request.args['hash']
        )
        if 'return_url' in request.args:
            session['return_url'] = request.args['return_url']

        return response
    return abort(401)


@app.route('/logout')
def logout():
    if 'remote_oauth' in session and 'client_id' in session:
        resp = app.remote_oauth.get('me')
        if resp.status == 200:
            remove_client(resp.data['bidder_id'], session['client_id'])
            send_event(
                resp.data['bidder_id'],
                app.auction_bidders[resp.data['bidder_id']]["clients"],
                "ClientsList"
            )
    session.clear()
    return redirect(
        urljoin(request.headers['X-Forwarded-Path'], '.').rstrip('/')
    )


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
    abort(401)


@app.route('/kickclient', methods=['POST'])
def kickclient():
    if 'remote_oauth' in session and 'client_id' in session:
        auction = app.config['auction']
        with auction.bids_actions:
            data = request.json
            resp = app.remote_oauth.get('me')
            if resp.status == 200:

                data['bidder_id'] = resp.data['bidder_id']
                if 'client_id' in data:
                    send_event_to_client(
                        data['bidder_id'], data['client_id'], {
                            "from": session['client_id']
                        }, "KickClient"
                    )
                    return jsonify({"status": "ok"})
    abort(401)


@app.route('/authorized')
def authorized():
    if not('error' in request.args and request.args['error'] == 'access_denied'):
        resp = app.remote_oauth.authorized_response()
        if resp is None:
            return abort(401, 'Access denied: reason=%s error=%s' % (
                request.args['error_reason'],
                request.args['error_description']
            ))
        session['remote_oauth'] = (resp['access_token'], '')
        session['client_id'] = os.urandom(16).encode('hex')
    return redirect(
        urljoin(request.headers['X-Forwarded-Path'], '.').rstrip('/')
    )


def run_server(auction, mapping_expire_time, logger, timezone='Europe/Kiev'):
    app.config.update(auction.worker_defaults)
    app.log = logger
    app.config['auction'] = auction
    app.config['timezone'] = tz(timezone)
    app.config['SESSION_COOKIE_PATH'] = '/tenders/{}'.format(auction.auction_doc_id)
    app.oauth = OAuth(app)
    app.remote_oauth = app.oauth.remote_app(
        'remote',
        consumer_key=app.config['OAUTH_CLIENT_ID'],
        consumer_secret=app.config['OAUTH_CLIENT_SECRET'],
        request_token_params={'scope': 'email'},
        base_url=app.config['OAUTH_BASE_URL'],
        request_token_url=app.config['OAUTH_REQUEST_TOKEN_URL'],
        access_token_url=app.config['OAUTH_ACCESS_TOKEN_URL'],
        authorize_url=app.config['OAUTH_AUTHORIZE_URL']
    )

    @app.remote_oauth.tokengetter
    def get_oauth_token():
        return session.get('remote_oauth')
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = 'true'

    # Start server on unused port
    lisener = get_lisener(auction.worker_defaults["STARTS_PORT"])
    logger.info("Start server on {0}:{1}".format(*lisener.getsockname()))
    server = WSGIServer(lisener, app)
    server.start()
    # Set mapping
    mapping_value = "http://{0}:{1}/".format(*lisener.getsockname())
    create_mapping(auction.worker_defaults["REDIS_URL"],
                   auction.auction_doc_id,
                   mapping_value)
    logger.info("Server mapping: {} -> {}".format(
        auction.auction_doc_id,
        mapping_value,
        mapping_expire_time
    ))

    # Spawn events functionality
    spawn(push_timestamps_events, app,)
    spawn(check_clients, app, )
    return server
