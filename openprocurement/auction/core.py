import logging
from zope.interface import implementer
from pkg_resources import iter_entry_points

from openprocurement.auction.components import components
from openprocurement.auction.auction_runner import AuctionsRunner
from openprocurement.auction.interfaces import IFeedItem, IAuctionDatabridge,\
    IAuctionManager, IAuctionsRunner, IAuctionType


PKG_NAMESPACE = "openprocurement.auction.plugins"
LOGGER = logging.getLogger(__name__)


@components.adapter(
    provides=IAuctionsRunner, adapts=(IAuctionDatabridge, IFeedItem)
)
@implementer(IAuctionManager)
class AuctionManager(object):

    def __init__(self, databridge, feed):
        self.databridge = databridge
        self.feed_item = feed
        plugins = self.databridge.config_get('plugins') or []

        # TODO: check me
        for entry_point in iter_entry_points(PKG_NAMESPACE):
            LOGGER.info("Loading {} plugin".format(entry_point.name))
            plugin = entry_point.load()
            plugin(components)

    def __call__(self):
        # TODO:
        auction_iface = components.queryUtility(IAuctionsRunner)
        if not auction_iface:
            # DEBUG:
            print "{} skipped".format(self.feed_item.get('procurementMethodType'))
            return None
        return components.queryMultiAdapter(
            (self.databridge, self.feed_item),
            auction_iface
        )
