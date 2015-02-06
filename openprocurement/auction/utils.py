import iso8601
from datetime import MINYEAR, datetime
from pytz import timezone
from gevent import sleep
import logging
import json
import requests
from hashlib import sha1

from gevent.pywsgi import WSGIServer
from gevent.baseserver import parse_address
from redis import Redis
import uuid

EXTRA_LOGGING_VALUES = {
    'X-Request-ID': 'JOURNAL_REQUEST_ID',
    'X-Clint-Request-ID': 'JOURNAL_CLIENT_REQUEST_ID'
}

def generate_request_id(prefix=b'auction-req-'):
    return prefix + str(uuid.uuid4()).encode('ascii')

def filter_by_bidder_id(bids, bidder_id):
    """
    >>> bids = [
    ...     {"bidder_id": "1", "amount": 100},
    ...     {"bidder_id": "1", "amount": 200},
    ...     {"bidder_id": "2", "amount": 101}
    ... ]

    >>> filter_by_bidder_id(bids, "1")
    [{'amount': 100, 'bidder_id': '1'}, {'amount': 200, 'bidder_id': '1'}]

    >>> filter_by_bidder_id(bids, "2")
    [{'amount': 101, 'bidder_id': '2'}]

    """
    return [bid for bid in bids if bid['bidder_id'] == bidder_id]


def filter_start_bids_by_bidder_id(bids, bidder):
    """
    """
    return [bid for bid in bids
            if bid['bidders'][0]['id']['name'] == bidder]


def get_time(item):
    """
    >>> date = get_time({"time": "2015-01-04T15:40:44Z"}) # doctest: +NORMALIZE_WHITESPACE
    >>> date.utctimetuple()  # doctest: +NORMALIZE_WHITESPACE
    time.struct_time(tm_year=2015, tm_mon=1, tm_mday=4, tm_hour=15, tm_min=40,
                     tm_sec=44, tm_wday=6, tm_yday=4, tm_isdst=0)

    >>> date = get_time({"date": "2015-01-04T15:40:44Z"})
    >>> date.utctimetuple()  # doctest: +NORMALIZE_WHITESPACE
    time.struct_time(tm_year=2015, tm_mon=1, tm_mday=4, tm_hour=15, tm_min=40,
                     tm_sec=44, tm_wday=6, tm_yday=4, tm_isdst=0)

    >>> date = get_time({})
    >>> date.utctimetuple()  # doctest: +NORMALIZE_WHITESPACE
    time.struct_time(tm_year=0, tm_mon=12, tm_mday=31, tm_hour=21, tm_min=58,
                     tm_sec=0, tm_wday=6, tm_yday=366, tm_isdst=0)
    """
    if item.get('time', ''):
        bid_time = iso8601.parse_date(item['time'])
    elif item.get('date', ''):
        bid_time = iso8601.parse_date(item['date'])
    else:
        bid_time = datetime(MINYEAR, 1, 1, tzinfo=timezone('Europe/Kiev'))
    return bid_time


def sorting_by_amount(bids, reverse=True):
    """
    >>> bids = [
    ...     {"bidder_id": "1", "amount": 100},
    ...     {"bidder_id": "1", "amount": 200},
    ...     {"bidder_id": "2", "amount": 101}
    ... ]
    >>> sorting_by_amount(bids)  # doctest: +NORMALIZE_WHITESPACE
    [{'amount': 200, 'bidder_id': '1'},
     {'amount': 101, 'bidder_id': '2'},
     {'amount': 100, 'bidder_id': '1'}]

    >>> sorting_by_amount(bids, reverse=False)  # doctest: +NORMALIZE_WHITESPACE
    [{'amount': 100, 'bidder_id': '1'},
     {'amount': 101, 'bidder_id': '2'},
     {'amount': 200, 'bidder_id': '1'}]
    """
    def get_amount(item):
        return item['amount']

    return sorted(bids, key=get_amount, reverse=reverse)


def sorting_start_bids_by_amount(bids, reverse=True):
    """
    >>> from json import load
    >>> import os
    >>> data = load(open(os.path.join(os.path.dirname(__file__),
    ...                               'tests/data/tender_data.json')))
    >>> sorted_data = sorting_start_bids_by_amount(data['data']['bids'])
    >>> sorted_data[0]['value']['amount'] > sorted_data[1]['value']['amount']
    True

    >>> sorted_data = sorting_start_bids_by_amount(data['data']['bids'],
    ...                                            reverse=False)
    >>> sorted_data[0]['value']['amount'] < sorted_data[1]['value']['amount']
    True

    """
    def get_amount(item):
        return item['value']['amount']

    return sorted(bids, key=get_amount, reverse=reverse)


def sorting_by_time(bids, reverse=True):
    return sorted(bids, key=get_time, reverse=reverse)


def get_latest_bid_for_bidder(bids, bidder_id):
    return sorted(filter_by_bidder_id(bids, bidder_id),
                  key=get_time, reverse=True)[0]


