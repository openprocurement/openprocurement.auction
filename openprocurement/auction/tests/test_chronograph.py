# TODO: test chronograph config
import webtest
import pytest
from requests import Session
from gevent import spawn

from openprocurement.auction.chronograph import AuctionsChronograph
from openprocurement.auction.tests.utils import put_test_doc, test_public_document,\
    update_start_auction_period

test_chronograph_config = {}


def chronograph(request):
    # webapp = true
    chrono = AuctionsChronograph(test_chronograph_config)
    request.cls.chrono = chrono
    request.cls.client = Session() # TODO: Add prefix path
    return chrono



@pytest.mark.usefixtures('chronograph')
class TestChronograph(object):
    pass
