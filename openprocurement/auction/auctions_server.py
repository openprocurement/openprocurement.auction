from gevent import monkey

monkey.patch_all()

import time
from collections import deque
from Cookie import SimpleCookie
from couchdb import Server, Session
from datetime import datetime
from design import sync_design, endDate_view
from flask import Flask, render_template, request, abort, url_for, redirect, Response
from flask.ext.assets import Environment, Bundle
from flask_redis import Redis
from http_parser.util import IOrderedDict
from json import dumps, loads
from memoize import Memoizer
from pytz import timezone as tz
from restkit.conn import Connection
from restkit.contrib.wsgi_proxy import HostProxy
from socketpool import ConnectionPool
from sse import Sse as PySse
from urlparse import urlparse, urljoin
from werkzeug.exceptions import NotFound

from .utils import StreamWrapper, unsuported_browser
from systemd.journal import send

def start_response_decorated(start_response_decorated):
    def inner(status, headers):
        headers_obj = IOrderedDict(headers)
        if 'Set-Cookie' in headers_obj and ', ' in headers_obj['Set-Cookie']:
            cookie = SimpleCookie()
            cookie.load(headers_obj['Set-Cookie'])
            del headers_obj['Set-Cookie']
            headers_list = headers_obj.items()
            for key in ("auctions_loggedin", "auction_session"):
                if key in cookie:
                    headers_list += [
                        ('Set-Cookie', cookie[key].output(header="").lstrip().rstrip(','))
                    ]
            headers = headers_list
        return start_response_decorated(status, headers)
    return inner


