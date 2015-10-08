from apscheduler.executors.gevent import GeventExecutor


class AuctionsExecutor(GeventExecutor):

    def start(self, scheduler, alias):
        """
        Called by the scheduler when the scheduler is being started or when the executor is being added to an already
        running scheduler.

        :param apscheduler.schedulers.base.BaseScheduler scheduler: the scheduler that is starting this executor
        :param str|unicode alias: alias of this executor as it was assigned to the scheduler
        """
        self._scheduler = scheduler
        self._lock = scheduler._create_lock()
        self._logger = scheduler._logger