def get_latest_start_bid_for_bidder(bids, bidder):
    return sorted(filter_start_bids_by_bidder_id(bids, bidder),
                  key=get_time, reverse=True)[0]


def get_tender_data(tender_url, user="", password="", retry_count=10,
                    request_id=None):
    if not request_id:
        request_id = generate_request_id()
    extra_headers = {'content-type': 'application/json', 'X-Client-Request-ID': request_id}

    if user or password:
        auth = (user, password)
    else:
        auth = None
    for iteration in xrange(retry_count):
        try:
            logging.info("Get data from {}".format(tender_url),
                         extra={"JOURNAL_REQUEST_ID": request_id})
            response = requests.get(tender_url, auth=auth, headers=extra_headers,
                                    timeout=300)
            if response.ok:
                logging.info("Response from {}: status: {} text: {}".format(
                    tender_url, response.status_code, response.text),
                    extra={"JOURNAL_REQUEST_ID": request_id}
                )
                return response.json()
            else:
                logging.error("Response from {}: status: {} text: {}".format(
                    tender_url, response.status_code, response.text),
                    extra={"JOURNAL_REQUEST_ID": request_id}
                )
                if response.status_code == 403:
                    for error in response.json()["errors"]:
                        if error["description"].startswith('Can\'t get auction info'):
                            return None
        except requests.exceptions.RequestException, e:
            logging.error(
                "Request error {} error: {}".format(tender_url, e),
                extra={"JOURNAL_REQUEST_ID": request_id}
            )
        except Exception, e:
            logging.error(
                "Unhandled error {} error: {}".format(tender_url, e),
                extra={"JOURNAL_REQUEST_ID": request_id}
            )
        logging.info("Wait before retry...",
                     extra={"JOURNAL_REQUEST_ID": request_id})
        sleep(pow(iteration, 2))
    return None


def patch_tender_data(tender_url, data=None, files=None, user="", password="",
                      retry_count=10, method='patch', request_id=None):
    if not request_id:
        request_id = generate_request_id()
    extra_headers = {'content-type': 'application/json', 'X-Client-Request-ID': request_id}

    if user or password:
        auth = (user, password)
    else:
        auth = None
    for iteration in xrange(retry_count):
        try:
            if data:
                response = getattr(requests, method)(
                    tender_url,
                    auth=auth,
                    headers=extra_headers,
                    data=json.dumps(data),
                    timeout=300
                )
            else:
                response = getattr(requests, method)(
                    tender_url,
                    auth=auth,
                    headers=extra_headers,
                    files=files,
                    timeout=300
                )

            if response.ok:
                logging.info("Response from {}: status: {} text: {}".format(
                    tender_url, response.status_code, response.text),
                    extra={"JOURNAL_REQUEST_ID": request_id}
                )
                return response.json()
            else:
                logging.error("Response from {}: status: {} text: {}".format(
                    tender_url, response.status_code, response.text),
                    extra={"JOURNAL_REQUEST_ID": request_id}
                )
        except requests.exceptions.RequestException, e:
            logging.error("Request error {} error: {}".format(
                tender_url,
                e),
                extra={"JOURNAL_REQUEST_ID": request_id}
            )
        except Exception, e:
            logging.error("Unhandled error {} error: {}".format(
                tender_url,
                e),
                extra={"JOURNAL_REQUEST_ID": request_id}
            )
        logging.info("Wait before retry...",
                     extra={"JOURNAL_REQUEST_ID": request_id})
        sleep(pow(iteration, 2))




def do_until_success(func, args=(), kw={}, repeat=10, sleep_seconds=10):
    while True:
        try:
            return func(*args, **kw)
        except Exception, e:
            logging.error("Error {} while call {} with args: {}, kw: {}".format(
                e, func, args, kw
            ))
        repeat -= 1
        if repeat == 0:
            logging.error("Stop running {} with args: {}, kw: {}".format(
                func, args, kw
            ))
            break
        sleep(sleep_seconds)


def calculate_hash(bidder_id, hash_secret):
    digest = sha1(hash_secret)
    digest.update(bidder_id)
    return digest.hexdigest()


def get_lisener(port, host=''):
    lisener = None
    while lisener is None:
        family, address = parse_address((host, port))
        try:
            lisener = WSGIServer.get_listener(address, family=family)
        except Exception, e:
            pass
        port += 1
    return lisener


def create_mapping(redis_url, auction_id, auction_url):
    mapings = Redis.from_url(redis_url)
    return mapings.set(auction_id, auction_url)


def delete_mapping(redis_url, auction_id):
    mapings = Redis.from_url(redis_url)
    return mapings.delete(auction_id)


def prepare_extra_journal_fields(headers):
    extra = {}
    for key in EXTRA_LOGGING_VALUES:
        if key in headers:
            extra[EXTRA_LOGGING_VALUES[key]] = headers[key]
    return extra
