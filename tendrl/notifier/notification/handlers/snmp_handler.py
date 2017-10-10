from etcd import EtcdException
from etcd import EtcdKeyNotFound
from pysnmp.error import PySnmpError
from pysnmp.hlapi import CommunityData
from pysnmp.hlapi import ContextData
from pysnmp.hlapi import ObjectIdentity
from pysnmp.hlapi import ObjectType
from pysnmp.hlapi import OctetString
from pysnmp.hlapi import sendNotification
from pysnmp.hlapi import SnmpEngine
from pysnmp.hlapi import UdpTransportTarget
from pysnmp.hlapi import usmDESPrivProtocol
from pysnmp.hlapi import usmHMACMD5AuthProtocol
from pysnmp.hlapi import UsmUserData
from tendrl.commons.config import load_config
from tendrl.commons.event import Event
from tendrl.commons.message import ExceptionMessage
from tendrl.commons.utils.log_utils import log
from tendrl.notifier.notification import NotificationPlugin

# USM users fixed snmp engine id
ENGINE_ID = "8000000001020304"
# default snmp port
PORT = 162
V2_ENDPOINT = "v2_endpoint"
V3_ENDPOINT = "v3_endpoint"
ALERT_TYPES = {0: "STATUS",
               1: "UTILIZATION"}


class SnmpEndpoint(object):
    # Base class for SNMP endpoint (credential and host+port pair)

    def __init__(self, host_ip="127.0.0.1", proto=0):
        self.proto = proto
        self.host = host_ip
        self.port = PORT
        self.engineid = ENGINE_ID


class V2Endpoint(SnmpEndpoint):
    # Class encapsulating an SNMPv2c community, host+port pair
    # 2 represent SNMPv2
    def __init__(self, host_ip, community):
        super(V2Endpoint, self).__init__(host_ip, 2)
        self.community = community


class V3Endpoint(SnmpEndpoint):
    # Class encapsulating an SNMPv2c community, host+port pair
    # 2 represent SNMPv2
    def __init__(self, host_ip, username, auth_key, priv_key):
        super(V3Endpoint, self).__init__(host_ip, 3)
        self.usm_user = UsmUserData(userName=username,
                                    authKey=auth_key,
                                    privKey=priv_key,
                                    authProtocol=usmHMACMD5AuthProtocol,
                                    privProtocol=usmDESPrivProtocol
                                    )


class SnmpHandler(NotificationPlugin):

    def __init__(self):
        self.name = 'snmp'
        self.user_configs = []

    def set_destinations(self):
        try:
            self.user_configs = self.get_alert_destinations()
        except (
            EtcdException,
            EtcdKeyNotFound,
            ValueError,
            KeyError,
            SyntaxError
        ) as ex:
            if type(ex) != EtcdKeyNotFound:
                self.user_configs = []
                return
            raise ex

    def get_alert_destinations(self):
        snmp_config = load_config(
            'notifier',
            '/etc/tendrl/notifier/snmp.conf.yaml'
        )
        return snmp_config

    def format_message(self, alert):
        resource = alert.resource.replace("_", " ").title()
        severity = alert.severity
        message = alert.tags['message']
        if alert.alert_type == ALERT_TYPES[0]:
            suffix = "status changed"
        elif alert.alert_type == ALERT_TYPES[1]:
            suffix = "threshold breached"
        return "[Tendrl Alert] %s, %s: %s-%s" % (
            resource, severity, suffix, message)

    def getPDU(self, message):
        pdu = [
            ObjectType(ObjectIdentity('1.3.6.1.4.2312.19.1.1'),
                       OctetString(message))]
        return pdu

    def trapV2(self, endpoint, message):
        # Send trap to one endpoint
        errorIndication, errorStatus, errorIndex, varBinds = next(
            sendNotification(
                SnmpEngine(snmpEngineID=OctetString(
                    hexValue=endpoint.engineid)),
                CommunityData(endpoint.community, mpModel=1),
                UdpTransportTarget((endpoint.host, endpoint.port)),
                ContextData(),
                'trap',
                # sequence of custom OID-value pairs
                self.getPDU(message)))
        if errorIndication:
            log(
                "error",
                "notifier",
                {
                    "message": 'Unable to sent snmp message to %s err:%s %s %s'
                    % (endpoint.host,
                       errorIndication,
                       errorStatus,
                       errorIndex)
                }
            )
        else:
            log(
                "info",
                "notifier",
                {
                    "message": 'Sent snmp message to %s to alert about %s'
                    % (endpoint.host,
                       message)
                }
            )

    def trapV3(self, endpoint, message):
        # Send trap to one endpoint
        errorIndication, errorStatus, errorIndex, varBinds = next(
            sendNotification(
                SnmpEngine(snmpEngineID=OctetString(
                    hexValue=endpoint.engineid)),
                endpoint.usm_user,
                UdpTransportTarget((endpoint.host, endpoint.port)),
                ContextData(),
                'trap',
                # sequence of custom OID-value pairs
                self.getPDU(message)))
        if errorIndication:
            log(
                "error",
                "notifier",
                {
                    "message": 'Unable to sent snmp message to %s err:%s %s %s'
                    % (endpoint.host,
                       errorIndication,
                       errorStatus,
                       errorIndex)
                }
            )
        else:
            log(
                "info",
                "notifier",
                {
                    "message": 'Sent snmp message to %s to alert about %s'
                    % (endpoint.host,
                       message)
                }
            )

    def send_message(self, endpoint, message):
        if endpoint.proto == 2:
            self.trapV2(endpoint, message)
        elif endpoint.proto == 3:
            self.trapV3(endpoint, message)

    def dispatch_notification(self, alert):
        try:
            self.set_destinations()
            if (
                self.user_configs is None
            ):
                log(
                    "error",
                    "notifier",
                    {
                        "message": 'No snmp destinations configured to send'
                        'alert notification'
                    }
                )
                return
        except (
            AttributeError,
            TypeError,
            EtcdException,
            ValueError,
            KeyError,
            SyntaxError
        ) as ex:
            Event(
                ExceptionMessage(
                    priority="debug",
                    publisher="notifier",
                    payload={
                        "message": 'Exception caught attempting to set'
                        ' %s snmp destinations' % str(alert.tags),
                        "exception": ex
                    }
                )
            )
            return ex
        try:
            msg = self.format_message(alert)
            for endpoint in self.user_configs:
                if endpoint == V2_ENDPOINT:
                    for user_config in self.user_configs[endpoint]:
                        v2_endpoint = V2Endpoint(
                            **self.user_configs[endpoint][user_config]
                        )
                        self.send_message(v2_endpoint, msg)
                elif endpoint == V3_ENDPOINT:
                    for user_config in self.user_configs[endpoint]:
                        v3_endpoint = V3Endpoint(
                            **self.user_configs[endpoint][user_config]
                        )
                        self.send_message(v3_endpoint, msg)
        except (
            PySnmpError,
            KeyError,
            ValueError,
            TypeError,
            AttributeError
        ) as ex:
            Event(
                ExceptionMessage(
                    priority="debug",
                    publisher="notifier",
                    payload={
                        "message": 'Exception caught attempting to email'
                        '%s' % msg,
                        "exception": ex
                    }
                )
            )
            return ex
