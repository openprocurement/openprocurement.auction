# TODO: test chronograph config

from gevent import sleep
import pytest
from openprocurement.auction.helpers.chronograph \
    import MAX_AUCTION_START_TIME_RESERV
import datetime
from openprocurement.auction.tests.unit.utils import job_is_added, \
    job_is_not_added, job_is_active, job_is_not_active


class TemplateTestChronograph(object):
    def test_view_job_not_add(self, db, chronograph, auction):
        sleep(1)
        assert job_is_not_added()
        assert job_is_not_active()

    # def test_view_job_add(self, log_for_test, db, chronograph, auction):
    #     auction.prepare_auction_document()
    #     sleep(1)
    #
    #     assert job_is_added()
    #     assert job_is_not_active()

    @pytest.mark.parametrize(
        'auction',
        [({'time': MAX_AUCTION_START_TIME_RESERV,
           'delta_t': datetime.timedelta(seconds=3)})], indirect=['auction'])
    def test_listing(self, db, chronograph, auction):
        auction.prepare_auction_document()
        sleep(0.5)

        assert job_is_added()
        assert job_is_not_active()

        sleep(65)
        assert job_is_not_added()
        assert job_is_active()


    # def test_shutdown(self, chronograph):
    #     resp = self.client.get('shutdown')
    #     assert resp.test == "Start shutdown"

