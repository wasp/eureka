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


async def renew_lease(eureka):
    # Guarded to ensure one bad try doesn't kill
    # checkins for good.
    print('Renewing eureka lease')
    try:
        res = await eureka.renew()
        print('Renewed:', res)
        return res
    except Exception:
        print('Error renewing registration')
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
    res = loop.run_until_complete(eureka.register())
    assert res, 'Unable to register'
    print('Done')

    scheduler.add_job(renew_lease, 'interval', seconds=30, args=(eureka,))
    scheduler.start()

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        print('Deregistering...')
        res = loop.run_until_complete(eureka.deregister())
        print('Done')
        loop.close()