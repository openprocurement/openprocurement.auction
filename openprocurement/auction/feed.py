from munch import Munch
from zope.interface import implementer
from openprocurement.auction.interfaces import IFeedItem


@implementer(IFeedItem)
class FeedItem(Munch):
    """"""
