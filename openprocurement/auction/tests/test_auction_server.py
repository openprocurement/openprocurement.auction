# TODO: check StopIteration was raised
# TODO: test make_auctions_app.


import pytest
from webtest import TestApp
from openprocurement.auction.auctions_server import auctions_server as frontend
import openprocurement.auction.auctions_server as auctions_server_module
from openprocurement.auction.auctions_server import auctions_proxy
from mock import MagicMock, call, NonCallableMock
from couchdb import Server
from mock import sentinel
from openprocurement.auction.tests.data.couch_data import \
    l1a, l1b, l1c, l2a, l2b, l3
from memoize import Memoizer
from openprocurement.auction.tests.utils import Any

DEFAULT = sentinel.DEFAULT

proxy_data_proxy_path = {'server_config_redis': sentinel.REDIS,
                         'connection_limit': sentinel.connection_limit,
                         'proxy_connection_pool': sentinel.proxy_pool,
                         'get_mapping': sentinel.get_mapping,
                         'proxy_path': sentinel.proxy_path,
                         'stream_proxy': sentinel.stream_proxy,
                         'event_sources_pool': sentinel.event_sources_pool,}


@pytest.fixture(scope='function')
def mock_auctions_server(request, mocker):
    params = getattr(request, 'param', {})

    server_config_redis = params.get('server_config_redis', DEFAULT)
    connection_limit = params.get('connection_limit', DEFAULT)
    get_mapping = params.get('get_mapping', DEFAULT)
    proxy_path = params.get('proxy_path', DEFAULT)
    event_sources_pool = params.get('event_sources_pool', DEFAULT)
    proxy_connection_pool = params.get('proxy_connection_pool', DEFAULT)
    stream_proxy = params.get('stream_proxy', DEFAULT)

    class AuctionsServerAttributesContainer(object):
        logger = NotImplemented
        proxy_mappings = NotImplemented
        config = NotImplemented
        event_sources_pool = NotImplemented
        proxy_connection_pool = NotImplemented
        get_mapping = NotImplemented

    attr = AuctionsServerAttributesContainer()

    class Config(object):
        __getitem__ = NotImplemented

    attr_conf = Config()

    def config_getitem(item):
        if item == 'REDIS':
            return server_config_redis
        elif item == 'event_source_connection_limit':
            return connection_limit
        else:
            raise KeyError

    mock_path_info = MagicMock()

    def environ_setitem(item, value):
        if item == 'PATH_INFO':
            mock_path_info(value)
            return value
        else:
            raise KeyError

    mocker.patch.object(auctions_server_module, 'get_mapping', get_mapping)

    patch_request = mocker.patch.object(auctions_server_module, 'request')
    patch_request.environ.__setitem__.side_effect = environ_setitem

    patch_StreamProxy = \
        mocker.patch.object(auctions_server_module, 'StreamProxy',
                            return_value=stream_proxy)

    auctions_server = NonCallableMock(spec_set=attr)

    logger = MagicMock(spec_set=frontend.logger)
    proxy_mappings = MagicMock(spec_set=Memoizer({}))
    proxy_mappings.get.return_value = proxy_path
    config = MagicMock(spec_set=attr_conf)
    config.__getitem__.side_effect = config_getitem

    auctions_server.logger = logger
    auctions_server.proxy_mappings = proxy_mappings
    auctions_server.config = config
    auctions_server.event_sources_pool = event_sources_pool
    auctions_server.proxy_connection_pool = proxy_connection_pool

    return {'server': auctions_server,
            'proxy_mappings': proxy_mappings,
            'mock_path_info': mock_path_info,
            'patch_StreamProxy': patch_StreamProxy}


@pytest.fixture(scope='function')
def auctions_server(request):
    params = getattr(request, 'param', {})
    server_config = params.get('server_config', {})

    logger = MagicMock(spec_set=frontend.logger)
    logger.name = server_config.get('logger_name', 'some-logger')
    frontend.logger_name = logger.name
    frontend._logger = logger

    for key in ('limit_replications_func', 'limit_replications_progress'):
        frontend.config.pop(key, None)

    for key in ('limit_replications_func', 'limit_replications_progress'):
        if key in server_config:
            frontend.config[key] = server_config[key]

    frontend.couch_server = MagicMock(spec_set=Server)
    frontend.config['TIMEZONE'] = 'some_time_zone'

    if 'couch_tasks' in params:
        frontend.couch_server.tasks.return_value = params['couch_tasks']

    test_app = TestApp(frontend)
    return {'app': frontend, 'test_app': test_app}


@pytest.fixture(scope='function')
def send(mocker):
    mock_send = mocker.patch.object(auctions_server_module, 'send')
    return mock_send


