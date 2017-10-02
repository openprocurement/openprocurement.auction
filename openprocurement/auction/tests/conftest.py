# -*- coding: utf-8 -*-
import json
import logging
import couchdb
import datetime
from openprocurement.auction.databridge import ResourceFeeder
import pytest
from gevent import spawn
from openprocurement.auction import core as core_module
from openprocurement.auction.chronograph import AuctionsChronograph
from openprocurement.auction.databridge import AuctionsDataBridge
from openprocurement.auction.helpers.chronograph import \
    MIN_AUCTION_START_TIME_RESERV
from openprocurement.auction.tests.utils import get_tenders_dummy
from openprocurement.auction.worker.auction import Auction
from openprocurement.auction.tests.utils import update_auctionPeriod, \
    AUCTION_DATA
from openprocurement.auction.tests.utils import worker_defaults, \
    test_chronograph_config, worker_defaults_file_path, test_bridge_config
import yaml
import openprocurement.auction.helpers.couch as couch_module
import openprocurement.auction.chronograph as chrono_module
from openprocurement.auction.tests.utils import DummyTrue, iterview_wrappper


LOGGER = logging.getLogger('Log For Tests')

test_log_config = {
     'version': 1,
     'disable_existing_loggers': False,
     'formatters': {'simpleFormatter': {'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'}},
     'handlers': {'journal': {'class': 'ExtendedJournalHandler.ExtendedJournalHandler', 'formatter': 'simpleFormatter', 'SYSLOG_IDENTIFIER': 'AUCTIONS_LOG_FOR_TESTS', 'level': 'DEBUG'}},
     'loggers': {'Log For Tests': {'handlers': ['journal'], 'propagate': False, 'level': 'DEBUG'},
                 '': {'handlers': ['journal'], 'propagate': False, 'level': 'DEBUG'}}
     }

logging.config.dictConfig(test_log_config)


@pytest.fixture(scope='function')
def db(request):
    server = couchdb.Server("http://" + worker_defaults['COUCH_DATABASE'].split('/')[2])
    name = worker_defaults['COUCH_DATABASE'].split('/')[3]

    documents = getattr(request, 'param', None)

    def delete():
        del server[name]

    if name in server:
        delete()

    data_base = server.create(name)

    if documents:
        for doc in documents:
            data_base.save(doc)
            
    request.addfinalizer(delete)

    return data_base


@pytest.fixture(scope='function')
def chronograph(request, mocker):
    logging.config.dictConfig(test_chronograph_config)

    # We use 'dummy_true' variable instead of real True and mock iterview
    # with iterview_wrapper function to tear down the test gracefully.
    # Without these steps iterview from previous test running continue working
    # while next test have already been launched.
    dummy_true = DummyTrue()
    couch_module.TRUE = dummy_true
    mocker.patch.object(chrono_module, 'iterview',
                        side_effect=iterview_wrappper, autospec=True)

    chrono = AuctionsChronograph(test_chronograph_config)
    chrono_thread = spawn(chrono.run)

    def delete_chronograph():
        chrono.scheduler.execution_stopped = True
        dummy_true.ind = False
        chrono_thread.join(0.15)
        chrono.scheduler.shutdown(True, True)

    request.addfinalizer(delete_chronograph)

    return chrono_thread


@pytest.fixture(scope="function")
def auction(request):
    defaults = {'time': MIN_AUCTION_START_TIME_RESERV,
                'delta_t': datetime.timedelta(seconds=10)}

    params = getattr(request, 'param', defaults)
    for key in defaults.keys():
        params[key] = defaults[key] if params.get(key, 'default') == 'default'\
            else params[key]

    with update_auctionPeriod(
            AUCTION_DATA['simple']['path'],
            auction_type='simple',
            time_shift=params['time']+params['delta_t']) \
            as updated_doc, open(updated_doc, 'r') as auction_updated_data:
        auction_inst = Auction(
            tender_id=AUCTION_DATA['simple']['data']['data']['tenderID'],
            worker_defaults=yaml.load(open(worker_defaults_file_path)),
            auction_data=json.load(auction_updated_data),
            lot_id=False)

    return auction_inst


@pytest.fixture(scope='function')
def bridge(request, mocker):
    params = getattr(request, 'param', {})
    tenders = params.get('tenders', [])
    bridge_config = params.get('bridge_config', test_bridge_config)

    mock_resource_items = \
        mocker.patch.object(ResourceFeeder, 'get_resource_items',
                            side_effect=get_tenders_dummy(tenders),
                            autospec=True)

    mock_do_until_success = \
        mocker.patch.object(core_module, 'do_until_success', autospec=True)

    bridge_inst = AuctionsDataBridge(bridge_config)
    thread = spawn(bridge_inst.run)

    return {'bridge': bridge_inst,
            'bridge_thread': thread,
            'bridge_config': bridge_config,
            'tenders': tenders,
            'mock_resource_items': mock_resource_items,
            'mock_do_until_success': mock_do_until_success}


@pytest.yield_fixture(scope="function")
def log_for_test(request):
    LOGGER.debug('-------- Test Start ---------')
    LOGGER.debug('Current module: {0}'.format(request.module.__name__))
    LOGGER.debug('Current test class: {0}'.format(request.cls.__name__))
    LOGGER.debug('Current test function: {0}'
                 .format(request.function.__name__))
    yield LOGGER
    LOGGER.debug('-------- Test End ---------')
