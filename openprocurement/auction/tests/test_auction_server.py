# TODO: check StopIteration was raised
# TODO: test make_auctions_app.


import pytest
import openprocurement.auction.auctions_server as auctions_server_module
from openprocurement.auction.auctions_server import auctions_proxy
from openprocurement.auction.tests.data.couch_data import \
    l1a, l1b, l1c, l2a, l2b, l3
from openprocurement.auction.tests.utils import Any
from openprocurement.auction.tests.data.auctions_server_data import \
    proxy_data_proxy_path
from mock import call


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
        [(proxy_data_proxy_path, 'some_path',
          proxy_data_proxy_path['stream_proxy']),
         (proxy_data_proxy_path, 'login',
          proxy_data_proxy_path['stream_proxy']),
         (proxy_data_proxy_path, 'event_source',
          proxy_data_proxy_path['stream_proxy'])],
        indirect=['mock_auctions_server'])
    def test_proxy_with_proxy_path(self, mock_auctions_server, path,
                                   expected_result, mocker):
        mocker.patch.object(auctions_server_module, 'auctions_server',
                            mock_auctions_server['server'])

        output = auctions_proxy(self.auction_doc_id, path)

        # assertion block
        mock_auctions_server['proxy_mappings'].get.assert_called_once_with(
            self.auction_doc_id,
            proxy_data_proxy_path['get_mapping'],
            (proxy_data_proxy_path['server_config_redis'],
             self.auction_doc_id, False), max_age=Any(int)
        )
        mock_auctions_server['mock_path_info']\
            .assert_called_once_with('/' + path)
        mock_auctions_server['patch_StreamProxy'].assert_called_once_with(
            proxy_data_proxy_path['proxy_path'],
            auction_doc_id=self.auction_doc_id,
            event_sources_pool=proxy_data_proxy_path['event_sources_pool'],
            event_source_connection_limit=
                proxy_data_proxy_path['connection_limit'],
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
