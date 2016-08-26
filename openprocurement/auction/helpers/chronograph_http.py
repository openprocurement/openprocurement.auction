from flask import Flask, current_app, jsonify
from gevent import spawn

chronograph_webapp = Flask(__name__)

@chronograph_webapp.route("/jobs")
def get_jobs():
    if chronograph_webapp.chronograph.scheduler.running:
        return jsonify([{"id": job.id, "time": str(job.next_run_time)} for job in chronograph_webapp.chronograph.scheduler.get_jobs()])
    else:
        return jsonify([])

@chronograph_webapp.route("/active_locks")
def get_active_locks():
    return jsonify(chronograph_webapp.chronograph.scheduler.consul.kv.get('auction_', recurse=True)[1])

@chronograph_webapp.route("/active_jobs")
def get_active_jobs():
    return jsonify(chronograph_webapp.chronograph.scheduler._executors['default']._instances)

@chronograph_webapp.route("/shutdown")
def shutdown():
    if chronograph_webapp.chronograph.scheduler.running:
        spawn(chronograph_webapp.chronograph.scheduler.shutdown, (True))
    return jsonify(True)