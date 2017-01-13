import json
import logging
import multiprocessing
import Queue
from tendrl.commons.alert import AlertUtils

LOG = logging.getLogger(__name__)


class AlertsWatchManager(multiprocessing.Process):
    def __init__(self, alert_queue, etcd_client):
        super(AlertsWatchManager, self).__init__()
        self.alert_queue = alert_queue
        self.etcd_client = etcd_client

    def run(self):
        try:
            while True:
                new_alert = self.etcd_client.watch(
                    '/alerts',
                    recursive=True,
                    timeout=0
                )
                if new_alert is not None:
                    if new_alert.value is not None:
                        self.alert_queue.put(
                            AlertUtils().to_obj(
                                json.loads(new_alert.value)
                            )
                        )
        except Queue.Full as ex:
            LOG.error(
                'Exception in alert watcher.Error %s' % str(
                    ex),
                exc_info=True
            )
            raise ex