@pytest.fixture(scope='function')
def response(mocker):
    mock_response = mocker.patch.object(auctions_server_module, 'Response',
                                        return_value='Response Message')
    return mock_response


@pytest.mark.usefixtures("auctions_server")
class TestAuctionsServer(object):
    auction_doc_id = 'some_id'

    def test_before_after_request(self, auctions_server):
        resp = auctions_server['test_app'].get('/route_not_defined',
                                               expect_errors=True)

        expected = \
            [call('Start GET: http://localhost:80/route_not_defined', ),
             call('End 404 : GET : http://localhost:80/route_not_defined', )]
        assert auctions_server['app'].logger.debug.call_args_list == expected
        assert resp.status_int == 404
        assert 'Not Found' in resp.body

    def test_log_post_error(self, auctions_server, send, response):
        resp = auctions_server['test_app'].post('/log', {'key': 'value'})
        assert resp.status_int == 200
        assert resp.body == 'Response Message'
        assert resp.content_type == 'text/html'
        response.assert_called_once_with('error')

    # post without extra_environ
    def test_log_post_ok_1(self, auctions_server, send, response):
        resp = auctions_server['test_app'].post_json('/log', {'key': 'value'})
        assert resp.status_int == 200
        assert resp.body == 'Response Message'
        assert resp.content_type == 'text/html'
        send.assert_called_once_with('', SYSLOG_IDENTIFIER='AUCTION_CLIENT',
                                     key=u'value', REMOTE_ADDR='')
        response.assert_called_once_with('ok')

    # post with extra_environ
    def test_log_post_ok_2(self, auctions_server, send, response):
        resp = auctions_server['test_app'] \
            .post_json('/log', {'key': 'value'},
                       extra_environ={'REMOTE_ADDR': '0.0.0.0'})
        assert resp.status_int == 200
        assert resp.body == 'Response Message'
        assert resp.content_type == 'text/html'
        send.assert_called_once_with('', SYSLOG_IDENTIFIER='AUCTION_CLIENT',
                                     key=u'value', REMOTE_ADDR='0.0.0.0')
        response.assert_called_once_with('ok')

    @pytest.mark.parametrize(
        'auctions_server, expected_response', l1a + l1b + l1c + l2a + l2b + l3,
        indirect=['auctions_server'])
    def test_health(self, auctions_server, expected_response):
        resp = auctions_server['test_app'].get('/health', expect_errors=True)
        assert resp.status_int == expected_response['status_int']
        assert resp.body == expected_response['body']

    @pytest.mark.parametrize(
        'mock_auctions_server, path, expected_result',
        [(proxy_data_proxy_path, 'some_path', proxy_data_proxy_path['stream_proxy']),
         (proxy_data_proxy_path, 'login', proxy_data_proxy_path['stream_proxy']),
         (proxy_data_proxy_path, 'event_source',  proxy_data_proxy_path['stream_proxy'])],
        indirect=['mock_auctions_server'])
    def test_proxy_with_proxy_path(self, mock_auctions_server, path, expected_result, mocker):
        mocker.patch.object(auctions_server_module, 'auctions_server',
                            mock_auctions_server['server'])

        output = auctions_proxy(self.auction_doc_id, path)

        # assertion block
        mock_auctions_server['proxy_mappings'].get.assert_called_once_with(
            self.auction_doc_id,
            proxy_data_proxy_path['get_mapping'],
            (proxy_data_proxy_path['server_config_redis'], self.auction_doc_id, False), max_age=Any(int)
        )
        mock_auctions_server['mock_path_info']\
            .assert_called_once_with('/' + path)
        mock_auctions_server['patch_StreamProxy'].assert_called_once_with(
            proxy_data_proxy_path['proxy_path'],
            auction_doc_id=self.auction_doc_id,
            event_sources_pool=proxy_data_proxy_path['event_sources_pool'],
            event_source_connection_limit=proxy_data_proxy_path['connection_limit'],
            pool=proxy_data_proxy_path['proxy_connection_pool'],
            backend='gevent'
        )
        assert output == expected_result

    def test_get_server_time(self, auctions_server, mocker):
        server_time = 'some_server_time'

        mock_datetime = mocker.patch.object(auctions_server_module, 'datetime')
        mock_datetime.now.return_value.isoformat.return_value = server_time

        resp = auctions_server['test_app'].get('/get_current_server_time')
        mock_datetime.now.\
            assert_called_once_with(auctions_server['app'].config['TIMEZONE'])
        assert resp.status_int == 200
        assert resp.body == server_time
        assert resp.headers['Cache-Control'] == 'public, max-age=0'

    # optional
    def test_config(self):
        pass
