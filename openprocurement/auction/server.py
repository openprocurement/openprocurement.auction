from flask_oauthlib.client import OAuth
from flask import Flask, request, jsonify, url_for, session, abort, redirect
import os
from urlparse import urljoin
import iso8601
from dateutil.tz import tzlocal

from gevent.pywsgi import WSGIServer, WSGIHandler
from gevent import socket
import errno
from datetime import datetime, timedelta
from pytz import timezone
from openprocurement.auction.forms import BidsForm
from openprocurement.auction.utils import get_lisener, create_mapping, prepare_extra_journal_fields
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

INVALIDATE_GRANT = timedelta(0, 230)


class _LoggerStream(object):
    """
    Logging workaround for Gevent PyWSGI Server
    """
    def __init__(self, logger):
        super(_LoggerStream, self).__init__()
        self.logger = logger

    def write(self, msg, **kw):
        self.logger.info(msg, **kw)


class AuctionsWSGIHandler(WSGIHandler):

    def run_application(self):
        try:
            return super(AuctionsWSGIHandler, self).run_application()
        except socket.error as ex:
            # Broken pipe, connection reset by peer
            if ex.args[0] in (errno.EPIPE, errno.ECONNRESET):
                self.close_connection = True
            else:
                raise ex

    def log_request(self):
        log = self.server.log
        if log:
            extra = prepare_extra_journal_fields(self.headers)
            extra['JOURNAL_REMOTE_ADDR'] = ','.join(
                [self.environ.get('HTTP_X_FORWARDED_FOR', ''),
                 self.environ.get('HTTP_X_REAL_IP', '')]
            )
            extra['JOURNAL_USER_AGENT'] = self.environ.get('HTTP_USER_AGENT', '')

            log.write(self.format_request(), extra=extra)


@app.route('/login')
def login():
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
        session['login_bidder_id'] = request.args['bidder_id']
        session['login_hash'] = request.args['hash']
        session['login_callback'] = callback_url
        app.logger.debug("Session: {}".format(repr(session)))
        return response
    return abort(401)


@app.route('/authorized')
def authorized():
    if not('error' in request.args and request.args['error'] == 'access_denied'):
        resp = app.remote_oauth.authorized_response()
        if resp is None or hasattr(resp, 'data'):
            app.logger.info("Error Response from Oauth: {}".format(resp))
            return abort(403, 'Access denied')
        app.logger.info("Get response from Oauth: {}".format(repr(resp)))
        session['remote_oauth'] = (resp['access_token'], '')
        session['client_id'] = os.urandom(16).encode('hex')
    app.logger.debug("Session: {}".format(repr(session)))
    return redirect(
        urljoin(request.headers['X-Forwarded-Path'], '.').rstrip('/')
    )


@app.route('/relogin')
def relogin():
    if (all([key in session
             for key in ['login_callback', 'login_bidder_id', 'login_hash']])):
        if 'amount' in request.args:
            session['amount'] = request.args['amount']
        app.logger.debug("Session: {}".format(repr(session)))
        return app.remote_oauth.authorize(
            callback=session['login_callback'],
            bidder_id=session['login_bidder_id'],
            hash=session['login_hash'],
            auto_allow='1'
        )
    return redirect(
        urljoin(request.headers['X-Forwarded-Path'], '.').rstrip('/')
    )


@app.route('/check_authorization', methods=['POST'])
def check_authorization():
    if 'remote_oauth' in session and 'client_id' in session:
        resp = app.remote_oauth.get('me')
        if resp.status == 200:
            grant_timeout = iso8601.parse_date(resp.data[u'expires']) - datetime.now(tzlocal())
            if grant_timeout > INVALIDATE_GRANT:
                app.logger.info("Bidder {} with client_id {} pass check_authorization".format(
                                resp.data['bidder_id'], session['client_id'],
                                ), extra=prepare_extra_journal_fields(request.headers))
                return jsonify({'status': 'ok'})
            else:
                app.logger.info(
                    "Grant will end in a short time. Activate re-login functionality",
                    extra=prepare_extra_journal_fields(request.headers)
                )
        else:
            app.logger.warning("Client_id {} didn't passed check_authorization".format(session['client_id']),
                               extra=prepare_extra_journal_fields(request.headers))
    abort(401)


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
def post_bid():
    auction = app.config['auction']
    if 'remote_oauth' in session and 'client_id' in session:
        resp = app.remote_oauth.get('me')
        if resp.status == 200 and resp.data['bidder_id'] == request.json['bidder_id']:
            with auction.bids_actions:
                form = BidsForm.from_json(request.json)
                form.document = auction.db.get(auction.auction_doc_id)
                current_time = datetime.now(timezone('Europe/Kiev'))
                if form.validate():
                    # write data
                    auction.add_bid(form.document['current_stage'],
                                    {'amount': request.json['bid'],
                                     'bidder_id': request.json['bidder_id'],
                                     'time': current_time.isoformat()})
                    if request.json['bid'] == -1:
                        app.logger.info("Bidder {} with client_id {} canceled bids in stage {} in {}".format(
                            request.json['bidder_id'], session['client_id'],
                            form.document['current_stage'], current_time.isoformat()
                        ), extra=prepare_extra_journal_fields(request.headers))
                    else:
                        app.logger.info("Bidder {} with client_id {} placed bid {} in {}".format(
                            request.json['bidder_id'], session['client_id'],
                            request.json['bid'], current_time.isoformat()
                        ), extra=prepare_extra_journal_fields(request.headers))
                    response = {'status': 'ok', 'data': request.json}
                else:
                    response = {'status': 'failed', 'errors': form.errors}
                    app.logger.info("Bidder {} with client_id {} wants place bid {} in {} with errors {}".format(
                        request.json['bidder_id'], session['client_id'],
                        request.json['bid'], current_time.isoformat(),
                        repr(form.errors)
                    ), extra=prepare_extra_journal_fields(request.headers))
                return jsonify(response)
        else:
            app.logger.warning("Client with client id: {} and bidder_id {} wants post bid but response status from Oauth is {}".format(
                session.get('client_id', ''), request.json.get('bidder_id', ''), resp.status
            ))
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


def run_server(auction, mapping_expire_time, logger, timezone='Europe/Kiev'):
    app.config.update(auction.worker_defaults)
    # Replace Flask custom logger
    app.logger_name = logger.name
    app._logger = logger
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
    app.logger.info(
        "Start server on {0}:{1}".format(*lisener.getsockname()),
        extra={"JOURNAL_REQUEST_ID": auction.request_id}
    )
    server = WSGIServer(lisener, app,
                        log=_LoggerStream(logger),
                        handler_class=AuctionsWSGIHandler)
    server.start()
    # Set mapping
    mapping_value = "http://{0}:{1}/".format(*lisener.getsockname())
    create_mapping(auction.worker_defaults["REDIS_URL"],
                   auction.auction_doc_id,
                   mapping_value)
    app.logger.info("Server mapping: {} -> {}".format(
        auction.auction_doc_id,
        mapping_value,
        mapping_expire_time
    ), extra={"JOURNAL_REQUEST_ID": auction.request_id})

    # Spawn events functionality
    spawn(push_timestamps_events, app,)
    spawn(check_clients, app, )
    return server
