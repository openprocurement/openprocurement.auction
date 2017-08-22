# -*- coding: utf-8 -*-
# TODO: check that only "active.auction" tender status are taken into account
# TODO: check with different data for 'planning', 'cancel', 'qualification'
# TODO: with lot_id no lot_id



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
import openprocurement.auction.databridge as databridge_module
from openprocurement.auction.tests.unit.utils import \
    no_lots_tender_data_template, get_tenders_dummy, API_EXTRA, \
    check_call_dummy
from gevent import spawn
from openprocurement.auction import core as core_module


logger = logging.getLogger()
logger.level = logging.DEBUG


class TestDatabridgeConfig(object):
    def test_config_init(self, db, bridge):
        # TODO: check if value of bridge.config corresponds to config file
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


class TestDataBridgeRunLogInformation(object):
    # LOGGER.info('Start Auctions Bridge',
    #             extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING_START_BRIDGE})
    # LOGGER.info('Start data sync...',
    #             extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING_DATA_SYNC})
    pass


class TestDataBridgeGetTenders(object):
    @pytest.mark.parametrize("number_of_tenders", [0, 1, 2])
    def test_run_get_tenders_once(self, log_for_test, db, bridge, mocker,
                                  number_of_tenders):
        """
        Test checks:
        1) 'get_tenders' function is called once inside bridge.run method.
        2) 'get_tenders' yields the same number of tenders the database
           contains
        3) the function gevent.subprocess.check_call is not called if
           tender's data are empty.
        """
        mock_get_tenders = \
            mocker.patch.object(databridge_module, 'get_tenders',
                                side_effect=
                                get_tenders_dummy([{}]*number_of_tenders),
                                autospec=True)
        mock_check_call = \
            mocker.patch.object(core_module, 'check_call',
                                side_effect=check_call_dummy,
                                autospec=True)

        spawn(bridge.run)
        sleep(0.5)

        # check that 'get_tenders' function was called once
        mock_get_tenders.assert_called_once_with(
            host=test_bridge_config['main']['tenders_api_server'],
            version=test_bridge_config['main']['tenders_api_version'],
            key='',
            extra_params=API_EXTRA)

        # check that 'get_tenders' yielded the correct number of tenders
        assert mock_get_tenders.side_effect.ind == number_of_tenders

        # check that 'check_call' was not called as tender documents
        # doesn't contain any data
        assert mock_check_call.call_count == 0



# assertRaises

# endDate
# no_lots_tender_data = deepcopy(no_lots_tender_data_template)
# no_lots_tender_data['auctionPeriod'] = \
#     {'startDate': '2017-06-28T10:32:19.233669+03:00'}

    def test_active_auction_with_lots(self):
        """TODO: """

    def test_announce(self):
        """Only multilot tenders in auction.qualification status"""

    def test_cancel(self):
        """Auction has been cancelled"""
