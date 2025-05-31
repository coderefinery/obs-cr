import asyncio
import functools
import json
import os
import ssl
import textwrap

import websockets


async def handle(conn):
    target_url = args.target
    print(f'Connection from {conn.remote_address}')
    #print(path)
    #print(conn.request.headers)
    forward_headers = [
        'user-agent',
        #'Accept-Encoding',
        #'Sec-WebSocket-Version',
        #'Origin',
        #'Sec-WebSocket-Protocol',
        #'Sec-WebSocket-Extensions',
        #'Sec-WebSocket-Key',
    ]
    headers = {name: conn.request.headers[name] for name in forward_headers}
    #print(headers)
    async with websockets.connect(
        target_url,
        #additional_headers=headers,
        subprotocols=conn.request.headers['Sec-WebSocket-Protocol'].split(),
        #extensions=conn.request.headers['Sec-WebSocket-Extensions'].split(),
      ) as target_ws:
        #await conn.send('test')
        async def forward_messages():
            async for message in conn:
                #print (f'---> {message}')
                message = filter_forwarded(message)
                if message is None:
                    continue
                #print(f'>    {message} --->')
                await target_ws.send(message)
                await asyncio.sleep(0)
        async def return_messages():
            async for message in target_ws:
                #print(f'<    {message} <----')
                message = filter_returned(message)
                if message is None:
                    continue
                #print(f'<--- {message}')
                await conn.send(message)
                await asyncio.sleep(0)
                #print('done', conn.closed)
        await asyncio.gather(forward_messages(), return_messages())

ALLOWED_REQUESTS = set("""
    GetVersion

    GetPersistentData
    SetPersistentData
    BroadcastCustomEvent

    GetSceneList
    GetCurrentProgramScene
    SetCurrentProgramScene
    GetSceneItemId
    GetSceneItemList
    SetSceneItemEnabled

    GetInputMute
    SetInputMute
    GetInputVolume
    SetInputVolume

    GetMediaInputStatus
    GetInputSettings
    SetInputSettings
    TriggerMediaInputAction

    GetSceneItemTransform
    SetSceneItemTransform

    GetSourceScreenshot
""".split())

def filter_forwarded(message):
    data = json.loads(message)
    if data['op'] in {0, 1, 2, 3}:
        return message
    if data['op'] == 5:
        # event
        pass
    if data['op'] == 6:
        # request
        request = data['d']
        requestType = request['requestType']
        if requestType == 'SetInputSettings':
            inputSettings = request['requestData']['inputSettings']
            if len(set(inputSettings) - set('local_file overlay text font'.split())) == 0:
                return message
            print(message)
            return None
        if requestType in ALLOWED_REQUESTS:
            return message
        print(requestType)
    if data['op'] == 8:
        # batch
        submessages = data['requests']
        print("Batch not supported yet")
        #return message
    print(message)
    return None

def filter_returned(message):
    return message

async def main(target_url):
    server = await websockets.serve(
        handle, 
        *args.bind.rsplit(':', 1),
        subprotocols=['obswebsocket.json'],
        ssl=ssl_context,
        )
    print(f'Server started on {args.bind}')
    await server.serve_forever()
    print('Server closed')

if __name__ == "__main__":
    import argparse
    usage = textwrap.dedent("""\
    SSL:

    You may first need to register an account:
      bash acme.sh --register-account -m EMAIL

    Then request the certs:
      bash acme.sh --issue --dns --yes-I-know-dns-manual-mode-enough-go-ahead-please -d DOMAIN

    Set the manual DNS stuff and then change --issue to --renew
      bash acme.sh --renew --dns --yes-I-know-dns-manual-mode-enough-go-ahead-please -d DOMAIN

    Then run this program with --ssl-domain which hopefully grabs certs from ~/.acme.sh/
      websocket_proxy --ssl-domain=DOMAIN ...

    """)
    parser = argparse.ArgumentParser(usage=usage)
    parser.add_argument('--target', default="ws://localhost:4455")
    parser.add_argument('--ssl-domain', metavar='DOMAIN',
                        help="Automatically find acme.sh certs from ~/.acme.sh/DOMAIN_ecc/")
    parser.add_argument('--cert', help="Manual SSL .cer path")
    parser.add_argument('--key', help="Manual SSL .key path")
    parser.add_argument('bind', nargs='?', default='0.0.0.0:4445',
                        help="local bind, format ADDRESS:PORT, default=%(default)s")
    args = parser.parse_args()
    print(args.bind)

    ssl_context = None
    if args.ssl_domain:
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(
            certfile=os.path.expanduser(f'~/.acme.sh/{args.ssl_domain}_ecc/fullchain.cer'),
            keyfile=os.path.expanduser(f'~/.acme.sh/{args.ssl_domain}_ecc/{args.ssl_domain}.key'),
            )

    if args.cert:
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(certfile=args.cert, keyfile=args.key)

    asyncio.run(main(target_url=args.target))

