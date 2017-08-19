# -*- coding: utf-8 -*-
# TODO See: openprocurement.auction.core.Planning
from gevent import monkey
monkey.patch_all()

import unittest
import datetime
import os
import logging
import uuid
from gevent import sleep
from gevent.queue import Queue
from couchdb import Server
from mock import MagicMock, patch
from munch import munchify
from httplib import IncompleteRead
from openprocurement_client.exceptions import RequestFailed
import pytest
from openprocurement.auction.databridge import AuctionsDataBridge
# from openprocurement.auction.tests.utils import MockFeedItem
from .conftest import test_bridge_config, test_bridge_config_error_port
from urlparse import urljoin
from pytest import raises


logger = logging.getLogger()
logger.level = logging.DEBUG


class DataBridgeConfigError(Exception):
    pass


class TestDatabridge(object):
    """
    check with different data for 'planning' 'cancel'
    with lot_id no lot_id
    """

    def test_init(self, db, bridge):
        assert 'tenders_api_server' in bridge.config['main']
        assert 'tenders_api_version' in bridge.config['main']
        assert 'tenders_api_token' in bridge.config['main']
        assert 'couch_url' in bridge.config['main']
        assert 'auctions_db' in bridge.config['main']
        assert 'timezone' in bridge.config['main']
        assert 'auction_worker' in bridge.config['main']
        assert 'auction_worker_config' in bridge.config['main']
        assert 'plugins' in bridge.config['main']
        assert 'esco.EU' in bridge.config['main']
        assert 'auction_worker' in bridge.config['main']['esco.EU']
        assert bridge.couch_url == urljoin(bridge.config['main']['couch_url'], bridge.config['main']['auctions_db'])

        # self.assertEqual(len(bridge.server.uuids()[0]), 32) # TODO: what is it???

    def test_connetcion_refused(self, db):
        with raises(Exception) as exc_info:
            AuctionsDataBridge(test_bridge_config_error_port)

        assert exc_info.value.strerror == 'Connection refused'

        # with self.assertRaises(DataBridgeConfigError) as e:
        #     bridge = EdgeDataBridge(self.config)
        # assert e.exception.message == 'Connection refused'


        # del bridge
        # self.config['main']['resource_items_queue_size'] = 101
        # self.config['main']['retry_resource_items_queue_size'] = 101
        # bridge = AuctionsDataBridge(self.config)
        #
        # self.config['main']['couch_url'] = 'http://127.0.0.1:5987'
        # with self.assertRaises(DataBridgeConfigError) as e:
        #     bridge = AuctionsDataBridge(self.config)
        # self.assertEqual(e.exception.message, 'Connection refused')
        #
        # del bridge
        # self.config['main']['couch_url'] = 'http://127.0.0.1:5984'
        #
        # try:
        #     server = Server(self.config['main'].get('couch_url'))
        #     del server[self.config['main']['db_name']]
        # except:
        #     pass
        # test_config = {}
        #
        # # Create AuctionsDataBridge object with wrong config variable structure
        # test_config = {
        #     'mani': {
        #         'resources_api_server': 'https://lb.api-sandbox.openprocurement.org',
        #         'resources_api_version': "0",
        #         'public_resources_api_server': 'https://lb.api-sandbox.openprocurement.org',
        #         'couch_url': 'http://localhost:5984',
        #         'db_name': 'test_db',
        #         'retrievers_params': {
        #             'down_requests_sleep': 5,
        #             'up_requests_sleep': 1,
        #             'up_wait_sleep': 30,
        #             'queue_size': 101
        #         }
        #     },
        #     'version': 1
        # }
        # with self.assertRaises(DataBridgeConfigError) as e:
        #     AuctionsDataBridge(test_config)
        # self.assertEqual(e.exception.message, 'In config dictionary missed '
        #                  'section \'main\'')
        #
        # # Create AuctionsDataBridge object without variable 'resources_api_server' in config
        # del test_config['mani']
        # test_config['main'] = {
        #     'retrievers_params': {
        #         'down_requests_sleep': 5,
        #         'up_requests_sleep': 1,
        #         'up_wait_sleep': 30,
        #         'queue_size': 101
        #     }
        # }
        # with self.assertRaises(DataBridgeConfigError) as e:
        #     AuctionsDataBridge(test_config)
        # self.assertEqual(e.exception.message, 'In config dictionary empty or '
        #                  'missing \'tenders_api_server\'')
        # with self.assertRaises(KeyError) as e:
        #     test_config['main']['resources_api_server']
        # self.assertEqual(e.exception.message, 'resources_api_server')
        #
        # # Create AuctionsDataBridge object with empty resources_api_server
        # test_config['main']['resources_api_server'] = ''
        # with self.assertRaises(DataBridgeConfigError) as e:
        #     AuctionsDataBridge(test_config)
        # self.assertEqual(e.exception.message, 'In config dictionary empty or '
        #                  'missing \'tenders_api_server\'')
        #
        # # Create AuctionsDataBridge object with invalid resources_api_server
        # test_config['main']['resources_api_server'] = 'my_server'
        # with self.assertRaises(DataBridgeConfigError) as e:
        #     AuctionsDataBridge(test_config)
        # self.assertEqual(e.exception.message, 'Invalid \'tenders_api_server\' '
        #                  'url.')
        #
        # test_config['main']['resources_api_server'] = 'https://lb.api-sandbox.openprocurement.org'
        #
        # test_config['main']['db_name'] = 'public'
        # test_config['main']['resources_api_version'] = "0"
        # test_config['main']['public_resources_api_server'] \
        #     = 'https://lb.api-sandbox.openprocurement.org'
        #
        # # Create AuctionsDataBridge object with deleting config variables step by step
        # bridge = AuctionsDataBridge(test_config)
        # self.assertEqual(type(bridge), AuctionsDataBridge)
        # with self.assertRaises(KeyError) as e:
        #     test_config['main']['couch_url']
        # self.assertEqual(e.exception.message, 'couch_url')
        # del bridge
        #
        # del test_config['main']['resources_api_version']
        # bridge = AuctionsDataBridge(test_config)
        # self.assertEqual(type(bridge), AuctionsDataBridge)
        # with self.assertRaises(KeyError) as e:
        #     test_config['main']['resources_api_version']
        # self.assertEqual(e.exception.message, 'resources_api_version')
        # del bridge
        #
        # del test_config['main']['public_resources_api_server']
        # bridge = AuctionsDataBridge(test_config)
        # self.assertEqual(type(bridge), AuctionsDataBridge)
        # with self.assertRaises(KeyError) as e:
        #     test_config['main']['public_resources_api_server']
        # self.assertEqual(e.exception.message, 'public_resources_api_server')
        # del bridge
        # server = Server(test_config['main'].get('couch_url') or 'http://127.0.0.1:5984')
        # del server[test_config['main']['db_name']]
        #
        # test_config['main']['retrievers_params']['up_wait_sleep'] = 0
        # with self.assertRaises(DataBridgeConfigError) as e:
        #     AuctionsDataBridge(test_config)
        # self.assertEqual(e.exception.message, 'Invalid \'up_wait_sleep\' in '
        #                  '\'retrievers_params\'. Value must be grater than 30.')
        #
    def test_active_auction_no_lots(self):
        """TODO: """

    def test_active_auction_with_lots(self):
        """TODO: """

    def test_announce(self):
        """Only multilot tenders in auction.qualification status"""

    def test_cancel(self):
        """Auction has been cancelled"""
