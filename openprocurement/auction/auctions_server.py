from gevent import monkey
monkey.patch_all()

from datetime import datetime
from design import sync_design, endDate_view
from flask import Flask, render_template, request, abort, url_for, redirect, Response
from flask.ext.assets import Environment, Bundle
from flask_redis import Redis
from paste.proxy import make_proxy
from pytz import timezone as tz
from urlparse import urljoin
import couchdb
import time
from sse import Sse as PySse
from pkg_resources import parse_version
from restkit.contrib.wsgi_proxy import HostProxy
from restkit.conn import Connection
from socketpool import ConnectionPool
from .utils import StreamWrapper
from collections import deque
from werkzeug.exceptions import NotFound


class StreamProxy(HostProxy):

    def __init__(self, uri, event_sources_pool,
                 event_source_connection_limit=1000,
                 **kwargs):
        super(StreamProxy, self).__init__(uri, **kwargs)
        self.event_source_connection_limit = event_source_connection_limit
        self.event_sources = event_sources_pool

    def add_event_source(self, stream_response):
        self.event_sources.append(stream_response)
        while len(self.event_sources) > self.event_source_connection_limit:
            ev_connection = self.event_sources.popleft()
            if not ev_connection._closed:
                ev_connection.close()

    def __call__(self, environ, start_response):
        header_map = {
            'HTTP_HOST': 'X_FORWARDED_SERVER',
            'SCRIPT_NAME': 'X_FORWARDED_SCRIPT_NAME',
            'wsgi.url_scheme': 'X_FORWARDED_SCHEME'
        }
        for key, dest in header_map.items():
            value = environ.get(key)
            if value:
                environ['HTTP_%s' % dest] = value
        environ['HTTP_X-Forwarded-Path'] = request.url
        if 'HTTP_X_FORWARDED_FOR' in environ:
            environ['HTTP_X_FORWARDED_FOR'] = ", ".join(
                [ip
                 for ip in environ['HTTP_X_FORWARDED_FOR'].split(", ")
                 if not ip.startswith("172.")]
            )
        else:
            environ['HTTP_X_FORWARDED_FOR'] = environ['REMOTE_ADDR']
        try:
            response = super(StreamProxy, self).__call__(environ, start_response)
            stream_response = StreamWrapper(response.resp, response.connection)
            if 'event_source' in stream_response.resp.request.url:
                self.add_event_source(stream_response)
            return stream_response
        except Exception, e:
            auctions_server.logger.warning(
                "Error on request to {} with msg {}".format(request.url, e)
            )
            return NotFound()(environ, start_response)

auctions_server = Flask(
    __name__,
    static_url_path='',
    template_folder='templates'
)

################################################################################
assets = Environment(auctions_server)
assets.manifest = "json:manifest.json"


css = Bundle("vendor/angular-growl-2/build/angular-growl.min.css",
             "static/css/starter-template.css",
             filters='cssmin,datauri', output='min/styles_%(version)s.css')
assets.register('all_css', css)
js = Bundle("vendor/event-source-polyfill/eventsource.min.js",
            "vendor/angular-cookies/angular-cookies.min.js",
            "vendor/pouchdb/dist/pouchdb.js",
            "vendor/angular-bootstrap/ui-bootstrap-tpls.min.js",
            "vendor/angular-ellipses/src/truncate.js",
            "vendor/angular-timer/dist/angular-timer.min.js",
            "vendor/angular-translate/angular-translate.min.js",
            "vendor/angular-translate-storage-cookie/angular-translate-storage-cookie.min.js",
            "vendor/angular-translate-storage-local/angular-translate-storage-local.min.js",
            "vendor/angular-growl-2/build/angular-growl.js",
            "static/js/app.js",
            "static/js/utils.js",
            "static/js/translations.js",
            "static/js/controllers.js",
            "vendor/moment/locale/uk.js",
            "vendor/moment/locale/ru.js",
            filters='jsmin', output='min/all_js_%(version)s.js')
assets.register('all_js', js)

################################################################################


@auctions_server.before_request
def before_request():
    auctions_server.logger.debug('Start {0.method}: {0.url}'.format(request))


@auctions_server.after_request
def after_request(response):
    auctions_server.logger.debug(
        'End {1.status_code} : {0.method} : {0.url} '.format(request, response)
    )
    return response


@auctions_server.route('/tenders/<auction_doc_id>')
def auction_url(auction_doc_id):
    unsupported_browser = False
    if request.user_agent.browser == 'msie':
        if parse_version(request.user_agent.version) <= parse_version('9'):
            unsupported_browser = True
        # Add to blacklist IE11
        if parse_version(request.user_agent.version) >= parse_version('11'):
            unsupported_browser = True
    elif request.user_agent.browser == 'opera':
        if 'Opera Mini' in request.user_agent.string:
            unsupported_browser = True
    request_base = request.url + '/'
    if request_base.startswith("https:"):
        request_base = request_base[6:]
    else:
        request_base = request_base[5:]
    return render_template(
        'index.html',
        db_url=auctions_server.config.get('EXT_COUCH_DB'),
        auction_doc_id=auction_doc_id,
        unsupported_browser=unsupported_browser,
        request_base=request_base
    )


