import iso8601
from datetime import MINYEAR, datetime
from pytz import timezone


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
        return item['totalValue']['amount']

    return sorted(bids, key=get_amount, reverse=reverse)


def sorting_by_time(bids, reverse=True):
    return sorted(bids, key=get_time, reverse=reverse)


def get_latest_bid_for_bidder(bids, bidder_id):
    return sorted(filter_by_bidder_id(bids, bidder_id),
                  key=get_time, reverse=True)[0]


def get_latest_start_bid_for_bidder(bids, bidder):
    return sorted(filter_start_bids_by_bidder_id(bids, bidder),
                  key=get_time, reverse=True)[0]
