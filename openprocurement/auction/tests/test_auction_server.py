import pytest
from webtest import TestApp
from openprocurement.auction.auctions_server import auctions_server as frontend
import openprocurement.auction.auctions_server as auctions_server_module
from mock import MagicMock, call


@pytest.fixture(scope='function')
def auctions_server(mocker):
    logger = MagicMock(spec=frontend.logger)
    logger.name = 'some-logger'
    frontend.logger_name = logger.name
    frontend._logger = logger

    test_app = TestApp(frontend)
    # request.cls.server = test_app
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

    def test_log_post_ok_1(self, auctions_server, send, response):
        resp = auctions_server['test_app'].post_json('/log', {'key': 'value'})
        assert resp.status_int == 200
        assert resp.body == 'Response Message'
        assert resp.content_type == 'text/html'
        send.assert_called_once_with('', SYSLOG_IDENTIFIER='AUCTION_CLIENT',
                                     key=u'value', REMOTE_ADDR='')
        response.assert_called_once_with('ok')

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

    def test_health(self):
        pass

    # mock server.py
    def test_proxy(self):
        pass

    def test_get_server_time(self):
        pass

    # optional
    def test_config(self):
        pass
