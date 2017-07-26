# TODO: test chronograph config
from gevent import spawn, sleep
import json


class TestClient(object):
    """TODO: """


class TestChronograph(object):
    def test_view_job_add(self, db, chronograph, auction):
        auction.prepare_auction_document()
        sleep(0.1)
        resp = chronograph['client'].get("http://0.0.0.0:9005/jobs")
        one_job_is_added = True if len(json.loads(resp.content)) == 1 else False

        assert one_job_is_added is True

    # def test_listing(self, chronograph, db):
    #     spawn(chronograph['chronograph'].run)
    #     with put_test_doc(db, update_auctionPeriod(test_public_document)):
    #         resp = chronograph['client'].get('/active_jobs')
    #         assert resp

    # def test_shutdown(self, chronograph):
    #     resp = self.client.get('/active_jobs')
    #     assert resp.test == "Start shutdown"

