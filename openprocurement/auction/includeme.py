from zope.interface import Interface
from zope.interface.interface import InterfaceClass

from openprocurement.auction.core import AuctionsRunner, AuctionsPlanner
from openprocurement.auction.interfaces import IFeedItem, IAuctionDatabridge, IAuctionsChronograph
from openprocurement.auction.components import components


def includeme(procurement_method_type):
    iface = InterfaceClass("I{}Auction".format(procurement_method_type),
                           bases=(Interface,))
    components.add_auction(iface,
                           procurementMethodType=procurement_method_type)
    components.registerAdapter(AuctionsPlanner, (IAuctionDatabridge, IFeedItem), iface)
    components.registerAdapter(AuctionsRunner, (IAuctionsChronograph, IFeedItem), iface)
