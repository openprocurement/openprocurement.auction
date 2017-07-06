from zope.interface import Interface
from zope.interface.interface import InterfaceClass

from openprocurement.auction.core import RunDispatcher, Planning 
from openprocurement.auction.interfaces import IFeedItem, IAuctionDatabridge, IAuctionsChronograph


def _register(components, procurement_method_type):
    iface = InterfaceClass("I{}Auction".format(procurement_method_type),
                           bases=(Interface,))
    components.add_auction(iface,
                           procurementMethodType=procurement_method_type)
    components.registerAdapter(Planning, (IAuctionDatabridge, IFeedItem), iface)
    components.registerAdapter(RunDispatcher, (IAuctionsChronograph, IFeedItem), iface)   


def default(components):
    _register(components, 'default')


def belowThreshold(components):
    _register(components, 'belowThreshold')


def aboveThresholdUA(components):
    _register(components, 'aboveThresholdUA')


def aboveThresholdEU(components):
    _register(components, 'aboveThresholdEU')


def competitiveDialogueEU(components):
    _register(components, 'competitiveDialogueEU.stage2')


def competitiveDialogueUA(components):
    _register(components, 'competitiveDialogueUA.stage2')


def aboveThresholdUAdefense(components):
    _register(components, 'aboveThresholdUA.defense')
