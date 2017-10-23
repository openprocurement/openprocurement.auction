# -*- coding: utf-8 -*-
import json
import logging
import couchdb
import datetime
from openprocurement.auction.databridge import ResourceFeeder
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
import pytest
from webtest import TestApp
from openprocurement.auction.auctions_server import auctions_server as frontend
import openprocurement.auction.auctions_server as auctions_server_module
from mock import MagicMock, NonCallableMock
from couchdb import Server
from memoize import Memoizer
from mock import sentinel
from sse import Sse as PySse
from flask import Response


DEFAULT = sentinel.DEFAULT
RESPONSE = sentinel.response

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


@pytest.fixture(scope='function')
def send(mocker):
    mock_send = mocker.patch.object(auctions_server_module, 'send')
    return mock_send


@pytest.fixture(scope='function')
def response(mocker):
    mock_response = mocker.patch.object(auctions_server_module, 'Response',
                                        return_value='Response Message')
    return mock_response


@pytest.fixture(scope='function')
def patch_response(request, mocker):
    params = getattr(request, 'param', {})
    resp = params.get('response', DEFAULT)
    mock_response = mocker.patch.object(auctions_server_module, 'Response',
                                        return_value=resp)
    return {'patch_resp': mock_response, 'result': resp} 


@pytest.fixture(scope='function')
def mock_auctions_server(request, mocker):
    params = getattr(request, 'param', {})

    server_config_redis = params.get('server_config_redis', DEFAULT)
    connection_limit = params.get('connection_limit', DEFAULT)
    get_mapping = params.get('get_mapping', DEFAULT)
    proxy_path = params.get('proxy_path', DEFAULT)
    event_sources_pool = params.get('event_sources_pool', DEFAULT)
    proxy_connection_pool = params.get('proxy_connection_pool', DEFAULT)
    stream_proxy = params.get('stream_proxy', DEFAULT)
    db = params.get('db', DEFAULT)
    request_headers = params.get('request_headers', [])
    request_url = params.get('request_url', DEFAULT)
    redirect_url = params.get('redirect_url', DEFAULT)
    abort = params.get('abort', DEFAULT)

    class AuctionsServerAttributesContainer(object):
        logger = NotImplemented
        proxy_mappings = NotImplemented
        config = NotImplemented
        event_sources_pool = NotImplemented
        proxy_connection_pool = NotImplemented
        get_mapping = NotImplemented
        db = NotImplemented
        request_headers = NotImplemented

    class Request(object):
        headers = NotImplemented
        environ = NotImplemented
        url = NotImplemented

    class Config(object):
        __getitem__ = NotImplemented

    def config_getitem(item):
        if item == 'REDIS':
            return server_config_redis
        elif item == 'event_source_connection_limit':
            return connection_limit
        else:
            raise KeyError

    mock_path_info = MagicMock()

    def environ_setitem(item, value):
        if item == 'PATH_INFO':
            mock_path_info(value)
            return value
        else:
            raise KeyError

    mocker.patch.object(auctions_server_module, 'get_mapping', get_mapping)
    patch_pysse = mocker.patch.object(auctions_server_module, 'PySse',
                                      spec_set=PySse)
    patch_add_message = patch_pysse.return_value.add_message

    patch_request = mocker.patch.object(auctions_server_module, 'request',
                                        spec_set=Request)
    patch_request.environ.__setitem__.side_effect = environ_setitem
    patch_request.headers = request_headers
    patch_request.url = request_url

    patch_redirect = mocker.patch.object(auctions_server_module, 'redirect',
                                         return_value=redirect_url)
    patch_abort = mocker.patch.object(auctions_server_module, 'abort',
                                      return_value=abort)

    patch_StreamProxy = \
        mocker.patch.object(auctions_server_module, 'StreamProxy',
                            return_value=stream_proxy)

    auctions_server = NonCallableMock(spec_set=
                                      AuctionsServerAttributesContainer)

    logger = MagicMock(spec_set=frontend.logger)
    proxy_mappings = MagicMock(spec_set=Memoizer({}))
    proxy_mappings.get.return_value = proxy_path
    config = MagicMock(spec_set=Config)
    config.__getitem__.side_effect = config_getitem

    auctions_server.logger = logger
    auctions_server.proxy_mappings = proxy_mappings
    auctions_server.config = config
    auctions_server.event_sources_pool = event_sources_pool
    auctions_server.proxy_connection_pool = proxy_connection_pool
    auctions_server.db = db

    mocker.patch.object(auctions_server_module, 'auctions_server',
                        auctions_server)

    return {'server': auctions_server,
            'proxy_mappings': proxy_mappings,
            'mock_path_info': mock_path_info,
            'patch_StreamProxy': patch_StreamProxy,
            'patch_redirect': patch_redirect,
            'patch_abort': patch_abort,
            'patch_PySse': patch_pysse,
            'patch_add_message': patch_add_message}


@pytest.fixture(scope='function')
def auctions_server(request):
    params = getattr(request, 'param', {})
    server_config = params.get('server_config', {})

    logger = MagicMock(spec_set=frontend.logger)
    logger.name = server_config.get('logger_name', 'some-logger')
    frontend.logger_name = logger.name
    frontend._logger = logger

    for key in ('limit_replications_func', 'limit_replications_progress'):
        frontend.config.pop(key, None)

    for key in ('limit_replications_func', 'limit_replications_progress'):
        if key in server_config:
            frontend.config[key] = server_config[key]

    frontend.couch_server = MagicMock(spec_set=Server)
    frontend.config['TIMEZONE'] = 'some_time_zone'

    if 'couch_tasks' in params:
        frontend.couch_server.tasks.return_value = params['couch_tasks']

    test_app = TestApp(frontend)
    return {'app': frontend, 'test_app': test_app}


@pytest.yield_fixture(scope="function")
def log_for_test(request):
    LOGGER.debug('-------- Test Start ---------')
    LOGGER.debug('Current module: {0}'.format(request.module.__name__))
    LOGGER.debug('Current test class: {0}'.format(request.cls.__name__))
    LOGGER.debug('Current test function: {0}'
                 .format(request.function.__name__))
    yield LOGGER
    LOGGER.debug('-------- Test End ---------')
