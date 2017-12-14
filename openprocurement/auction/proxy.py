from restkit.contrib.wsgi_proxy import HostProxy
from flask import request, current_app as app
from http_parser.util import IOrderedDict
from Cookie import SimpleCookie
from .utils import StreamWrapper
from werkzeug.exceptions import NotFound


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
                 rewrite_path=None,
                 **kwargs):
        super(StreamProxy, self).__init__(uri, **kwargs)
        self.rewrite_path = rewrite_path
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
            if self.rewrite_path:
                environ['PATH_INFO'] = environ['PATH_INFO'].replace(self.rewrite_path[0], self.rewrite_path[1])
            response = super(StreamProxy, self).__call__(
                environ, start_response_decorated(start_response)
            )
            stream_response = StreamWrapper(response.resp, response.connection)
            if 'event_source' in stream_response.resp.request.url:
                self.add_event_source(stream_response)
            return stream_response
        except Exception, e:
            app.logger.warning(
                "Error on request to {} with msg {}".format(request.url, e)
            )
            app.proxy_mappings.expire(str(self.auction_doc_id), 0)
            return NotFound()(environ, start_response)


def couch_server_proxy(path):
    """USED FOR DEBUG ONLY"""
    return StreamProxy(
        app.config['PROXY_COUCH_URL'],
        app.event_sources_pool,
        pool=app.proxy_connection_pool,
        backend="gevent"
    )


def auth_couch_server_proxy(path):
    """USED FOR DEBUG ONLY"""
    return StreamProxy(
        app.config['PROXY_COUCH_URL'],
        app.event_sources_pool,
        rewrite_path=(app.config['COUCH_DB'] + "_secured", app.config['COUCH_DB']),
        pool=app.proxy_connection_pool,
        backend="gevent"
    )
