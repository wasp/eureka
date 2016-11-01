"""
This example uses APScheduler to schedule heartbeats with the remote server.

Note: APScheduler plans to support co-routines in 3.3.0, but you can
      install the HEAD to have it now:

  pip install git+git://github.com/agronholm/apscheduler@d4bce351a4dc15a5eb4be1887999426d005ba2ac#egg=APScheduler
"""
import asyncio
import socket

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from wasp_eureka import EurekaClient
from wasp_eureka.exc import EurekaException


async def renew_lease(eureka):
    # Guarded to ensure one bad try doesn't kill
    # checkins for good.
    print('Renewing eureka lease')
    try:
        await eureka.renew()
        print('Renewed')
        return True
    except EurekaException as e:
        print('Error renewing registration:', e.status)
        return False


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    scheduler = AsyncIOScheduler(loop=loop)

    hostname = socket.gethostname()
    ip = socket.gethostbyname(hostname)

    eureka = EurekaClient('test-app', 5000, ip,
                          eureka_url='https://localhost:8761/eureka',
                          loop=loop)

    print('Registering...')
    loop.run_until_complete(eureka.register())
    print('Done')

    scheduler.add_job(renew_lease, 'interval', seconds=30, args=(eureka,))
    scheduler.start()

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        # Note: If you run this with gunicorn this will deregister your app
        # You probable just want to let that lease expire (since your app
        # probably has >1 worker)
        print('Deregistering...')
        res = loop.run_until_complete(eureka.deregister())
        print('Done')
        loop.close()
