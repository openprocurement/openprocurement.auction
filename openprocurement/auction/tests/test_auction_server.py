# TODO: check StopIteration was raised
# TODO: test make_auctions_app.


import pytest
from webtest import TestApp
from openprocurement.auction.auctions_server import auctions_server as frontend
import openprocurement.auction.auctions_server as auctions_server_module
from mock import MagicMock, call
from couchdb import Server
from openprocurement.auction.tests.data.couch_data import \
    l1a, l1b, l1c, l2a, l2b, l3


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
    def test_before_after_request(self, auctions_server):
        resp = auctions_server['test_app'].get('/route_not_defined',
                                               expect_errors=True)

        expected = \
            [call('Start GET: http://localhost:80/route_not_defined',),
             call('End 404 : GET : http://localhost:80/route_not_defined',)]
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
        resp = auctions_server['test_app']\
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

    # mock server.py
    def test_proxy(self):
        pass

    def test_get_server_time(self, auctions_server, mocker):
        server_time = 'some_server_time'

        mock_datetime = mocker.patch.object(auctions_server_module, 'datetime')
        mock_datetime.now.return_value.isoformat.return_value = server_time

        resp = auctions_server['test_app'].get('/get_current_server_time')
        mock_datetime.now.assert_called_once_with(auctions_server['app'].config['TIMEZONE'])
        assert resp.status_int == 200
        assert resp.body == server_time
        assert resp.headers['Cache-Control'] == 'public, max-age=0'


    # optional
    def test_config(self):
        pass
