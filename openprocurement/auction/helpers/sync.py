from gevent import monkey, sleep
monkey.patch_all()

import logging
from openprocurement_client.client import TendersClientSync
from gevent import spawn
from gevent.queue import Queue


RETRIEVER_DOWN_REQUESTS_SLEEP = 5
RETRIEVER_UP_REQUESTS_SLEEP = 1
RETRIEVER_UP_WAIT_SLEEP = 30
RETRIEVERS_QUEUE_SIZE = 30

DEFAULT_API_HOST = 'https://lb.api-sandbox.openprocurement.org/'
DEFAULT_API_VERSION = '2.3'
DEFAULT_API_KEY = ''
DEFAULT_API_EXTRA_PARAMS = {'opt_fields': 'status,auctionPeriod,lots', 'mode': '_all_'}

logger = logging.getLogger(__name__)


def start_sync(host=DEFAULT_API_HOST, version=DEFAULT_API_VERSION,
               key=DEFAULT_API_KEY, extra_params=DEFAULT_API_EXTRA_PARAMS):
    """
    Start retrieving from Openprocurement API.

    :param:
        host (str): Url of Openprocurement API. Defaults is DEFAULT_API_HOST
        version (str): Verion of Openprocurement API. Defaults is DEFAULT_API_VERSION
        key(str): Access key of broker in Openprocurement API. Defaults is DEFAULT_API_KEY (Empty string)
        extra_params(dict): Extra params of query

    :returns:
        queue: Queue which containing objects derived from the list of tenders
        forward_worker: Greenlet of forward worker
        backfard_worker: Greenlet of backfard worker

    """
    forward = TendersClientSync(key, host, version)
    backfard = TendersClientSync(key, host, version)
    Cookie = forward.headers['Cookie'] = backfard.headers['Cookie']
    backfard_params = {'descending': True, 'feed': 'changes'}
    backfard_params.update(extra_params)
    forward_params =  {'feed': 'changes'}
    forward_params.update(extra_params)

    response = backfard.sync_tenders(backfard_params)

    queue = Queue()
    for tender in response.data:
        queue.put(tender)
    backfard_params['offset'] = response.next_page.offset
    forward_params['offset'] = response.prev_page.offset

    backfard_worker = spawn(retriever_backward, queue, backfard, Cookie, backfard_params)
    forward_worker = spawn(retriever_forward, queue, forward, Cookie, forward_params)

    return queue, forward_worker, backfard_worker


def restart_sync(up_worker, down_worker,
                 host=DEFAULT_API_HOST, version=DEFAULT_API_VERSION, key=DEFAULT_API_KEY, extra_params=DEFAULT_API_EXTRA_PARAMS):
    """
    Restart retrieving from Openprocurement API.

    Args:
        forward_worker: Greenlet of forward worker
        backfard_worker: Greenlet of backfard worker

    :param:
        host (str): Url of Openprocurement API. Defaults is DEFAULT_API_HOST
        version (str): Verion of Openprocurement API. Defaults is DEFAULT_API_VERSION
        key(str): Access key of broker in Openprocurement API. Defaults is DEFAULT_API_KEY (Empty string)
        extra_params(dict): Extra params of query

    :returns:
        queue: Queue which containing objects derived from the list of tenders
        forward_worker: Greenlet of forward worker
        backfard_worker: Greenlet of backfard worker

    """

    logger.info('Restart workers')
    up_worker.kill()
    down_worker.kill()
    return start_sync(host=host, version=version, key=key, extra_params=extra_params)


def get_tenders(host=DEFAULT_API_HOST, version=DEFAULT_API_VERSION, key=DEFAULT_API_KEY, extra_params=DEFAULT_API_EXTRA_PARAMS):
    """
    Prepare iterator for retrieving from Openprocurement API.

    :param:
        host (str): Url of Openprocurement API. Defaults is DEFAULT_API_HOST
        version (str): Verion of Openprocurement API. Defaults is DEFAULT_API_VERSION
        key(str): Access key of broker in Openprocurement API. Defaults is DEFAULT_API_KEY (Empty string)
        extra_params(dict): Extra params of query

    :returns:
        iterator of tender_object (Munch): object derived from the list of tenders

    """

    queue, up_worker, down_worker = start_sync(host=host, version=version, key=key, extra_params=extra_params)
    check_down_worker = True
    while 1:
        if check_down_worker and down_worker.ready():
            if down_worker.value == 0:
                logger.info('Stop check backward worker')
                check_down_worker = False
            else:
                queue, up_worker, down_worker = restart_sync(up_worker, down_worker,
                                                             host=host, version=version, key=key, extra_params=extra_params)
                check_down_worker = True
        if up_worker.ready():
            queue, up_worker, down_worker = restart_sync(up_worker, down_worker,
                                                         host=host, version=version, key=key, extra_params=extra_params)
            check_down_worker = True
        while not queue.empty():
             yield queue.get()
        sleep(5)


def retriever_backward(queue, client, origin_cookie, params):
    logger.info('Backward: Start worker')
    response = client.sync_tenders(params)
    if origin_cookie != client.headers['Cookie']:
        raise Exception('LB Server mismatch')
    while response.data:
        for tender in response.data:
            queue.put(tender)
        params['offset'] = response.next_page.offset
        response = client.sync_tenders(params)
        if origin_cookie != client.headers['Cookie']:
            raise Exception('LB Server mismatch')
        logger.debug('Backward: pause between requests')
        sleep(RETRIEVER_DOWN_REQUESTS_SLEEP)
    logger.info('Backward: finished')
    return 0


def retriever_forward(queue, client, origin_cookie, params):
    logger.info('Forward: Start worker')
    response = client.sync_tenders(params)
    if origin_cookie != client.headers['Cookie']:
        raise Exception('LB Server mismatch')
    while 1:
        while response.data:
            for tender in response.data:
                queue.put(tender)
            params['offset'] = response.next_page.offset
            response = client.sync_tenders(params)
            if origin_cookie != client.headers['Cookie']:
                raise Exception('LB Server mismatch')
            if len(response.data) != 0:
                logger.debug('Forward: pause between requests')
                sleep(RETRIEVER_UP_REQUESTS_SLEEP)

        logger.debug('Forward: pause after empty response')
        sleep(RETRIEVER_UP_WAIT_SLEEP)

        params['offset'] = response.next_page.offset
        response = client.sync_tenders(params)
        if origin_cookie != client.headers['Cookie']:
            raise Exception('LB Server mismatch')

    return 1

if __name__ == '__main__':
    for tender_item in get_tenders():
        if tender_item['status'] == 'active.auction':
            print 'Tender {0[id]}'.format(tender_item)
