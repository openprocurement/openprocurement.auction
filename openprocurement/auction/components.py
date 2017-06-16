from zope import interface
from zope.interface import registry, implementedBy
from walkabout import PredicateDomain, PredicateMismatch

from openprocurement.auction.interfaces import IComponents, IAuctionType, IFeedItem


@interface.implementer(IComponents)
class AuctionComponents(registry.Components):

    def __init__(self, *args, **kw):
        super(AuctionComponents, self).__init__(*args, **kw)
        self._dispatch = PredicateDomain(IAuctionType, self)

    def add_predicate(self, *args, **kw):
        self._dispatch.add_predicate(*args)

    def add_auction(self, auction_iface, **preds):
        self._dispatch.add_candidate(
            auction_iface, IFeedItem, **preds
        )

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

    def component(self):
        """ Zope utility regitration decorator """
        def wrapped(Wrapped):
            iface = list(implementedBy(Wrapped))
            if not iface:
                raise ValueError("{} should be marked as interface".format(Wrapped.__name__))
            name = Wrapped.__name__.lower()
            def new(cls, *args, **kw):
                ob = self.queryUtility(iface[0], name=name)
                if not ob:
                    ob = super(Wrapped, cls).__new__(*args, **kw)
                    self.registerUtility(ob, iface[0], name=name)
                return ob
            Wrapped.__new__ = classmethod(new)
            return Wrapped

        return wrapped

    def qA(self, obj, iface, name=''):
        return self.queryAdapter(obj, iface, name=name)
        
    def q(self, iface, name='', default=''):
        """ TODO: query the component by 'iface' """    
        return self.queryUtility(iface, name=name, default=default)

        
components = AuctionComponents()

