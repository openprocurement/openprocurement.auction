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


def filter_by_bidder_id(bids, bidder_id):
    return [bid for bid in bids if bid['bidder_id'] == bidder_id]


def filter_start_bids_by_bidder_id(bids, bidder):
    return [bid for bid in bids
            if bid['bidders'][0]['id']['name'] == bidder]


def get_time(item):
    if item.get('time', ''):
        bid_time = iso8601.parse_date(item['time'])
    elif item.get('date', ''):
        bid_time = iso8601.parse_date(item['date'])
    else:
        bid_time = datetime(MINYEAR, 1, 1, tzinfo=timezone('Europe/Kiev'))
    return bid_time


def sorting_by_amount(bids, reverse=True):
    def get_amount(item):
        return item['amount']

    return sorted(bids, key=get_amount, reverse=reverse)


def sorting_start_bids_by_amount(bids, reverse=True):
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


def get_tender_data(tender_url, user="", password="", retry_count=10):
    if user or password:
        auth = (user, password)
    else:
        auth = None
    for iteration in xrange(retry_count):
        try:
            logging.info("Get data from {}".format(tender_url))
            response = requests.get(tender_url, auth=auth,
                                    timeout=300)
            if response.ok:
                logging.info("Response from {}: status: {} text: {}".format(
                    tender_url, response.status_code, response.text)
                )
                return response.json()
            else:
                logging.error("Response from {}: status: {} text: {}".format(
                    tender_url, response.status_code, response.text)
                )
                if response.status_code == 403:
                    for error in response.json()["errors"]:
                        if error["description"] == 'Can\'t get auction info in current tender status':
                            return None
        except requests.exceptions.RequestException, e:
            logging.error("Request error {} error: {}".format(
                tender_url,
                e)
            )
        except Exception, e:
            logging.error("Unhandled error {} error: {}".format(
                tender_url,
                e)
            )
        logging.info("Wait before retry...")
        sleep(pow(iteration, 2))
    return None


def patch_tender_data(tender_url, data, user="", password="", retry_count=10,
                      method='patch'):
    if user or password:
        auth = (user, password)
    else:
        auth = None
    for iteration in xrange(retry_count):
        try:
            response = getattr(requests, method)(
                tender_url,
                auth=auth,
                headers={'content-type': 'application/json'},
                data=json.dumps(data),
                timeout=300
            )

            if response.ok:
                logging.info("Response from {}: status: {} text: {}".format(
                    tender_url, response.status_code, response.text)
                )
                return response.json()
            else:
                logging.error("Response from {}: status: {} text: {}".format(
                    tender_url, response.status_code, response.text)
                )
        except requests.exceptions.RequestException, e:
            logging.error("Request error {} error: {}".format(
                tender_url,
                e)
            )
        except Exception, e:
            logging.error("Unhandled error {} error: {}".format(
                tender_url,
                e)
            )
        logging.info("Wait before retry...")
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
