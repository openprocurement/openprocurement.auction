# TODO: test chronograph config
import webtest
import pytest
from requests import Session
from gevent import spawn

from openprocurement.auction.chronograph import AuctionsChronograph
from openprocurement.auction.tests.unit.utils import put_test_doc, \
    test_public_document, \
    update_start_auction_period

test_chronograph_config = {}


@pytest.fixture(scope='function')
def chronograph(request):
    # webapp = true
    chrono = AuctionsChronograph(test_chronograph_config)
    client = Session()  # TODO: Add prefix path
    return {'chronograph': chrono, 'client': client}


class TestChronograph(object):
    def test_view_job_add(self, chronograph):
        spawn(chronograph['chronograph'].run)
        with put_test_doc(some_db,
                          update_start_auction_period(test_public_document)):
            resp = chronograph['client'].get('/jobs')
            assert resp

    def test_listing(self, chronograph):
        spawn(chronograph['chronograph'].run)
        with put_test_doc(some_db,
                          update_start_auction_period(test_public_document)):
            resp = chronograph['client'].get('/active_jobs')
            assert resp

    def test_shutdown(self, chronograph):
        resp = self.client.get('/active_jobs')
        assert resp.test == "Start shutdown"


