import pytest
from openprocurement.auction.server import run_server
from openprocurement.auction.tests.utils import MockAuction, MockClient, \
    MockLogger

def server(request):
    auction = MockAuction()
    server = run_server(MockAuction(), 10000, MockLogger())
    request.cls.server = server
    request.cls.client = MockClient(server)
    return server


@pytest.mark.usefixtures('server')
class TestAuctionSever(object):


  def test_login(self):
      data = "invalid data here"
      with self.client.get('/login', data=data) as resp:
          assert resp.status == 401

      # mock patch oauth server
      with self.client.get('/login', data=data) as resp:
          assert resp.status == 302
          # TODO
          # assert  /oauth/authorize in resp.heades["location"]

    # mock.path oauth server
    def test_authorized(self):
        """TODO: """

    def test_check_authorization(self):
        # TODO:
        data = bidder_data_invalid
        with self.client.post('/check_authorization', data=data) as resp:
            assert resp.status ==  401

        data = bidder_data_valid
        with self.client.post('/check_authorization', data=data) as resp:
            assert resp.json == {"status": "ok"}
    
    def test_relogin(self):
        data = invalid_bidder_data
        with self.client.get('/relogin', data=data) as resp:
            assert resp.status == 302
            assert resp.headers['Location'] = '/'

        data = valid_bidder_data
        with self.client.get('/relogin', data=data) as resp:
            assert resp.status == 302
            assert "authorized" in resp.headers['Location']

    def test_kickclient(self):
        data = bidder_data_invalid
        with self.client.get('/kickclient', data=data) as resp:
            assert resp.status = 401

        data = bidder_data_valid
        with self.client.post('/kickclient', data=data) as resp:
            assert resp.json == {"status": "ok"}
    
    # mock_auction
    def test_postbid(self)
        data = invalid_post_data
        # All possible invalid values
        with client.post('/postbid', data=data) as resp:
            assert resp.json == {'status': 'failed', 'errors': "*See wft forms and forms.py*"}

        with client.post('/postbid', data=data) as resp:
            assert resp.json == {'status': 'ok', 'data': data}

        unathorized = invalid_data
        with client.post('/postbid', data=data) as resp:
            assert resp.status == 401

    def test_sse_timeout(self):
        # TODO
        data_for_auth = some_data
        with self.client.post('/set_sse_timeout', data=data_for_auth) as resp:
            assert resp.status == 200
            assert resp.json == {'timeout': data_for_auth['timeout']}

    def test_event_source(self):
        resp = {}
        # TODO:
        # authorize
        # connect to /event_source
        # check messages Tick, Identification, Client list, KickClient, New client
        # https://pypi.python.org/pypi/sseclient/
