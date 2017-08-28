import contextlib
from requests import Session as Sess
import signal, psutil
import os
from copy import deepcopy


ID = 'UA-11111'


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


tender_data_templ = {'id': ID, 'status': 'active.auction'}
tender_data_wrong_status = {'id': ID, 'status': 'wrong.status'}

tender_in_past_data = deepcopy(tender_data_templ)
tender_in_past_data['auctionPeriod'] = \
    {'startDate': '2017-06-28T10:32:19.233669+03:00'}

tender_data_active_auction_no_lots = deepcopy(tender_data_templ)
tender_data_active_auction_no_lots['auctionPeriod'] = \
    {'startDate': '2100-06-28T10:32:19.233669+03:00'}

# TODO: make appropriate changes!!!
tender_data_active_auction_with_lots = deepcopy(tender_data_templ)


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
