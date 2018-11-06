import pytest
import uuid
import os
from couchdb import Server

from openprocurement.auction.design import sync_design_chronograph, sync_design
from openprocurement.auction.tests.utils import test_public_document, put_test_doc

COUCHDB_HTTP_HOST = os.environ.get('COUCHDB_HTTP_HOST', '127.0.0.1')
COUCHDB_HTTP_PORT = os.environ.get('COUCHDB_HTTP_PORT', '9000')
COUCHDB_USER = os.environ.get('COUCHDB_USER', 'admin')
COUCHDB_PASSWORD = os.environ.get('COUCHDB_PASSWORD', 'zaq1xsw2')

SERVER = Server(
    'http://{}:{}@{}:{}'.format(
        COUCHDB_USER,
        COUCHDB_PASSWORD,
        COUCHDB_HTTP_HOST,
        COUCHDB_HTTP_PORT
    )
)


@pytest.fixture(scope='function')
def db(request):
    name = 'test_{}'.format(uuid.uuid4().hex)
    db = SERVER.create(name)
    sync_design_chronograph(db)
    sync_design(db)
    request.cls.db = db
    request.addfinalizer(lambda: SERVER.delete(name))
    return db


@pytest.mark.usefixtures('db')
class TestViews(object):

    def test_chronograph_view(self):
        with put_test_doc(self.db, test_public_document):
            data = next(iter(self.db.view('chronograph/start_date').rows))
            assert not set(data.get('value').keys()).difference(
                set(['start', 'mode', 'api_version', 'auction_type', 'procurementMethodType']))

    def test_start_date_view(self):
        """see: https://github.com/openprocurement/openprocurement.auction/blob/master/openprocurement/auction/design.py#L18"""

    def test_end_date_view(self):
        """see: https://github.com/openprocurement/openprocurement.auction/blob/master/openprocurement/auction/design.py#L8"""

    def test_pre_announce_view(self):
        """https://github.com/openprocurement/openprocurement.auction/blob/master/openprocurement/auction/design.py#L31"""
