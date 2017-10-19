import contextlib
import json
from requests import Session as Sess
import os
from copy import deepcopy
import yaml
from openprocurement.auction.helpers.couch import iterview
import logging
from datetime import datetime, timedelta
import tempfile
from dateutil.tz import tzlocal


def read_file_from_json(path):
    with open(path) as file:
        data = json.loads(file.read())
    return data


PWD = os.path.dirname(os.path.realpath(__file__))
LOGGER = logging.getLogger('Log For Tests')
PAUSE_SECONDS = timedelta(seconds=120)
AUCTION_DATA = {
    'simple': {'path': os.path.join(PWD, 'data', 'tender_simple.json'),
               'data': read_file_from_json(os.path.join(
                   PWD, 'data', 'tender_simple.json')
               )},
    'multilot': {'path': os.path.join(PWD, 'data', 'tender_multilot.json'),
                 'data': read_file_from_json(
                     os.path.join(PWD, 'data', 'tender_multilot.json')
                 )}
}


def Any(cls):
    class Any(cls):
        def __eq__(self, other):
            return True
    return Any()

ID = 'UA-11111'
LOT_ID = '11111111111111111111111111111111'
API_EXTRA = {'opt_fields': 'status,auctionPeriod,lots,procurementMethodType',
             'mode': '_all_'}
CONF_FILES_FOLDER = os.path.join(PWD, "data")


# with open('data/public_document.json') as _file:
#     test_public_document = json.load(_file)


@contextlib.contextmanager
def update_auctionPeriod(path, auction_type='simple',
                         time_shift=PAUSE_SECONDS):
    new_start_time = (datetime.now(tzlocal()) + time_shift).isoformat()
    with open(path) as file:
        data = json.loads(file.read())
    if auction_type == 'multilot':
        for lot in data['data']['lots']:
            lot['auctionPeriod']['startDate'] = new_start_time
    else:
        data['data']['auctionPeriod']['startDate'] = new_start_time

    with tempfile.NamedTemporaryFile(delete=False) as auction_file:
        json.dump(data, auction_file)
        auction_file.seek(0)
    yield auction_file.name
    auction_file.close()


worker_defaults_file_path = \
    os.path.join(CONF_FILES_FOLDER, "auction_worker_defaults.yaml")
with open(worker_defaults_file_path) as stream:
    worker_defaults = yaml.load(stream)

chronograph_conf_file_path = \
    os.path.join(CONF_FILES_FOLDER, 'auctions_chronograph.yaml')
with open(chronograph_conf_file_path) as stream:
    test_chronograph_config = yaml.load(stream)
    test_chronograph_config['handlers']['journal']['formatter'] = 'simple'
    test_chronograph_config['main']['auction_worker'] = \
        os.path.join(PWD, (".." + os.path.sep)*5, "bin", "auction_worker")
    test_chronograph_config['main']['auction_worker_config'] = \
        os.path.join(PWD, 'data', 'auction_worker_defaults.yaml')
    test_chronograph_config['main'] \
    ['auction_worker_config_for_api_version_dev'] = \
        os.path.join(PWD, 'data', 'auction_worker_defaults.yaml')

databridge_conf_file_path = \
    os.path.join(CONF_FILES_FOLDER, 'auctions_data_bridge.yaml')
with open(databridge_conf_file_path) as stream:
    test_bridge_config = yaml.load(stream)
    test_bridge_config['main']['resource_api_server'] = \
        'http://127.0.0.1:6543/'
    test_bridge_config['handlers']['journal']['formatter'] = 'simple'

test_bridge_config_error_port = deepcopy(test_bridge_config)
couch_url = test_bridge_config_error_port['main']['couch_url']
error_port = str(int(couch_url.split(':')[-1][:-1]) + 1)
couch_url_parts = couch_url.split(':')[0:-1]
couch_url_parts.append(error_port)
test_bridge_config_error_port['main']['couch_url'] = ':'.join(couch_url_parts)


@contextlib.contextmanager
def put_test_doc(db, doc):
    id, rev = db.save(doc)
    yield id
    del db[id]


class TestClient(Sess):
    def __init__(self, pref):
        super(self.__class__, self).__init__()
        LOGGER.info('inside TestClient. pref = {}'.format(pref))
        self.pref = pref

    def get(self, url, **kwargs):
        return super(self.__class__, self)\
            .get('/'.join([self.pref, url]), **kwargs)


class DummyTrue(object):
    def __init__(self):
        self.ind = True

    def __nonzero__(self):
        return self.ind


def iterview_wrappper(server_url, database_name, view_name,
                      sleep_seconds=0.4, wrapper=None, **options):
    return iterview(server_url, database_name, view_name,
                    sleep_seconds=sleep_seconds,
                    wrapper=wrapper, **options)


