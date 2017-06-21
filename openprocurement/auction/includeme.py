from zope.interface import implementer, Interface
from zope.interface.interface import InterfaceClass
from openprocurement.auction.auction_runner import AuctionsRunner, AuctionsPlanner
from openprocurement.auction.constants import DEFAULT_PROCUREMENT_METHOD_TYPES
from openprocurement.auction.predicates import ProcurementMethodType
from openprocurement.auction.interfaces import IFeedItem, IAuctionDatabridge, IAuctionsChronograph,IDBData
from openprocurement.auction.components import components


def includeme(procurement_method_type):
    iface = InterfaceClass( "I{}Auction".format(procurement_method_type),
                            bases=(Interface,))
    components.add_auction(iface,
                           procurementMethodType=procurement_method_type)
    components.registerAdapter(AuctionsPlanner, (IAuctionDatabridge, IFeedItem), iface)
    components.registerAdapter(AuctionsRunner, (IAuctionsChronograph, IFeedItem), iface)
