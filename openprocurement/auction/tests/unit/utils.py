import contextlib
from requests import Session as Sess
import signal, psutil
import os
from copy import deepcopy


ID = 'UA-11111'
LOT_ID = '11111111111111111111111111111111'


@contextlib.contextmanager
def put_test_doc(db, doc):
    id, rev = db.save(doc)
    yield id
    del db[id]


class TestClient(Sess):
    def __init__(self, pref):
        super(self.__class__, self).__init__()
        self.pref = pref

    def get(self, url, **kwargs):
        return super(self.__class__, self)\
            .get('/'.join([self.pref, url]), **kwargs)


def kill_child_processes(parent_pid=os.getpid(), sig=signal.SIGTERM):
    try:
        parent = psutil.Process(parent_pid)
    except psutil.NoSuchProcess:
        return
    children = parent.children(recursive=True)
    for process in children:
        process.send_signal(sig)

# = = = = = = = = = Data for different statuses = = = = = = = = =
# Data for test with 'active.auction' status
tender_data_templ = {'id': ID, 'status': 'active.auction'}
tender_data_wrong_status = {'id': ID, 'status': 'wrong.status'}

# Data for test with 'active.qualification' status
tender_data_active_qualification_status = {'id': ID, 'status': 'active.qualification'}

# Data for test with 'cancelled' status
tender_data_cancelled = {'id': ID, 'status': 'cancelled'}
# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =

# = = = = = = = = = Data for positive tests = = = = = = = = = = = = =
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
tender_data_active_qualification = deepcopy(tender_data_active_qualification_status)
tender_data_active_qualification['lots'] = \
    [{'id': LOT_ID, 'status': 'active'}]

# Data for test with 'cancelled' status and with lots
tender_data_cancelled_with_lots = deepcopy(tender_data_cancelled)
tender_data_cancelled_with_lots['lots'] = \
    [{'id': LOT_ID, 'status': 'active'}]

# Data for test with 'cancelled' status and no lots
tender_data_cancelled_no_lots = deepcopy(tender_data_cancelled)
# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =

# = = = = = = = = = Data for negative tests = = = = = = = = = = = = =
# Data for test with 'active.auction' status, no lots and wrong data
tender_data_active_auction_wrong_startDate = deepcopy(tender_data_templ)
tender_data_active_auction_wrong_startDate['auctionPeriod'] = \
    {'startDate': '2017-06-28T10:32:19.233669+03:00'}

# Data for test with 'active.auction' status, no lots and re_planning
tender_data_re_planning = deepcopy(tender_data_templ)
tender_data_re_planning['auctionPeriod'] = \
    {'startDate': '2100-06-28T10:32:19.233669+03:00'}

# Data for test with 'active.auction' status, no lots and planned_on_the_same_date
tender_data_planned_on_the_same_date = deepcopy(tender_data_templ)
tender_data_planned_on_the_same_date['auctionPeriod'] = \
    {'startDate': '2100-06-28T10:32:19.233669+03:00'}

# Data for test with 'active.qualification' status and not active status in lot
tender_data_active_qualification_no_active_lot = deepcopy(tender_data_active_qualification_status)
tender_data_active_qualification_no_active_lot['lots'] = \
    [{'id': LOT_ID, 'status': 'deleted'}]
# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =

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


def get_tenders_dummy(tender_data_list, *args, **kwargs):
    class GetTenders(object):
        ind = 0

        @classmethod
        def iterator(self, tender_data_list):
            for elem in tender_data_list:
                self.ind += 1
                yield elem

        def __call__(self, *args, **kwargs):
            return self.iterator(tender_data_list)

    a = GetTenders()
    return a


def check_call_dummy(*args, **kwargs):
    pass


API_EXTRA = {'opt_fields': 'status,auctionPeriod,lots,procurementMethodType', 'mode': '_all_'}
