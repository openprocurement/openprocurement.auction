# -*- coding: utf-8 -*-
# TODO: check StopIteration was raised
# TODO: test make_auctions_app.


import pytest
from mock import MagicMock
import openprocurement.auction.auctions_server as auctions_server_module
from openprocurement.auction.auctions_server import auctions_proxy
from openprocurement.auction.tests.data.couch_data import \
    l1a, l1b, l1c, l2a, l2b, l3
from openprocurement.auction.tests.utils import Any
from openprocurement.auction.tests.data.auctions_server_data import \
    proxy_data_proxy_path, proxy_data_no_proxy_path_forwarded_header_1, \
    proxy_data_no_proxy_path_forwarded_header_2, proxy_data_no_proxy_path, \
    proxy_data_no_proxy_path_no_forwarded_header
from mock import call
from openprocurement.auction.tests.conftest import RESPONSE
from openprocurement.auction.tests.data.auctions_server_data import \
    AUCTION_DOC_ID


class TestAuctionsServer(object):
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
                                   expected_result):

        output = auctions_proxy(AUCTION_DOC_ID, path)

        # assertion block
        mock_auctions_server['proxy_mappings'].get.assert_called_once_with(
            AUCTION_DOC_ID,
            proxy_data_proxy_path['get_mapping'],
            (proxy_data_proxy_path['server_config_redis'],
             AUCTION_DOC_ID, False), max_age=Any(int)
        )
        mock_auctions_server['mock_path_info']\
            .assert_called_once_with('/' + path)
        mock_auctions_server['patch_StreamProxy'].assert_called_once_with(
            proxy_data_proxy_path['proxy_path'],
            auction_doc_id=AUCTION_DOC_ID,
            event_sources_pool=proxy_data_proxy_path['event_sources_pool'],
            event_source_connection_limit=
                proxy_data_proxy_path['connection_limit'],
            pool=proxy_data_proxy_path['proxy_connection_pool'],
            backend='gevent'
        )
        assert output == expected_result

    @pytest.mark.parametrize(
        'mock_auctions_server, transformed_url, expected_result',
        [(proxy_data_no_proxy_path_forwarded_header_1,
          proxy_data_no_proxy_path_forwarded_header_1['transformed_url'],
          proxy_data_no_proxy_path_forwarded_header_1['redirect_url']),
         (proxy_data_no_proxy_path_forwarded_header_2,
          proxy_data_no_proxy_path_forwarded_header_2['transformed_url'],
          proxy_data_no_proxy_path_forwarded_header_2['redirect_url']),
         ],
        indirect=['mock_auctions_server'])
    def test_proxy_path_login_1(self, mock_auctions_server, transformed_url,
                                expected_result):

        output = auctions_proxy(AUCTION_DOC_ID, 'login')

        # assertion block
        mock_auctions_server['proxy_mappings'].get.assert_called_once_with(
            AUCTION_DOC_ID,
            proxy_data_proxy_path['get_mapping'],
            (proxy_data_proxy_path['server_config_redis'],
             AUCTION_DOC_ID, False), max_age=Any(int)
        )

        mock_auctions_server['patch_redirect'].\
            assert_called_once_with(transformed_url)
        assert output == expected_result

    @pytest.mark.parametrize(
        'mock_auctions_server, expected_result',
        [(proxy_data_no_proxy_path_no_forwarded_header, 
          proxy_data_no_proxy_path_no_forwarded_header['abort'])],
        indirect=['mock_auctions_server'])
    def test_proxy_path_login_2(self, mock_auctions_server, expected_result):

        output = auctions_proxy(AUCTION_DOC_ID, 'login')

        # assertion block
        mock_auctions_server['proxy_mappings'].get.assert_called_once_with(
            AUCTION_DOC_ID,
            proxy_data_proxy_path['get_mapping'],
            (proxy_data_proxy_path['server_config_redis'],
             AUCTION_DOC_ID, False), max_age=Any(int)
        )
        mock_auctions_server['patch_abort'].assert_called_once_with(404)
        assert output == expected_result

    @pytest.mark.parametrize(
        'mock_auctions_server, patch_response',
        [(proxy_data_no_proxy_path, {'response': RESPONSE})],
        indirect=['mock_auctions_server', 'patch_response'])
    def test_proxy_path_event_source(self, mock_auctions_server,
                                     patch_response):

        manager = MagicMock()
        manager.attach_mock(mock_auctions_server['patch_PySse'],
                            'patch_PySse')
        manager.attach_mock(mock_auctions_server['patch_add_message'],
                            'patch_add_message')
        manager.attach_mock(patch_response['patch_resp'], 'patch_resp')

        output = auctions_proxy(AUCTION_DOC_ID, 'event_source')

        # assertion block
        expected_calls = [call.patch_PySse(),
                          call.patch_add_message('Close', 'Disable'),
                          call.patch_resp(
                              mock_auctions_server['patch_PySse'].return_value,
                              mimetype='text/event-stream',
                              content_type='text/event-stream'
                          )]
        assert manager.mock_calls == expected_calls
        assert output == patch_response['result']

    @pytest.mark.parametrize(
        'mock_auctions_server, expected_result',
        [(proxy_data_no_proxy_path, proxy_data_no_proxy_path['abort'])],
        indirect=['mock_auctions_server'])
    def test_proxy_path_smth(self, mock_auctions_server, expected_result):

        output = auctions_proxy(AUCTION_DOC_ID, 'smth_path')

        # assertion block
        mock_auctions_server['patch_abort'].assert_called_once_with(404)
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
