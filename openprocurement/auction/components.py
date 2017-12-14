import logging
from zope import interface
from zope.interface import registry
from walkabout import PredicateDomain, PredicateMismatch

from openprocurement.auction.interfaces import IComponents, IAuctionType, IFeedItem


LOGGER = logging.getLogger(__name__)


@interface.implementer(IComponents)
class AuctionComponents(registry.Components):

    def __init__(self, *args, **kw):
        super(AuctionComponents, self).__init__(*args, **kw)
        self._dispatch = PredicateDomain(IAuctionType, self)

    def add_predicate(self, *args, **kw):
        self._dispatch.add_predicate(*args, **kw)

    def add_auction(self, iface, **preds):
        self._dispatch.add_candidate(iface, IFeedItem, **preds)

    def match(self, inst):
        try:
            return self._dispatch.lookup(inst)
        except PredicateMismatch:
            pass

    def adapter(self, provides, adapts, name=""):
        """ TODO: create decorator for such thinks """

        if not isinstance(adapts, (tuple, list)):
            adapts = (adapts,)

        def wrapped(wrapper):

            self.registerAdapter(
                wrapper,
                adapts,
                provides,
                name=name
            )
            return wrapper

        return wrapped

    def qA(self, obj, iface, name=''):
        return self.queryAdapter(obj, iface, name=name)

    def q(self, iface, name='', default=''):
        """ TODO: query the component by 'iface' """
        return self.queryUtility(iface, name=name, default=default)
