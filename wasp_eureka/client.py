"""
Eureka Client Library.

Eureka is a service discovery and registration service
built by Netflix and used in the Spring Cloud stack.
"""
import asyncio
import atexit
import enum
import uuid
from http import HTTPStatus
from typing import Optional, Dict, Any

from wasp_eureka.exc import EurekaException

try:
    import ujson as json
except ImportError:
    import json

from aiohttp import ClientSession

from .log import logger

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
                 '_status_page_url')

    def __init__(self,
                 app_name: Optional[str] = None,
                 port: Optional[int] = None,
                 ip_addr: Optional[str] = None,
                 *,
                 hostname: Optional[str] = None,
                 eureka_url: str = 'http://localhost:8765',
                 loop: Optional[asyncio.AbstractEventLoop] = None,
                 instance_id: Optional[str] = None,
                 health_check_url: Optional[str] = None,
                 status_page_url: Optional[str] = None):
        """
        Naive eureka client, only supports the base operations.

        :param app_name: Application name, this is used to register/find
                         by name. Only required if you want to register
                         with Eureka.
        :param port: Application port that is accessible. Only required if
                     you want to register with Eureka
        :param ip_addr: IP Address the server is available on. Only required
                        if you want to register with Eureka.
        :param hostname: Host name of the machine, if not reachable by
                         DNS, use the IP. If not provided, the IP is
                         used by default. Only required if you want to register
                         with Eureka
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
        self._loop = loop
        if loop is None:
            self._loop = asyncio.get_event_loop()
        self._eureka_url = eureka_url.rstrip('/') + '/eureka'
        self._app_name = app_name
        self._port = port
        self._hostname = hostname or ip_addr
        self._ip_addr = ip_addr
        self._health_check_url = health_check_url

        self._instance_id = instance_id

        # Not including this crashes the Eureka UI, fixed in later version,
        # not one we can ensure people are using.
        if status_page_url is None:
            status_page_url = 'http://{}:{}/info'.format(self._ip_addr, port)
            logger.debug('Status page not provided, rewriting to %s',
                         status_page_url)
        self._status_page_url = status_page_url

    async def register(self, *, metadata: Optional[Dict[str, Any]] = None,
                       lease_duration: int = 60,
                       lease_renewal_interval: int = 15):
        """Register the current application with eureka with the
        specified status. Note, there is a limited lease with eureka,
        so you will want to renew it on a schedule. Also to avoid
        unnecessary 500 errors, you will also want to ensure you
        deregister before your application is removed from service
        :param metadata: Arbitrary dictionary of metadata to set on
                         the instance. This can be treated effectively
                         as a key/value store. This needs to be json-able
        :param lease_duration: Length of the lease, defaults to 30s
        :param lease_renewal_interval: How often to expect renewals
        """
        payload = {
            'instance': {
                'instanceId': self.instance_id,
                'leaseInfo': {
                    # 'evictionDurationSecs': eviction_duration,  # v2?
                    'durationInSecs': lease_duration,
                    'renewalIntervalInSecs': lease_renewal_interval,
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
        url = '/apps/{}'.format(self._app_name)
        logger.debug('Registering %s', self._app_name)
        return await self._do_req(url, method='POST', data=json.dumps(payload))

    async def renew(self):
        """Renews the application's lease with eureka to avoid
        eradicating stale/decommissioned applications."""
        url = '/apps/{}/{}'.format(self._app_name, self.instance_id)
        return await self._do_req(url, method='PUT')

    async def deregister(self):
        """Deregister with the remote server, if you forget to do
        this the gateway will be giving out 500s when it tries to
        route to your application."""
        url = '/apps/{}/{}'.format(self._app_name, self.instance_id)
        return await self._do_req(url, method='DELETE')

    async def set_status_override(self, status: StatusType):
        """Sets the status override, note: this should generally only
        be used to pull services out of commission - not really used
        to manually be setting the status to UP falsely."""
        url = '/apps/{}/{}/status?value={}'.format(self._app_name,
                                                   self.instance_id,
                                                   status.value)
        return await self._do_req(url, method='PUT')

    async def remove_status_override(self):
        """Removes the status override."""
        url = '/apps/{}/{}/status'.format(self._app_name,
                                          self.instance_id)
        return await self._do_req(url, method='DELETE')

    async def update_meta(self, key: str, value: Any):
        url = '/apps/{}/{}/metadata?{}={}'.format(self._app_name,
                                                  self.instance_id,
                                                  key, value)
        return await self._do_req(url, method='PUT')

    async def get_apps(self) -> Dict[str, Any]:
        """Gets a payload of the apps known to the
        eureka server."""
        url = '/apps'
        return await self._do_req(url)

    async def get_app(self, app_name: Optional[str] = None) -> Dict[str, Any]:
        app_name = app_name or self._app_name
        url = '/apps/{}'.format(app_name)
        return await self._do_req(url)

    async def get_app_instance(self, app_name: Optional[str] = None,
                               instance_id: Optional[str] = None):
        """Get a specific instance, narrowed by app name."""
        app_name = app_name or self._app_name
        instance_id = instance_id or self.instance_id
        url = '/apps/{}/{}'.format(app_name, instance_id)
        return await self._do_req(url)

    async def get_instance(self, instance_id: Optional[str] = None):
        """Get a specific instance, without needing to care about
        the app name."""
        instance_id = instance_id or self.instance_id
        url = '/instances/{}'.format(instance_id)
        return await self._do_req(url)

    async def get_by_vip(self, vip_address: Optional[str] = None):
        """Query for all instances under a particular vip address"""
        vip_address = vip_address or self._app_name
        url = '/vips/{}'.format(vip_address)
        return await self._do_req(url)

    async def get_by_svip(self, svip_address: Optional[str] = None):
        """Query for all instances under a particular secure vip address"""
        svip_address = svip_address or self._app_name
        url = '/vips/{}'.format(svip_address)
        return await self._do_req(url)

    async def _do_req(self, path: str, *, method: str = 'GET',
                      data: Optional[Any] = None):
        """
        Performs a request against the instance eureka server.
        :param path: URL Path, the hostname is prepended automatically
        :param method: request method (put/post/patch/get/etc)
        :param data: Optional data to be sent with the request, must
                     already be encoded appropriately.
        :return: optional[dict[str, any]]
        """
        url = self._eureka_url + path
        logger.debug('Performing %s on %s with payload: %s', method, path,
                     data)
        async with _SESSION.request(method, url, data=data) as resp:
            if 400 <= resp.status < 600:
                # noinspection PyArgumentList
                raise EurekaException(HTTPStatus(resp.status),
                                      await resp.text())
            logger.debug('Result: %s', resp.status)
            return await resp.json()

    def _generate_instance_id(self) -> str:
        """Generates a unique instance id"""
        instance_id = '{}:{}:{}'.format(
            str(uuid.uuid4()), self._app_name, self._port
        )
        logger.debug('Generated new instance id: %s for app: %s', instance_id,
                     self._app_name)
        return instance_id

    @property
    def instance_id(self) -> str:
        """The instance_id the eureka client is targeting"""
        if self._instance_id is None:
            self._instance_id = self._generate_instance_id()
        # noinspection PyTypeChecker
        return self._instance_id

    @property
    def app_name(self) -> str:
        """The app_name the eureka client is targeting"""
        return self._app_name
