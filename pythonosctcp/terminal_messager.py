import asyncio
import shlex
import configparser

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

from pythonosctcp.pythonosctcp import Dispatcher, AsyncTCPClient


config = configparser.ConfigParser()
config.read('config.ini')

SERVER_ADDRESS = config['NETWORK']['RX_IP'], int(config['NETWORK']['RX_PORT'])


async def handler(address, *args):
    print(f"Received: {address} ; {args} ")


dispatcher = Dispatcher()
dispatcher.set_default_handler(handler)
client = AsyncTCPClient(SERVER_ADDRESS, dispatcher)


async def user_input_loop():
    session = PromptSession()

    while True:
        with patch_stdout():
            address = await asyncio.to_thread(session.prompt, "Address: ")
            print("Prompting for arguments...")
            if address.lower() == 'exit':
                await client.shutdown()
                break

            args_input = await asyncio.to_thread(session.prompt, "Arguments: ")
            args = shlex.split(args_input) if args_input.strip() else []

            # Convert args to the correct types as needed
            converted_args = []
            for arg in args:
                if arg.isdigit():
                    converted_args.append(int(arg))
                elif arg.replace('.', '', 1).isdigit() and arg.count('.') == 1:
                    converted_args.append(float(arg))
                else:
                    converted_args.append(arg)

            await client.add_message(address, *converted_args)


async def main():
    await client.connect()

    client_task = asyncio.create_task(client.run())
    input_task = asyncio.create_task(user_input_loop())

    await asyncio.gather(client_task, input_task)

    await client.add_message('/eos/reset')


if __name__ == '__main__':
    asyncio.run(main())
