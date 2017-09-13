from gevent import monkey

monkey.patch_all()

from collections import deque
from couchdb import Server, Session
from design import sync_design
from json import loads
from memoize import Memoizer
from pytz import timezone as tz
from restkit.conn import Connection
from socketpool import ConnectionPool
from pkg_resources import iter_entry_points
from urlparse import urljoin

from openprocurement.auction.core import components
from openprocurement.auction.interfaces import IAuctionsServer
from openprocurement.auction.proxy import couch_server_proxy,\
    auth_couch_server_proxy


PKG_NAMESPACE = "openprocurement.auction.auctions"
LIMIT_REPLICATIONS_LIMIT_FUNCTIONS = {
    'any': any,
    'all': all
}


def make_auctions_app(global_conf,
                      redis_url='redis://localhost:9002/1',
                      redis_password='',
                      redis_database='',
                      sentinel_cluster_name='',
                      sentinels='',
                      external_couch_url='http://localhost:5000/auction',
                      internal_couch_url='http://localhost:9000/',
                      proxy_internal_couch_url='http://localhost:9000/',
                      auctions_db='database',
                      hash_secret_key='',
                      timezone='Europe/Kiev',
                      preferred_url_scheme='http',
                      debug=False,
                      auto_build=False,
                      event_source_connection_limit=1000,
                      limit_replications_progress=99,
                      limit_replications_func='any'
                      ):
    """
    [app:main]
    use = egg:openprocurement.auction#auctions_server
    redis_url = redis://:passwod@localhost:1111/0
    external_couch_url = http://localhost:1111/auction
    internal_couch_url = http://localhost:9011/
    auctions_db = auction
    timezone = Europe/Kiev
    """
    auctions_server = components.queryUtility(IAuctionsServer)
    auctions_server.proxy_connection_pool = ConnectionPool(
        factory=Connection, max_size=20, backend="gevent"
    )
    auctions_server.proxy_mappings = Memoizer({})
    auctions_server.event_sources_pool = deque([])
    auctions_server.config['PREFERRED_URL_SCHEME'] = preferred_url_scheme
    auctions_server.config['limit_replications_progress'] = float(
        limit_replications_progress
    )
    auctions_server.config['limit_replications_func'] = limit_replications_func

    auctions_server.config['REDIS'] = {
        'redis': redis_url,
        'redis_password': redis_password,
        'redis_database': redis_database,
        'sentinel_cluster_name': sentinel_cluster_name,
        'sentinel': loads(sentinels)
    }

    auctions_server.config['event_source_connection_limit'] = int(
        event_source_connection_limit
    )
    auctions_server.config['EXT_COUCH_DB'] = urljoin(
        external_couch_url,
        auctions_db
    )
    auctions_server.add_url_rule(
        '/' + auctions_db + '/<path:path>',
        'couch_server_proxy',
        couch_server_proxy,
        methods=['GET'])
    auctions_server.add_url_rule(
        '/' + auctions_db + '/',
        'couch_server_proxy',
        couch_server_proxy,
        methods=['GET'], defaults={'path': ''})

    auctions_server.add_url_rule(
        '/' + auctions_db + '_secured/<path:path>',
        'auth_couch_server_proxy',
        auth_couch_server_proxy,
        methods=['GET'])
    auctions_server.add_url_rule(
        '/' + auctions_db + '_secured/',
        'auth_couch_server_proxy',
        auth_couch_server_proxy,
        methods=['GET'], defaults={'path': ''})

    auctions_server.config['INT_COUCH_URL'] = internal_couch_url
    auctions_server.config['PROXY_COUCH_URL'] = proxy_internal_couch_url
    auctions_server.config['COUCH_DB'] = auctions_db
    auctions_server.config['TIMEZONE'] = tz(timezone)

    auctions_server.couch_server = Server(
        auctions_server.config.get('INT_COUCH_URL'),
        session=Session(retry_delays=range(10))
    )
    if auctions_server.config['COUCH_DB'] not in auctions_server.couch_server:
        auctions_server.couch_server.create(auctions_server.config['COUCH_DB'])

    auctions_server.db = auctions_server.couch_server[auctions_server.config['COUCH_DB']]
    auctions_server.config['HASH_SECRET_KEY'] = hash_secret_key
    sync_design(auctions_server.db)
    for entry_point in iter_entry_points(PKG_NAMESPACE):
        plugin = entry_point.load()
        plugin(components)
    return auctions_server
