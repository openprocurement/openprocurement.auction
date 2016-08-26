from apscheduler.executors.gevent import GeventExecutor
from restkit import request
from .system import free_memory
from gevent import sleep
from logging import getLogger
from random import random
import consul
import iso8601
from datetime import timedelta, datetime
from apscheduler.schedulers.gevent import GeventScheduler
from gevent.subprocess import check_call

from uuid import uuid4

LOCK_RETRIES = 6
SLEEP_BETWEEN_TRIES_LOCK = 10
WORKER_TIME_RUN = 3600

AWS_META_DATA_URL = 'http://169.254.169.254/latest/meta-data/instance-id'
SERVER_NAME_PREFIX = 'AUCTION_WORKER_{}'

MIN_AUCTION_START_TIME_RESERV = timedelta(seconds=60)
MAX_AUCTION_START_TIME_RESERV = timedelta(seconds=15* 60)

def get_server_name():
    try:
        1/0
        r = request(AWS_META_DATA_URL)
        suffix = r.body_string()
    except Exception, e:
        suffix = uuid4().hex
    return SERVER_NAME_PREFIX.format(suffix)



class AuctionExecutor(GeventExecutor):

    def start(self, scheduler, alias):
        return super(AuctionExecutor, self).start(scheduler, alias)

    def shutdown(self, wait=True):
        """
        Shuts down this executor.

        :param bool wait: ``True`` to wait until all submitted jobs
            have been executed
        """
        while len(self._instances) > 0:
            sleep(1)



class AuctionScheduler(GeventScheduler):
    def __init__(self, server_name, config,
                 limit_auctions=500,
                 limit_free_memory=0.15,
                 logger=getLogger(__name__),
                 *args, **kwargs):
        super(AuctionScheduler, self).__init__(*args, **kwargs)
        self.server_name = server_name
        self.config = config
        self.execution_stopped = False
        self.consul = consul.Consul()
        self.logger = logger
        self._limit_pool_lock = self._create_lock()
        self._limit_auctions = int(limit_auctions)
        self._limit_free_memory = float(limit_free_memory)
        self._count_auctions = 0
        self.exit = False

    def _create_default_executor(self):
        return AuctionExecutor()

    def convert_datetime(self, datetime_stamp):
        return iso8601.parse_date(datetime_stamp).astimezone(self.timezone)

    def shutdown(self, *args, **kwargs):
        self.exit = True
        response = super(AuctionScheduler, self).shutdown(*args, **kwargs)
        self.execution_stopped = True
        return response

    def run_auction_func(self, tender_id, lot_id, view_value, ttl=WORKER_TIME_RUN):
        if self._count_auctions >= self._limit_auctions:
            self.logger.info("Limited by count")
            return

        if free_memory() <= self._limit_free_memory:
            self.logger.info("Limited by memory")
            return

        document_id = str(tender_id)
        if lot_id:
            document_id += "_"
            document_id += lot_id

        i = LOCK_RETRIES
        sleep(random())
        session = self.consul.session.create(behavior='delete', ttl=WORKER_TIME_RUN)
        while i > 0:
            if self.consul.kv.put("auction_{}".format(document_id), self.server_name, acquire=session):
                self.logger.info("Run worker for document {}".format(document_id))
                with self._limit_pool_lock:
                    self._count_auctions += 1

                params = [self.config['main']['auction_worker'],
                          "run", tender_id,
                          self.config['main']['auction_worker_config']]
                if lot_id:
                    params += ['--lot', lot_id]

                if view_value['api_version']:
                    params += ['--with_api_version', view_value['api_version']]
                rc = check_call(params)
                if rc:
                    self.logger.error("Exit with error {}".format(document_id))
                self.logger.info("Return code of {}: {}".format(document_id, rc))
                self.consul.session.destroy(session)
                with self._limit_pool_lock:
                    self._count_auctions -= 1
                return
            sleep(SLEEP_BETWEEN_TRIES_LOCK)
            i -= 1

        self.logger.info("Locked on other server")
        self.consul.session.destroy(session)

    def schedule_auction(self, document_id, view_value):

        now = datetime.now(self.timezone)
        auction_start_date = self.convert_datetime(view_value['start'])
        if auction_start_date - now > MAX_AUCTION_START_TIME_RESERV:
            AW_date = auction_start_date - MAX_AUCTION_START_TIME_RESERV
        if auction_start_date - now > MIN_AUCTION_START_TIME_RESERV:
            self.logger.warning('Planned auction\'s starts date in the past')
            AW_date = now
        if "_" in document_id:
            tender_id, lot_id = document_id.split("_")
        else:
            tender_id = document_id
            lot_id = None
        self.logger.info('Scedule start of {} at {} ({})'.format(document_id, AW_date, view_value['start']))

        self.add_job(self.run_auction_func, args=(tender_id, lot_id, view_value),
                          misfire_grace_time=60,
                          next_run_time=AW_date,
                          id=document_id,
                          replace_existing=True)