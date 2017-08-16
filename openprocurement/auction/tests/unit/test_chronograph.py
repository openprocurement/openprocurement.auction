# TODO: test chronograph config

# pdb.set_trace = lambda: None

from gevent import sleep
import json
import pytest
from openprocurement.auction.helpers.chronograph \
    import MAX_AUCTION_START_TIME_RESERV, MIN_AUCTION_START_TIME_RESERV
import datetime


class TestChronograph(object):
    def test_view_job_add(self, log_for_test, db, chronograph, auction):
        auction.prepare_auction_document()
        sleep(0.1)
        resp = chronograph['client'].get('jobs')
        one_job_is_added = True if len(json.loads(resp.content)) == 1 \
            else False

        assert one_job_is_added is True

    @pytest.mark.parametrize(
        'auction',
        [({'time': MAX_AUCTION_START_TIME_RESERV,
           'delta_t': datetime.timedelta(seconds=3)})], indirect=['auction'])
    def test_listing(self, db, chronograph, auction):
        auction.prepare_auction_document()
        sleep(65)
        resp = chronograph['client'].get('active_jobs')
        job_is_active = (len(json.loads(resp.content)) == 1)
        assert job_is_active

    # def test_shutdown(self, chronograph):
    #     resp = self.client.get('shutdown')
    #     assert resp.test == "Start shutdown"

