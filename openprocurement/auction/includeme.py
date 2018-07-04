# -*- coding: utf-8 -*-
from zope.interface import Interface
from zope.interface.interface import InterfaceClass

from openprocurement.auction.core import RunDispatcher, Planning
from openprocurement.auction.interfaces import IFeedItem, IAuctionDatabridge, IAuctionsChronograph
from openprocurement.auction.utils import get_logger_for_calling_module


def _register(components, procurement_method_type):
    iface = InterfaceClass("I{}Auction".format(procurement_method_type),
                           bases=(Interface,))
    components.add_auction(iface,
                           procurementMethodType=procurement_method_type)
    components.registerAdapter(Planning, (IAuctionDatabridge, IFeedItem), iface)
    components.registerAdapter(RunDispatcher, (IAuctionsChronograph, IFeedItem), iface)

    # for proper plugin loading logs
    logger = get_logger_for_calling_module()

    logger.info("Included %s plugin" % procurement_method_type,
                extra={'MESSAGE_ID': 'included_plugin'})


def default(components, _):
    _register(components, 'default')
