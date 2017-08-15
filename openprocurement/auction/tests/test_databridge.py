# See: openprocurement.auction.core.Planning
import pytest

from openprocurement.auction.databridge import AuctionsDatabridge
from openprocurement.auction.tests.utils import MockFeedItem


test_config = {}


@pytest.fixture(scope='function')
def bridge(request):
    # TODO:
    # Mock supbrocess && get_tedners
    request.cls.bridge = AuctionsDatabridge(test_config)


class TestDatabridge(self):
    """
    check with different data for 'plannign' 'cancel'
    with lot_id no lot_id
    """
    def test_active_auction_no_lots(self):
        """TODO: """

    def test_active_auction_with_lots(self):
        """TODO: """

    def test_announce(self):
        """Only multilot tenders in auction.qualification status"""

    def test_cancel(self):
        """Auction has been cancelled"""
