import datetime
import json
import contextlib
import tempfile
from dateutil.tz import tzlocal
import os

PWD = os.path.dirname(os.path.realpath(__file__))


@contextlib.contextmanager
def update_auctionPeriod(path, auction_type='simple', time_shift=datetime.timedelta(seconds=120)):
    new_start_time = (datetime.datetime.now(tzlocal()) + time_shift).isoformat()
    with open(path) as file:
        data = json.loads(file.read())
    if auction_type == 'multilot':
        for lot in data['data']['lots']:
            lot['auctionPeriod']['startDate'] = new_start_time
    else:
        data['data']['auctionPeriod']['startDate'] = new_start_time

    with tempfile.NamedTemporaryFile(delete=False) as auction_file:
        json.dump(data, auction_file)
        auction_file.seek(0)
    yield auction_file.name
    auction_file.close()


def read_file_from_json(path):
    with open(path) as file:
        data = json.loads(file.read())
    return data


AUCTION_DATA = {
    'simple': {'path': os.path.join(PWD, 'data', 'tender_simple.json'),
               'data': read_file_from_json(os.path.join(PWD, 'data', 'tender_simple.json'))},
    'multilot': {'path': os.path.join(PWD, 'data', 'tender_multilot.json'),
                 'data': read_file_from_json(os.path.join(PWD, 'data', 'tender_multilot.json'))}
}
