import json
import logging
import couchdb
import datetime
import gc
import openprocurement.auction.databridge as databridge_module
import pytest
from gevent import spawn, killall, GreenletExit
from greenlet import greenlet
from openprocurement.auction import core as core_module
from openprocurement.auction.chronograph import AuctionsChronograph
from openprocurement.auction.databridge import AuctionsDataBridge
from openprocurement.auction.helpers.chronograph import \
    MAX_AUCTION_START_TIME_RESERV
from openprocurement.auction.tests.unit.utils import get_tenders_dummy
from openprocurement.auction.tests.unit.utils import kill_child_processes
from openprocurement.auction.worker.auction import Auction
from openprocurement.auction.tests.utils import update_auctionPeriod, \
    AUCTION_DATA
from openprocurement.auction.tests.unit.utils import worker_defaults, \
    test_chronograph_config, worker_defaults_file_path, test_bridge_config
import yaml


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

# def pytest_generate_tests(metafunc):
#     for funcargs in getattr(metafunc.function, 'funcarglist', ()):
#         metafunc.addcall(funcargs=funcargs)


auction_data_simple = AUCTION_DATA['simple']
auction_data_multilot = AUCTION_DATA['multilot']


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
def chronograph(request):
    logging.config.dictConfig(test_chronograph_config)
    chrono = AuctionsChronograph(test_chronograph_config)
    spawn(chrono.run)

    def delete_chronograph():
        chrono.server.stop()

        kill_child_processes()

        jobs = chrono.scheduler.get_jobs()
        for job in jobs:
             chrono.scheduler.remove_job(job.id)

        # chrono.scheduler.shutdown()
        # TODO: find out why the previous command causes the problems.
        # But we can skip it as scheduler is turned off by the following block.

        try:
            killall(
                [obj for obj in gc.get_objects() if isinstance(obj, greenlet)])
        except GreenletExit:
            print("Correct exception 'GreenletExit' raised.")
        except Exception as e:
            print("Gevent couldn't close gracefully.")
            raise e

    request.addfinalizer(delete_chronograph)

    return chrono


@pytest.yield_fixture(scope="function")
def auction(request):
    defaults = {'time': MAX_AUCTION_START_TIME_RESERV,
                'delta_t': datetime.timedelta(seconds=10)}

    params = getattr(request, 'param', defaults)
    for key in defaults.keys():
        params[key] = defaults[key] if params.get(key, 'default') == 'default'\
            else params[key]

    with update_auctionPeriod(
            auction_data_simple,
            auction_type='simple',
            time_shift=params['time']+params['delta_t']) \
            as updated_doc, open(updated_doc, 'r') as auction_updated_data:
        auction_inst = Auction(
            tender_id=auction_data_simple['data']['tenderID'],
            worker_defaults=yaml.load(open(worker_defaults_file_path)),
            auction_data=json.load(auction_updated_data),
            lot_id=False)
        yield auction_inst

    auction_inst._end_auction_event.set()


@pytest.fixture(scope='function')
def bridge(request, mocker):
    params = getattr(request, 'param', {})
    tenders = params.get('tenders', [])
    bridge_config = params.get('bridge_config', test_bridge_config)

    mock_get_tenders = \
        mocker.patch.object(databridge_module, 'get_tenders',
                            side_effect=get_tenders_dummy(tenders),
                            autospec=True)

    mock_do_until_success = \
        mocker.patch.object(core_module, 'do_until_success', autospec=True)

    bridge_inst = AuctionsDataBridge(bridge_config)
    spawn(bridge_inst.run)

    return {'bridge': bridge_inst,
            'bridge_config': bridge_config,
            'tenders': tenders,
            'mock_get_tenders': mock_get_tenders,
            'mock_do_until_success': mock_do_until_success}


@pytest.fixture(scope="function")
def log_for_test(request):
    LOGGER.debug('-------- Test Start ---------')
    LOGGER.debug('Current module: {0}'.format(request.module.__name__))
    LOGGER.debug('Current test class: {0}'.format(request.cls.__name__))
    LOGGER.debug('Current test function: {0}'.format(request.function.__name__))
