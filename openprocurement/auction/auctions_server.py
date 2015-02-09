from datetime import datetime
from design import sync_design, endDate_view
from flask import Flask, render_template, request, abort, url_for, redirect, Response
from flask.ext.assets import Environment, Bundle
from flask_redis import Redis
from gevent import monkey
from paste.proxy import make_proxy
from pytz import timezone as tz
from urlparse import urljoin
from wsgiproxy import HostProxy
import couchdb
import time
from sse import Sse as PySse

monkey.patch_all()


class AuctionsHostProxy(HostProxy):

    def process_request(self, uri, method, headers, environ):
        headers["X-Forwarded-Path"] = request.url
        headers["X-Request-ID"] = environ.get("x_request_id", "")
        return super(AuctionsHostProxy, self).process_request(
            uri, method, headers, environ
        )

auctions_server = Flask(
    __name__,
    static_url_path='',
    template_folder='templates'
)

################################################################################
assets = Environment(auctions_server)
css = Bundle("vendor/bootstrap/dist/css/bootstrap.min.css",
             "vendor/angular-growl-2/build/angular-growl.min.css",
             "static/css/starter-template.css",
             filters='cssmin,datauri', output='min/styles_%(version)s.css')
assets.register('all_css', css)

js = Bundle("vendor/event-source-polyfill/eventsource.min.js",
            "vendor/moment/min/moment.min.js",
            "vendor/angular/angular.min.js",
            "vendor/angular-cookies/angular-cookies.min.js",
            "vendor/pouchdb/dist/pouchdb.js",
            "vendor/angular-bootstrap/ui-bootstrap-tpls.min.js",
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
    return render_template(
        'index.html',
        db_url=auctions_server.config.get('EXT_COUCH_DB'),
        auction_doc_id=auction_doc_id
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
        return AuctionsHostProxy(proxy_path, client='requests', chunk_size=1)
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
                      preferred_url_scheme='http'
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
    auctions_server.config['PREFERRED_URL_SCHEME'] = preferred_url_scheme
    auctions_server.config['REDIS_URL'] = redis_url
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
    # auctions_server.config['ASSETS_DEBUG'] = True
    return auctions_server
