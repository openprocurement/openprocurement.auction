import couchdb
import os
import pytest
from requests import Session
import yaml
from openprocurement.auction.chronograph import AuctionsChronograph
from openprocurement.auction.tests.utils import update_auctionPeriod, AUCTION_DATA
from openprocurement.auction.worker.auction import Auction, SCHEDULER
from gevent import spawn, sleep
from ..utils import PWD
import json
import logging
from openprocurement.auction.helpers.chronograph import MAX_AUCTION_START_TIME_RESERV
import datetime


LOGGER = logging.getLogger('Log For Tests')

test_log_config = {
     'version': 1,
     'disable_existing_loggers': False,
     'formatters': {'simpleFormatter': {'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'}},
     'handlers': {'journal': {'class': 'ExtendedJournalHandler.ExtendedJournalHandler', 'formatter': 'simpleFormatter', 'SYSLOG_IDENTIFIER': 'AUCTIONS_LOG_FOR_TESTS', 'level': 'DEBUG'}},
     'loggers': {'Log For Tests': {'handlers': ['journal'], 'propagate': False, 'level': 'DEBUG'}}
     }

logging.config.dictConfig(test_log_config)

# def pytest_generate_tests(metafunc):
#     for funcargs in getattr(metafunc.function, 'funcarglist', ()):
#         metafunc.addcall(funcargs=funcargs)


auction_data_simple = AUCTION_DATA['simple']
auction_data_multilot = AUCTION_DATA['multilot']


worker_defaults_file_path = os.path.join(PWD, "unit/data/auction_worker_defaults.yaml")
with open(worker_defaults_file_path) as stream:
    worker_defaults = yaml.load(stream)


chronograph_conf_file_path = os.path.join(PWD, "unit/data/auctions_chronograph.yaml")
with open(chronograph_conf_file_path) as stream:
    test_chronograph_config = yaml.load(stream)
    test_chronograph_config['disable_existing_loggers'] = False
    test_chronograph_config['handlers']['journal']['formatter'] = 'simple'


@pytest.fixture(scope='function')
def db(request):
    server = couchdb.Server("http://" + worker_defaults['COUCH_DATABASE'].split('/')[2])
    name = worker_defaults['COUCH_DATABASE'].split('/')[3]

    def delete():
        del server[name]

    if name in server:
        delete()
    data_base = server.create(name)

    request.addfinalizer(delete)

    return data_base


@pytest.fixture(scope='function')
def chronograph(request):
    # webapp = true
    logging.config.dictConfig(test_chronograph_config)
    chrono = AuctionsChronograph(test_chronograph_config)
    client = Session()  # TODO: Add prefix path
    spawn(chrono.run)
    return {'chronograph': chrono, 'client': client}


@pytest.yield_fixture(scope="function")
def auction(request):
    DELTA_T = datetime.timedelta(seconds=10)
    with update_auctionPeriod(auction_data_simple, auction_type='simple', time_shift=MAX_AUCTION_START_TIME_RESERV+DELTA_T) as updated_doc, open(updated_doc, 'r') as auction_updated_data:
        yield Auction(
            tender_id=auction_data_simple['data']['tenderID'],
            worker_defaults=yaml.load(open(worker_defaults_file_path)),
            auction_data=json.load(auction_updated_data),
            lot_id=False
        )

@pytest.fixture(scope="function")
def log_for_test(request):
    LOGGER.debug('-------- Test Start ---------')
    LOGGER.debug('Current module: {0}'.format(request.module.__name__))
    LOGGER.debug('Current test class: {0}'.format(request.cls.__name__))
    LOGGER.debug('Current test function: {0}'.format(request.function.__name__))
