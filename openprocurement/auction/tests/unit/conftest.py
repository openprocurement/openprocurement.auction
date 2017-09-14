import couchdb
import os
import pytest
import yaml
from openprocurement.auction.chronograph import AuctionsChronograph
from openprocurement.auction.tests.utils import update_auctionPeriod, \
    AUCTION_DATA, PWD
from openprocurement.auction.tests.unit.utils import TestClient
from openprocurement.auction.tests.unit.utils import kill_child_processes
from openprocurement.auction.worker.auction import Auction
from gevent import spawn, killall, GreenletExit
import json
import logging
from openprocurement.auction.helpers.chronograph import \
    MAX_AUCTION_START_TIME_RESERV
import datetime
import gc
from greenlet import greenlet
from openprocurement.auction.databridge import AuctionsDataBridge
from copy import deepcopy
from openprocurement.auction import core as core_module
import openprocurement.auction.databridge as databridge_module
from openprocurement.auction.tests.unit.utils import get_tenders_dummy


LOGGER = logging.getLogger('Log For Tests')
CONF_FILES_FOLDER = os.path.join(PWD, "unit", "data")

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

worker_defaults_file_path = \
    os.path.join(CONF_FILES_FOLDER, "auction_worker_defaults.yaml")
with open(worker_defaults_file_path) as stream:
    worker_defaults = yaml.load(stream)

chronograph_conf_file_path = \
    os.path.join(CONF_FILES_FOLDER, 'auctions_chronograph.yaml')
with open(chronograph_conf_file_path) as stream:
    test_chronograph_config = yaml.load(stream)
    test_chronograph_config['disable_existing_loggers'] = False
    test_chronograph_config['handlers']['journal']['formatter'] = 'simple'
    test_chronograph_config['main']['auction_worker'] = \
        os.path.join(PWD, (".." + os.path.sep)*5, "bin", "auction_worker")
    test_chronograph_config['main']['auction_worker_config'] = \
        os.path.join(PWD, 'unit', 'data', 'auction_worker_defaults.yaml')
    test_chronograph_config['main'] \
    ['auction_worker_config_for_api_version_dev'] = \
        os.path.join(PWD, 'unit', 'data', 'auction_worker_defaults.yaml')

databridge_conf_file_path = \
    os.path.join(CONF_FILES_FOLDER, 'auctions_data_bridge.yaml')
with open(databridge_conf_file_path) as stream:
    test_bridge_config = yaml.load(stream)
    test_bridge_config['disable_existing_loggers'] = False
    test_bridge_config['handlers']['journal']['formatter'] = 'simple'

test_bridge_config_error_port = deepcopy(test_bridge_config)
couch_url = test_bridge_config_error_port['main']['couch_url']
error_port = str(int(couch_url.split(':')[-1][:-1]) + 1)
couch_url_parts = couch_url.split(':')[0:-1]
couch_url_parts.append(error_port)
test_bridge_config_error_port['main']['couch_url'] = ':'.join(couch_url_parts)


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


test_client = \
    TestClient('http://0.0.0.0:{port}'.
               format(port=test_chronograph_config['main'].get('web_app')))


def job_is_added():
    resp = test_client.get('jobs')
    return (len(json.loads(resp.content)) == 1)


def job_is_not_added():
    resp = test_client.get('jobs')
    return (len(json.loads(resp.content)) == 0)


def job_is_active():
    resp = test_client.get('active_jobs')
    return (len(json.loads(resp.content)) == 1)


def job_is_not_active():
    resp = test_client.get('active_jobs')
    return (len(json.loads(resp.content)) == 0)


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
    # TODO: change it (MAX_AUCTION_START_TIME_RESERV)

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
