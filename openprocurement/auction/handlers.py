from openprocurement.auction.interfaces import IWorkerCommand


def default_(event):
   event.doc.created = datetime.datetime.utcnow()