class StreamProxy(HostProxy):
    def __init__(self, uri, event_sources_pool,
                 auction_doc_id="",
                 event_source_connection_limit=1000,
                 **kwargs):
        super(StreamProxy, self).__init__(uri, **kwargs)
        self.auction_doc_id = auction_doc_id
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
            response = super(StreamProxy, self).__call__(
                environ, start_response_decorated(start_response)
            )
            stream_response = StreamWrapper(response.resp, response.connection)
            if 'event_source' in stream_response.resp.request.url:
                self.add_event_source(stream_response)
            return stream_response
        except Exception, e:
            auctions_server.logger.warning(
                "Error on request to {} with msg {}".format(request.url, e)
            )
            auctions_server.proxy_mappings.expire(str(self.auction_doc_id), 0)
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
js = Bundle("vendor/pouchdb/dist/pouchdb.js",
            "vendor/event-source-polyfill/eventsource.min.js",
            "vendor/angular-cookies/angular-cookies.min.js",
            "vendor/angular-ellipses/src/truncate.js",
            "vendor/angular-timer/dist/angular-timer.min.js",
            "vendor/angular-translate/angular-translate.min.js",
            "vendor/angular-translate-storage-cookie/angular-translate-storage-cookie.min.js",
            "vendor/angular-translate-storage-local/angular-translate-storage-local.min.js",
            "vendor/angular-growl-2/build/angular-growl.js",
            "vendor/angular-gtm-logger/angular-gtm-logger.min.js",
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
    url_obj = urlparse(request.url)
    request_base = u'//' + url_obj.netloc + url_obj.path + u'/'
    return render_template(
        'tender.html',
        db_url=auctions_server.config.get('EXT_COUCH_DB'),
        auction_doc_id=auction_doc_id,
        unsupported_browser=unsuported_browser(request),
        request_base=request_base
    )


@auctions_server.route('/')
def auction_list_index():
    return render_template(
        'list.html',
        documents=reversed(
            [auction.doc
             for auction in endDate_view(auctions_server.db,
                                         startkey=time.time() * 1000,
                                         include_docs=True)
             ])
    )

@auctions_server.route('/log', methods=['POST'])
def log():

    try:
        data = loads(request.data)
        if "MESSAGE" in data:
            msg = data.get("MESSAGE")
            del data["MESSAGE"]
        else:
            msg = ""
        data['REMOTE_ADDR'] = ','.join(
            [ip
             for ip in request.environ.get('HTTP_X_FORWARDED_FOR', '').split(',')
             if not ip.startswith('172.')]
        )
        data["SYSLOG_IDENTIFIER"] = "AUCTION_CLIENT"
        send(msg, **data)
        return Response('ok')
    except:
        return Response('error')



@auctions_server.route('/health')
def health():
    data = auctions_server.couch_server.tasks()
    response = Response(dumps(data))
    if not(data and data[0]['progress'] > 90):
        response.status_code = 503
    return response


@auctions_server.route('/archive')
def archive_auction_list_index():
    offset = int(request.args.get('offset', default=time.time() * 1000))
    startkey_docid = request.args.get('startid', default=None)
    documents=[auction
               for auction in endDate_view(auctions_server.db,
                                               startkey=offset,
                                               startkey_docid=startkey_docid,
                                               limit=101,
                                               descending=True,
                                               include_docs=True)
                   ]
    if len(documents)>100:
        offset, startid = documents[100].key, documents[100].id
    else:
        offset, startid = False, False
    return render_template(
        'archive.html',
        documents=documents[:-1],
        offset=offset,
        startid=startid
    )


@auctions_server.route('/tenders/<auction_doc_id>/<path:path>',
                       methods=['GET', 'POST'])
def auctions_proxy(auction_doc_id, path):
    auctions_server.logger.debug('Auction_doc_id: {}'.format(auction_doc_id))
    proxy_path = auctions_server.proxy_mappings.get(
        str(auction_doc_id),
        auctions_server.redis.get,
        (str(auction_doc_id), ), max_age=60
    )
    auctions_server.logger.debug('Proxy path: {}'.format(proxy_path))
    if proxy_path:
        request.environ['PATH_INFO'] = '/' + path
        auctions_server.logger.debug('Start proxy to path: {}'.format(path))
        return StreamProxy(
            proxy_path,
            auction_doc_id=str(auction_doc_id),
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
    """USED FOR DEBUG ONLY"""
    return StreamProxy(
        auctions_server.config['PROXY_COUCH_URL'],
        auctions_server.event_sources_pool,
        pool=auctions_server.proxy_connection_pool,
        backend="gevent"
    )


def auth_couch_server_proxy(path):
    """USED FOR DEBUG ONLY"""
    return StreamProxy(
        auctions_server.config['PROXY_COUCH_URL'],
        auctions_server.event_sources_pool,
        pool=auctions_server.proxy_connection_pool,
        backend="gevent"
    )


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
    auctions_server.proxy_mappings = Memoizer({})
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

    auctions_server.add_url_rule(
        '/' + auctions_db + '_secured/<path:path>',
        'auth_couch_server_proxy',
        auth_couch_server_proxy,
        methods=['GET'])
    auctions_server.add_url_rule(
        '/' + auctions_db + '_secured/',
        'auth_couch_server_proxy',
        auth_couch_server_proxy,
        methods=['GET'], defaults={'path': ''})

    auctions_server.config['INT_COUCH_URL'] = internal_couch_url
    auctions_server.config['PROXY_COUCH_URL'] = proxy_internal_couch_url
    auctions_server.config['COUCH_DB'] = auctions_db
    auctions_server.config['TIMEZONE'] = tz(timezone)
    auctions_server.redis = Redis(auctions_server)
    auctions_server.couch_server = Server(
        auctions_server.config.get('INT_COUCH_URL'),
        session=Session(retry_delays=range(10))
    )
    if auctions_server.config['COUCH_DB'] not in auctions_server.couch_server:
        auctions_server.couch_server.create(auctions_server.config['COUCH_DB'])

    auctions_server.db = auctions_server.couch_server[auctions_server.config['COUCH_DB']]
    auctions_server.config['HASH_SECRET_KEY'] = hash_secret_key
    sync_design(auctions_server.db)
    auctions_server.config['ASSETS_DEBUG'] = True if debug else False
    assets.auto_build = True if auto_build else False
    return auctions_server
