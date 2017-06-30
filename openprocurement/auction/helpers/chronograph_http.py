from flask import Flask
from flask.json import dumps
from gevent import spawn
from consul import Consul


chronograph_webapp = Flask(__name__)


@chronograph_webapp.route("/jobs")
def get_jobs():
    if chronograph_webapp.chronograph.scheduler.running:
        return dumps(list([{"id": job.id, "time": str(job.next_run_time)}
                           for job in chronograph_webapp.chronograph.scheduler.get_jobs()]))
    else:
        return dumps([])


@chronograph_webapp.route("/active_locks")
def get_active_locks():
    client = Consul()
    return dumps(client.kv.get('auction_', recurse=True)[1])


@chronograph_webapp.route("/active_jobs")
def get_active_jobs():
    return dumps(chronograph_webapp.chronograph.scheduler._executors['default']._instances)


@chronograph_webapp.route("/shutdown")
def shutdown():
    if chronograph_webapp.chronograph.scheduler.running:
        spawn(chronograph_webapp.chronograph.scheduler.shutdown, (True))
    return dumps('Start shutdown')