@auctions_server.route('/')
def archive_tenders_list_index():
    return render_template(
        'list.html',
        documents=reversed(
            [auction.doc
             for auction in endDate_view(auctions_server.db,
                                         startkey=time.time() * 1000,
                                         include_docs=True)
             ])
    )


@auctions_server.route('/archive')
def auction_list_index():
    return render_template(
        'list.html',
        documents=[auction.doc
                   for auction in endDate_view(auctions_server.db,
                                               endkey=time.time() * 1000,
                                               include_docs=True)
                   ]
    )


@auctions_server.route('/tenders/<auction_doc_id>/<path:path>',
                       methods=['GET', 'POST'])
def auctions_proxy(auction_doc_id, path):
    auctions_server.logger.debug('Auction_doc_id: {}'.format(auction_doc_id))
    proxy_path = auctions_server.redis.get(auction_doc_id)
    auctions_server.logger.debug('Proxy path: {}'.format(proxy_path))
    if proxy_path:
        request.environ['PATH_INFO'] = '/' + path
        auctions_server.logger.debug('Start proxy to path: {}'.format(path))
        return StreamProxy(
            proxy_path,
            event_sources_pool=auctions_server.event_sources_pool,
            event_source_connection_limit=auctions_server.config['event_source_connection_limit'],
            pool=auctions_server.proxy_connection_pool,
            backend="gevent"
        )
    elif path == 'login' and auction_doc_id in auctions_server.db:
        return redirect((
            url_for('auction_url', auction_doc_id=auction_doc_id,
                    wait=1, **request.args)
        ))
    elif path == 'event_source':
        events_close = PySse()
        events_close.add_message("Close", "Disable")
        return Response(
            events_close,
            mimetype='text/event-stream',
            content_type='text/event-stream'
        )
    return abort(404)


@auctions_server.route('/get_current_server_time')
def auctions_server_current_server_time():
    response = Response(datetime.now(auctions_server.config['TIMEZONE']).isoformat())
    response.headers['Cache-Control'] = 'public, max-age=0'
    return response


def couch_server_proxy(path):
    return make_proxy(
        {}, auctions_server.config['PROXY_COUCH_URL'], allowed_request_methods="",
        suppress_http_headers="")


def make_auctions_app(global_conf,
                      redis_url='redis://localhost:7777/0',
                      external_couch_url='http://localhost:5000/auction',
                      internal_couch_url='http://localhost:9000/',
                      proxy_internal_couch_url='http://localhost:9000/',
                      auctions_db='auctions',
                      hash_secret_key='',
                      timezone='Europe/Kiev',
                      preferred_url_scheme='http',
                      debug=False,
                      auto_build=False,
                      event_source_connection_limit=1000
                      ):
    """
    [app:main]
    use = egg:openprocurement.auction#auctions_server
    redis_url = redis://:passwod@localhost:1111/0
    external_couch_url = http://localhost:1111/auction
    internal_couch_url = http://localhost:9011/
    auctions_db = auction
    timezone = Europe/Kiev
    """
    auctions_server.proxy_connection_pool = ConnectionPool(
        factory=Connection, max_size=20, backend="gevent"
    )
    auctions_server.event_sources_pool = deque([])
    auctions_server.config['PREFERRED_URL_SCHEME'] = preferred_url_scheme
    auctions_server.config['REDIS_URL'] = redis_url
    auctions_server.config['event_source_connection_limit'] = int(event_source_connection_limit)
    auctions_server.config['EXT_COUCH_DB'] = urljoin(
        external_couch_url,
        auctions_db
    )
    auctions_server.add_url_rule(
        '/' + auctions_db + '/<path:path>',
        'couch_server_proxy',
        couch_server_proxy,
        methods=['GET'])
    auctions_server.add_url_rule(
        '/' + auctions_db + '/',
        'couch_server_proxy',
        couch_server_proxy,
        methods=['GET'], defaults={'path': ''})
    auctions_server.config['INT_COUCH_URL'] = internal_couch_url
    auctions_server.config['PROXY_COUCH_URL'] = proxy_internal_couch_url
    auctions_server.config['COUCH_DB'] = auctions_db
    auctions_server.config['TIMEZONE'] = tz(timezone)
    auctions_server.redis = Redis(auctions_server)
    auctions_server.db = couchdb.client.Database(
        urljoin(auctions_server.config.get('INT_COUCH_URL'),
                auctions_server.config['COUCH_DB'])
    )
    auctions_server.config['HASH_SECRET_KEY'] = hash_secret_key
    sync_design(auctions_server.db)
    auctions_server.config['ASSETS_DEBUG'] = True if debug else False
    assets.auto_build = True if auto_build else False
    return auctions_server
