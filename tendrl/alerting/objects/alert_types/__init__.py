from tendrl.alerting.objects \
    import AlertingBaseObject
from tendrl.commons.etcdobj import EtcdObj


class AlertTypes(AlertingBaseObject):
    def __init__(self, types=None, *args, **kwargs):
        super(AlertTypes, self).__init__(*args, **kwargs)
        self.value = 'alerting/alert_types/types'
        self.types = types
        self._etcd_cls = _AlertTypes


class _AlertTypes(EtcdObj):
    """A table of the node context, lazily updated

    """
    __name__ = 'alerting/alert_types'
    _tendrl_cls = AlertTypes
