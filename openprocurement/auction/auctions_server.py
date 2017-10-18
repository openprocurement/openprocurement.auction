from datetime import datetime
from flask import Flask, request, abort, redirect, Response
from json import dumps, loads
from sse import Sse as PySse
from systemd.journal import send
from urlparse import urlparse, urlunparse

from openprocurement.auction.utils import get_mapping
from openprocurement.auction.proxy import StreamProxy


LIMIT_REPLICATIONS_LIMIT_FUNCTIONS = {
    'any': any,
    'all': all
}


auctions_server = Flask(__name__)


@auctions_server.before_request
def before_request():
    auctions_server.logger.debug('Start {0.method}: {0.url}'.format(request))


@auctions_server.after_request
def after_request(response):
    auctions_server.logger.debug(
        'End {1.status_code} : {0.method} : {0.url}'.format(request, response)
    )
    return response


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
        if request.environ.get('REMOTE_ADDR', '') and data['REMOTE_ADDR'] == "":
            data['REMOTE_ADDR'] += request.environ.get('REMOTE_ADDR', '')
        data["SYSLOG_IDENTIFIER"] = "AUCTION_CLIENT"
        send(msg, **data)
        return Response('ok')
    except:
        return Response('error')


@auctions_server.route('/health')
def health():
    data = auctions_server.couch_server.tasks()
    health_threshold = auctions_server.config.get(
        'limit_replications_progress', 1024
    )
    output = {
        task['replication_id']: task['progress']
        for task in data if 'type' in task and task['type'] == 'replication'
    }
    response = Response(dumps(output))
    limit_replications_func = LIMIT_REPLICATIONS_LIMIT_FUNCTIONS.get(
        auctions_server.config.get('limit_replications_func', 'any')
    )

    if not(output and limit_replications_func(
        [task['source_seq'] - task['checkpointed_source_seq'] <=
             health_threshold
         for task in data if 'type' in task and task['type'] == 'replication']
    )):
        response.status_code = 503
    return response


def auctions_proxy(auction_doc_id, path):
    auctions_server.logger.debug('Auction_doc_id: {}'.format(auction_doc_id))
    proxy_path = auctions_server.proxy_mappings.get(
        str(auction_doc_id),
        get_mapping,
        (auctions_server.config['REDIS'], str(auction_doc_id), False), max_age=60
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
        if 'X-Forwarded-For' in request.headers:
            url = urlunparse(
                urlparse(request.url)._replace(netloc=request.headers['Host'])
            ).replace('/login', '')
            auctions_server.logger.info('Redirecting loging path to {}'.format(url))
            return redirect(url)
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
def auctions_get_server_time():
    response = Response(datetime.now(auctions_server.config['TIMEZONE']).isoformat())
    response.headers['Cache-Control'] = 'public, max-age=0'
    return response
