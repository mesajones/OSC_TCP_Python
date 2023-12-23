import asyncio
import shlex
import configparser

from pythonosctcp import Dispatcher, AsyncTCPClient


config = configparser.ConfigParser()
config.read('config.ini')

SERVER_ADDRESS = config['IPCONFIG']['target_ip'], int(config['IPCONFIG']['port'])


async def handler(address, *args):
    print(f"Received: {address} ; {args} ")


dispatcher = Dispatcher()
dispatcher.set_default_handler(handler)
client = AsyncTCPClient(SERVER_ADDRESS, dispatcher)


def parse_user_input():
    address = input("Address: ")
    if address.lower() == 'exit':
        return 'exit', []

    args_input = input("Arguments: ")

    args = []
    for arg in shlex.split(args_input):
        if arg.isdigit():
            args.append(int(arg))
        elif arg.replace('.', '', 1).isdigit():
            args.append(float(arg))
        else:
            args.append(arg)

    return address, args


async def main():
    await client.connect()
    await client.run()

    while True:
        address, args = await asyncio.to_thread(parse_user_input)
        if address == 'exit':
            print("Shutting down...")
            break
        await client.add_message(address, *args)

    await client.shutdown()


if __name__ == '__main__':
    asyncio.run(main())
