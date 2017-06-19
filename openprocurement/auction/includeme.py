from zope.interface.interface import InterfaceClass
from zope.interface import implementer, Interface

from openprocurement.auction.auction_runner import AuctionsRunner,\
        MultilotAuctionRunner
from openprocurement.auction.constants import DEFAULT_PROCUREMENT_METHOD_TYPES
from openprocurement.auction.predicates import ProcurementMethodType, KeyIn 
from openprocurement.auction.interfaces import IFeedItem, IAuctionDatabridge


def includeme(components):
    if not components.contains_pred('procurementMethodType'):
        components.add_predicate('procurementMethodType', ProcurementMethodType)

    for procurement_method_type in DEFAULT_PROCUREMENT_METHOD_TYPES:
        iface = InterfaceClass(
            "{}_ISimpleAuction".format(procurement_method_type),
            bases=(Interface,)
        )
        components.add_auction(
            iface,
            procurementMethodType=procurement_method_type
        )
        components.registerAdapter(
            implementer(iface)(AuctionsRunner),
            (IAuctionDatabridge, IFeedItem),
            iface
        )


def includeme2(components):
    if not components.contains_pred('procurementMethodType'):
        components.add_predicate('procurementMethodType', ProcurementMethodType)

    components.add_predicate('match_key', KeyIn)
    for procurement_method_type in DEFAULT_PROCUREMENT_METHOD_TYPES:
        iface = InterfaceClass(
            "{}_IMultilotAuction".format(procurement_method_type),
            bases=(Interface,)
        )
        components.add_auction(iface,
                               procurementMethodType=procurement_method_type,
                               match_key="lots")
        components.registerAdapter(
            implementer(iface)(MultilotAuctionRunner),
            (IAuctionDatabridge, IFeedItem),
            iface
        )
