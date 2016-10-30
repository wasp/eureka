"""
Eureka Client Library.

Eureka is a service discovery and registration service
built by Netflix and used in the Spring Cloud stack.
"""
import asyncio
import atexit
import enum
import logging
import uuid
from typing import Optional, Dict, Any

from aiohttp import ClientSession

try:
    import ujson as json
except ImportError:
    import json

_LOG = logging.getLogger('wasp.eureka')

_SESSION = ClientSession(headers={
    # They default to using XML.
    'Accept': 'application/json',
    'Content-Type': 'application/json',
})
atexit.register(_SESSION.close)


class StatusType(enum.Enum):
    """
    Available status types with eureka, these can be used
    for any `EurekaClient.register` call to pl
    """
    UP = 'UP'
    DOWN = 'DOWN'
    STARTING = 'STARTING'
    OUT_OF_SERVICE = 'OUT_OF_SERVICE'
    UNKNOWN = 'UNKNOWN'


class EurekaClient:
    __slots__ = ('_loop', '_eureka_url', '_app_name', '_port', '_hostname',
                 '_ip_addr', '_instance_id', '_health_check_url',
                 '_status_page_url',)

    """
    A really naive eureka client.
    """

    def __init__(self, app_name: str, port: int, ip_addr: str, *,
                 hostname: Optional[str] = None,
                 eureka_url: str = 'http://localhost:8765/eureka/',
                 loop: Optional[asyncio.AbstractEventLoop] = None,
                 instance_id: Optional[str] = None,
                 health_check_url: Optional[str] = None,
                 status_page_url: Optional[str] = None):
        """
        Naive eureka client, only supports the base operations.

        :param app_name: Application name, this is used to register/find
                         by name.
        :param port: Application port that is accessible
        :param ip_addr: IP Address the server is available on
        :param hostname: Host name of the machine, if not reachable by
                         DNS, use the IP. If not provided, the IP is
                         used by default.
        :param eureka_url: Eureka server url, including path.
        :param loop: Event loop to operate on
        :param instance_id: Server instance ID, you should only really
                            set this if you need to operate on an existing
                            registered service.
        :param health_check_url: Health check URL if available, not required.
                                 But if included it should return 2xx.
        :param status_page_url: URL for server status (info route?), It's
                                required to not crash the Spring Eureka UI,
                                but otherwise not required. If not included -
                                we will just use the server IP with '/info'.
        """
        self._loop = loop or asyncio.get_event_loop()
        if eureka_url.endswith('/'):
            eureka_url = eureka_url[:-1]
        self._eureka_url = eureka_url
        self._app_name = app_name
        self._port = port
        self._hostname = hostname or ip_addr
        self._ip_addr = ip_addr
        self._health_check_url = health_check_url
        # Not including this seems to crash the Eureka UI,
        # it's just a link from eureka over so if none is
        # given we just give it a sane default. It being
        # a 404 doesn't seem to matter.
        if status_page_url is None:
            status_page_url = 'http://{}:{}/info'.format(ip_addr, port)
            _LOG.debug('Status page not provided, rewriting to %s',
                       status_page_url)
        self._status_page_url = status_page_url

        # unique id for the application, only really required
        # if this instance wants to register with Eureka instead
        # of just being a consumer.
        self._instance_id = instance_id or self._generate_instance_id()

    async def register(self, *, metadata: Optional[Dict[str, Any]] = None,
                       eviction_duration: int = 90):
        """Register the current application with eureka with the
        specified status. Note, there is a limited lease with eureka,
        so you will want to renew it on a schedule. Also to avoid
        unnecessary 500 errors, you will also want to ensure you
        deregister before your application is removed from service
        :param metadata: Arbitrary dictionary of metadata to set on
                         the instance. This can be treated effectively
                         as a key/value store. This needs to be json-able
        :param eviction_duration: Optional lease length customization (secs)
                                  ensure that renews are within the duration.
        """
        payload = {
            'instance': {
                'instanceId': self._instance_id,
                'leaseInfo': {
                    'evictionDurationSecs': eviction_duration,
                },
                'port': {
                    '$': self._port,
                    '@enabled': self._port is not None,
                },
                # TODO: Secure Port/Vip
                # 'securePort': {
                #     '$': self._secure_port,
                #     '@enabled': False
                # },
                # 'secureVipAddress': self._app_name,
                'hostName': self._hostname,
                'app': self._app_name,
                'ipAddr': self._ip_addr,
                'vipAddress': self._app_name,
                # TODO: AWS
                'dataCenterInfo': {
                    '@class': 'com.netflix.appinfo.MyDataCenterInfo',
                    'name': 'MyOwn',
                },
            }
        }
        if self._health_check_url is not None:
            payload['instance']['healthCheckUrl'] = self._health_check_url
        if self._status_page_url is not None:
            payload['instance']['statusPageUrl'] = self._status_page_url
        if metadata:
            payload['instance']['metadata'] = metadata
        url = '{}/apps/{}'.format(self._eureka_url, self._app_name)
        async with _SESSION.post(url, data=json.dumps(payload)) as resp:
            return resp.status == 204

    async def renew(self) -> bool:
        """Renews the application's lease with eureka to avoid
        eradicating stale/decommissioned applications."""
        url = '{}/apps/{}/{}'.format(self._eureka_url, self._app_name,
                                     self._instance_id)
        async with _SESSION.put(url) as resp:
            return resp.status == 200

    async def deregister(self) -> bool:
        """Deregister with the remote server, if you forget to do
        this the gateway will be giving out 500s when it tries to
        route to your application."""
        url = '{}/apps/{}/{}'.format(self._eureka_url, self._app_name,
                                     self._instance_id)
        async with _SESSION.delete(url) as resp:
            return resp.status == 200

    async def set_status_override(self, status: StatusType) -> bool:
        """Sets the status override, note: this should generally only
        be used to pull services out of commission - not really used
        to manually be setting the status to UP falsely."""
        url = '{}/apps/{}/{}/status?value={}'.format(self._eureka_url,
                                                     self._app_name,
                                                     self._instance_id,
                                                     status.value)
        async with _SESSION.put(url) as resp:
            return resp.status == 200

    async def remove_status_override(self) -> bool:
        """Removes the status override."""
        url = '{}/apps/{}/{}/status'.format(self._eureka_url,
                                            self._app_name,
                                            self._instance_id)
        async with _SESSION.delete(url) as resp:
            return resp.status == 200

    async def update_meta(self, key: str, value: Any) -> bool:
        url = '{}/apps/{}/{}/metadata?{}={}'.format(self._eureka_url,
                                                    self._app_name,
                                                    self._instance_id,
                                                    key, value)
        async with _SESSION.put(url) as resp:
            return resp.status == 200

    async def get_apps(self) -> Dict[str, Any]:
        """Gets a payload of the apps known to the
        eureka server."""
        url = self._eureka_url + '/apps'
        async with _SESSION.get(url) as resp:
            assert resp.status == 200, resp
            return await resp.json()

    async def get_app(self, app_name: Optional[str] = None) -> Dict[str, Any]:
        app_name = app_name or self._app_name
        url = self._eureka_url + '/apps/' + app_name
        async with _SESSION.get(url) as resp:
            assert resp.status == 200, resp
            return await resp.json()

    async def get_app_instance(self, app_name: Optional[str] = None,
                               instance_id: Optional[str] = None):
        """Get a specific instance, narrowed by app name."""
        app_name = app_name or self._app_name
        instance_id = instance_id or self._instance_id
        url = '{}/apps/{}/{}'.format(self._eureka_url,
                                     app_name, instance_id)
        async with _SESSION.get(url) as resp:
            assert resp.status == 200, resp
            return await resp.json()

    async def get_instance(self, instance_id: Optional[str] = None):
        """Get a specific instance, without needing to care about
        the app name."""
        instance_id = instance_id or self._instance_id
        url = '{}/instances/{}'.format(self._eureka_url, instance_id)
        async with _SESSION.get(url) as resp:
            assert resp.status == 200, resp
            return await resp.json()

    async def get_by_vip(self, vip_address: Optional[str] = None):
        """Query for all instances under a particular vip address"""
        vip_address = vip_address or self._app_name
        url = '{}/vips/{}'.format(self._eureka_url, vip_address)
        async with _SESSION.get(url) as resp:
            assert resp.status == 200, resp
            return await resp.json()

    async def get_by_svip(self, svip_address: Optional[str] = None):
        """Query for all instances under a particular secure vip address"""
        svip_address = svip_address or self._app_name
        url = '{}/vips/{}'.format(self._eureka_url, svip_address)
        async with _SESSION.get(url) as resp:
            assert resp.status == 200, resp
            return await resp.json()

    def _generate_instance_id(self):
        """Generates a unique instance id"""
        instance_id = '{}:{}:{}'.format(
            str(uuid.uuid4()), self._app_name, self._port
        )
        _LOG.info('Generated new instance id: %s', instance_id)
        return instance_id