# Data for test with 'active.auction' status
tender_data_templ = {'id': ID, 'status': 'active.auction'}
tender_data_wrong_status = {'id': ID, 'status': 'wrong.status'}

# Data for test with 'active.qualification' status
tender_data_active_qualification_status = \
    {'id': ID, 'status': 'active.qualification'}

# Data for test with 'cancelled' status
tender_data_cancelled = {'id': ID, 'status': 'cancelled'}

# Data for positive tests
# Data for test with auction periods
tender_in_past_data = deepcopy(tender_data_templ)
tender_in_past_data['auctionPeriod'] = \
    {'startDate': '2017-06-28T10:32:19.233669+03:00'}

# Data for test with 'active.auction' status and no lots
tender_data_active_auction_no_lots = deepcopy(tender_data_templ)
tender_data_active_auction_no_lots['auctionPeriod'] = \
    {'startDate': '2100-06-28T10:32:19.233669+03:00'}

# Data for test with 'active.auction' status and with lots
tender_data_active_auction_with_lots = deepcopy(tender_data_templ)
tender_data_active_auction_with_lots['auctionPeriod'] = \
    {'startDate': '2017-06-28T10:32:19.233669+03:00'}
tender_data_active_auction_with_lots['lots'] = \
    [{'id': LOT_ID, 'status': 'active', 'auctionPeriod':
        {'startDate': '2100-06-28T10:32:19.233669+03:00'}
      }]

# Data for test with 'active.qualification' status
tender_data_active_qualification = \
    deepcopy(tender_data_active_qualification_status)
tender_data_active_qualification['lots'] = \
    [{'id': LOT_ID, 'status': 'active'}]

# Data for test with 'cancelled' status and with lots
tender_data_cancelled_with_lots = deepcopy(tender_data_cancelled)
tender_data_cancelled_with_lots['lots'] = \
    [{'id': LOT_ID, 'status': 'active'}]

# Data for test with 'cancelled' status and no lots
tender_data_cancelled_no_lots = deepcopy(tender_data_cancelled)

# Data for negative tests
# Data for test with 'active.auction' status, no lots and wrong data
tender_data_active_auction_wrong_startDate = deepcopy(tender_data_templ)
tender_data_active_auction_wrong_startDate['auctionPeriod'] = \
    {'startDate': '2017-06-28T10:32:19.233669+03:00'}

# Data for test with 'active.auction' status, no lots and re_planning
tender_data_re_planning = deepcopy(tender_data_templ)
tender_data_re_planning['auctionPeriod'] = \
    {'startDate': '2100-06-28T10:32:19.233669+03:00'}

# Data for test with 'active.auction' status, no lots and
# planned_on_the_same_date
tender_data_planned_on_the_same_date = deepcopy(tender_data_templ)
tender_data_planned_on_the_same_date['auctionPeriod'] = \
    {'startDate': '2100-06-28T10:32:19.233669+03:00'}

# Data for test with 'active.qualification' status and not active status in lot
tender_data_active_qualification_no_active_lot = \
    deepcopy(tender_data_active_qualification_status)
tender_data_active_qualification_no_active_lot['lots'] = \
    [{'id': LOT_ID, 'status': 'deleted'}]

tender_data_active_auction = {
    'tender_in_past_data': tender_in_past_data,
    'tender_data_no_lots': tender_data_active_auction_no_lots,
    'tender_data_with_lots': tender_data_active_auction_with_lots,
    'wrong_startDate': tender_data_active_auction_wrong_startDate,
    're_planning': tender_data_re_planning,
    'planned_on_the_same_date': tender_data_planned_on_the_same_date,
}
tender_data_active_qualification = {
    'tender_data_active_qualification': tender_data_active_qualification,
    'no_active_status_in_lot': tender_data_active_qualification_no_active_lot
}
tender_data_cancelled = {
    'tender_data_with_lots': tender_data_cancelled_with_lots,
    'tender_data_no_lots': tender_data_cancelled_no_lots,
}


def get_tenders_dummy(tender_data_list):
    class GetTenders(object):
        ind = 0

        def iterator(self, tender_list):
            for elem in tender_list:
                self.ind += 1
                yield elem

        def __call__(self, *args, **kwargs):
            return self.iterator(tender_data_list)

    a = GetTenders()
    return a


# TODO: change host
test_client = \
    TestClient('http://0.0.0.0:{port}'.
               format(port=test_chronograph_config['main'].get('web_app')))


def job_is_added():
    resp = test_client.get('jobs')
    return len(json.loads(resp.content)) == 1


def job_is_not_added():
    resp = test_client.get('jobs')
    return len(json.loads(resp.content)) == 0


def job_is_active():
    resp = test_client.get('active_jobs')
    return len(json.loads(resp.content)) == 1


def job_is_not_active():
    resp = test_client.get('active_jobs')
    return len(json.loads(resp.content)) == 0
