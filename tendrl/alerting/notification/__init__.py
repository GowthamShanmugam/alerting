from abc import abstractmethod
import etcd
import importlib
import inspect
import os
import six
from tendrl.alerting.exceptions import AlertingError
from tendrl.alerting.notification.exceptions import NotificationDispatchError
from tendrl.alerting.notification.exceptions import NotificationPluginError
from tendrl.alerting.objects.alert_types import AlertTypes
from tendrl.alerting.handlers import AlertHandler
from tendrl.alerting.objects.notification_media import NotificationMedia
from tendrl.alerting.objects.notification_config import NotificationConfig
from tendrl.commons.event import Event
from tendrl.commons.message import Message


class PluginMount(type):

    def __init__(cls, name, bases, attrs):
        if not hasattr(cls, 'plugins'):
            cls.plugins = []
        else:
            cls.register_plugin(cls)

    def register_plugin(cls, plugin):
        instance = plugin()
        cls.plugins.append(instance)


@six.add_metaclass(PluginMount)
class NotificationPlugin(object):
    def __init__(self):
        super(NotificationPlugin, self).__init__()
        self.name = ''

    @abstractmethod
    def save_config_help(self):
        raise NotImplementedError()

    @abstractmethod
    def set_destinations(self):
        raise NotImplementedError()

    @abstractmethod
    def get_alert_destinations(self):
        raise NotImplementedError()

    @abstractmethod
    def format_message(self, alert):
        raise NotImplementedError()

    @abstractmethod
    def dispatch_notification(self, msg):
        raise NotImplementedError()


class NotificationPluginManager(object):
    def load_plugins(self):
        try:
            path = os.path.dirname(os.path.abspath(__file__)) + '/handlers'
            pkg = 'tendrl.alerting.notification.handlers'
            for py in [f[:-3] for f in os.listdir(path)
                       if f.endswith('.py') and f != '__init__.py']:
                plugin_name = '.'.join([pkg, py])
                mod = importlib.import_module(plugin_name)
                clsmembers = inspect.getmembers(mod, inspect.isclass)
                for name, cls in clsmembers:
                    exec("from %s import %s" % (plugin_name, name))
        except (SyntaxError, ValueError, ImportError) as ex:
            Event(
                Message(
                    "error",
                    "alerting",
                    {
                        "message": 'Failed to load the time series db'
                        'plugins. Error %s' % ex
                    }
                )
            )
            raise NotificationPluginError(str(ex))

    def save_alertnotificationconfig(self):
        notification_config = {}
        for n_plugin in tendrl_ns.notification_medium:
            for alert_type in tendrl_ns.alert_types:
                conf_name = '%s_%s' % (n_plugin, alert_type)
                notification_config[conf_name] = "true"
        NotificationConfig(config=notification_config).save()

    def __init__(self):
        super(NotificationPluginManager, self).__init__()
        try:
            self.load_plugins()
            notification_medium = []
            for plugin in NotificationPlugin.plugins:
                notification_medium.append(plugin.name)
            tendrl_ns.notification_medium = notification_medium
            NotificationMedia(
                media=notification_medium
            ).save()
            self.save_alertnotificationconfig()
        except (
            SyntaxError,
            ValueError,
            KeyError,
            etcd.EtcdKeyNotFound,
            etcd.EtcdConnectionFailed,
            etcd.EtcdException,
            NotificationPluginError
        ) as ex:
            Event(
                Message(
                    "error",
                    "alerting",
                    {
                        "message": 'Failed to intialize notification '
                        'manager.Error %s' % str(ex)
                    }
                )
            )
            raise AlertingError(str(ex))

    def notify_alert(self, alert):
        tendrl_ns.notification_subscriptions = \
            NotificationConfig().load().config
        if alert is not None:
            for plugin in NotificationPlugin.plugins:
                plugin.dispatch_notification(alert)
