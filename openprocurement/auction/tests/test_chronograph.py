# TODO: test chronograph config
import webtest
import pytest
from requests import Session
from gevent import spawn

from openprocurement.auction.chronograph import AuctionsChronograph
from openprocurement.auction.tests.utils import put_test_doc, test_public_document,\
    update_start_auction_period

test_chronograph_config = {}


@pytest.fixture(scope='funtion')
def chronograph(request):
    # webapp = true
    chrono = AuctionsChronograph(test_chronograph_config)
    request.cls.chrono = chrono
    request.client = Session() # TODO: Add prefix path
    return chrono


class TestChronoggraph(object):

    def test_view_job_add(self):
        spawn(self.chrono.run())
        with put_test_dock(some_db, update_start_auction_period(test_public_document)):
            resp = self.client.get('/jobs')
            assert resp

    def test_listing(self):
        spawn(self.chrono.run())
        with put_test_dock(some_db, update_start_auction_period(test_public_document)):
            resp = self.client.get('/active_jobs')
            assert resp

    def test_shutdown(self):
        resp = self.client.get('/active_jobs')
        assert resp.test == "Start shutdown"
