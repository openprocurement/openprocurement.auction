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
from .conftest import test_bridge_config
from urlparse import urljoin
from pytest import raises
from copy import deepcopy


logger = logging.getLogger()
logger.level = logging.DEBUG


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

    def test_connetcion_refused(self, db):
        with raises(Exception) as exc_info:
            AuctionsDataBridge(test_bridge_config_error_port)
        assert exc_info.value.strerror == 'Connection refused'

    def test_error_config(self, db):
        keys = ['couch_url', 'auctions_db']
        for key in keys:
            test_bridge_error_config = deepcopy(test_bridge_config)
            del test_bridge_error_config['main'][key]
            with raises(KeyError) as exc_info:
                AuctionsDataBridge(test_bridge_error_config)
            assert key in exc_info.value

    def test_active_auction_no_lots(self):
        """TODO: """

    def test_active_auction_with_lots(self):
        """TODO: """

    def test_announce(self):
        """Only multilot tenders in auction.qualification status"""

    def test_cancel(self):
        """Auction has been cancelled"""
