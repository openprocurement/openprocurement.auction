import pytest
from openprocurement.auction.helpers.chronograph \
    import MAX_AUCTION_START_TIME_RESERV
import datetime
from openprocurement.auction.tests.unit.utils import job_is_added, \
    job_is_not_added, job_is_active, job_is_not_active
from time import sleep as blocking_sleep


class TestChronograph(object):
    def test_view_job_not_add(self, db, chronograph, auction):

        # We use it here and in all tests below as initial couch view function
        # call triggers db indexation. It takes unpredictable amount of time
        # and it is worth to call it here rather than in test (actually run
        # function of chronograph instance).
        # Tests are unstable and sometimes fails without this call
        db.view('chronograph/start_date')

        # chronograph.join(1) is used here instead of nonblocking gevent.sleep
        # as sleep(1) doesn't necessary switch running thread to the
        # chronograph.run, Whereas chronograph.join(1) does.
        # If use sleep(1) instead of chronograph.join(1) tests becomes
        # unstable and sometimes fails.
        chronograph.join(1)

        assert job_is_not_added()
        assert job_is_not_active()

    def test_view_job_add(self, db, chronograph, auction):
        auction.prepare_auction_document()
        db.view('chronograph/start_date')

        chronograph.join(0.5)

        assert job_is_not_added()
        assert job_is_active()

    @pytest.mark.parametrize(
        'auction',
        [({'time': MAX_AUCTION_START_TIME_RESERV,
           'delta_t': datetime.timedelta(seconds=3)})], indirect=['auction'])
    def test_listing(self, db, chronograph, auction):
        auction.prepare_auction_document()
        db.view('chronograph/start_date')

        chronograph.join(0.1)

        assert job_is_added()
        assert job_is_not_active()

        blocking_sleep(3.4)
        assert job_is_not_added()
        assert job_is_active()

    # TODO: this test needs dummy auction_worker
    # from openprocurement.auction.tests.unit.utils import test_client
    # def test_shutdown(self, log_for_test, db, chronograph, auction):
    #     auction.prepare_auction_document()
    #     db.view('chronograph/start_date')
    #
    #     chronograph.join(0.5)
    #
    #     i = 0
    #     while (not job_is_active()) and i < 10:
    #         blocking_sleep(0.1)
    #         i += 1
    #
    #     if not job_is_active():
    #         raise ValueError('Job is not active and can not be shut down')
    #
    #     # chronograph.server.stop()
    #     log_for_test.debug('OK')
    #     resp = test_client.get('shutdown')
    #     sleep(0.5)
    #     import pdb; pdb.set_trace()
    #     assert resp.status_code == 200
    #     assert resp.text == '"Start shutdown"'
    #
