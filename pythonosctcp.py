"""
Created on Fri 22 Dec 2023:
@author: carey chomsoonthorn
"""
import struct
import fnmatch
import asyncio
from typing import Tuple, Any

SLIP_END = 0xC0
SLIP_ESC = 0xDB
SLIP_ESC_END = 0xDC
SLIP_ESC_ESC = 0xDD


def slip_encode(data):
    """
    Encode an OSC message into a SLIP-encoded byte-array.
    :param data:
    :return:
    """
    encoded = bytearray()
    encoded.append(SLIP_END)
    for byte in data:
        if byte == SLIP_END:
            encoded.append(SLIP_ESC)
            encoded.append(SLIP_ESC_END)
        elif byte == SLIP_ESC:
            encoded.append(SLIP_ESC)
            encoded.append(SLIP_ESC_ESC)
        else:
            encoded.append(byte)
    encoded.append(SLIP_END)
    return encoded


def slip_decode(data):
    """
    Decoding a SLIP-encoded byte-array into an OSC message.
    :param data:
    :return:
    """
    decoded = bytearray()
    i = 0
    while i < len(data):
        if data[i] == SLIP_END:
            i += 1
            continue
        elif data[i] == SLIP_ESC:
            i += 1
            if data[i] == SLIP_ESC_END:
                decoded.append(SLIP_END)
            elif data[i] == SLIP_ESC_ESC:
                decoded.append(SLIP_ESC)
            continue
        else:
            decoded.append(data[i])
        i += 1
    return decoded


def create_osc_message(address: str, *args: Any) -> bytes:
    """
    Create an OSC message from a string, automatically generating type tags.

    :param address: OSC address, e.g., '/example'
    :param args: Variable-length arguments
    :return: OSC message as bytes

    Example usage:
        osc_address = '/example'
        args = (42, 3.14, 'Hello, OSC!')
    """
    if not address.startswith('/'):
        raise ValueError("OSC address must start with '/'")

    address = address + '\0' * (4 - len(address) % 4)
    type_tags = ''.join(map(get_type_tag, args))
    type_tag = ',' + type_tags + '\0' * (4 - (len(type_tags) + 1) % 4)

    arg_values = b''
    for arg, arg_type in zip(args, type_tags):
        if arg_type == 'i':  # Integer
            arg_values += struct.pack('>i', arg)
        elif arg_type == 'f':  # Float
            arg_values += struct.pack('>f', arg)
        elif arg_type == 's':  # String
            padded_string = arg + '\0' * (4 - len(arg) % 4)
            arg_values += padded_string.encode()
        elif arg_type == 'T':
            arg_values += b'T'
        elif arg_type == 'F':
            arg_values += b'F'

    return address.encode() + type_tag.encode() + arg_values


def get_type_tag(arg: Any) -> str:
    if isinstance(arg, int):
        return 'i'
    elif isinstance(arg, float):
        return 'f'
    elif isinstance(arg, str):
        return 's'
    elif isinstance(arg, bool):
        if arg:
            return 'T'
        else:
            return 'F'
    else:
        raise ValueError(f"Unsupported argument type: {type(arg)}")


def parse_osc_message(data):
    """
    Parse an OSC message from a byte stream.
    :param data: Byte stream
    :return: Parsed message
    """
    try:
        # Basic validation
        if not data.startswith(b'/'):
            raise ValueError("Invalid OSC address")

        address_end = data.find(b'\0')
        address = data[:address_end].decode()

        type_tag_start = data.find(b',', address_end) + 1
        type_tag_end = data.find(b'\0', type_tag_start)
        type_tags = data[type_tag_start:type_tag_end].decode()

        arguments = []
        current_pos = type_tag_end + 1 + (4 - type_tag_end % 4)
        for tag in type_tags:
            value = None
            if tag == 'i':
                (value,) = struct.unpack('>i', data[current_pos:current_pos + 4])
                current_pos += 4
            elif tag == 'f':
                (value,) = struct.unpack('>f', data[current_pos:current_pos + 4])
                current_pos += 4
            elif tag == 's':
                string_end = data.find(b'\0', current_pos)
                value = data[current_pos:string_end].decode()
                current_pos = string_end + 1 + (4 - (string_end + 1) % 4)  # Align to 4-byte boundary
            elif tag == 'T':
                value = True
            elif tag == 'F':
                value = False
            # Add more types as needed
            arguments.append(value)

        return address, arguments

    except Exception as e:
        print(f"Error parsing OSC message: {e}")
        return None, None


def split_osc_message(address):
    """
    Split an OSC address into its components.
    :param address:
    :return:
    """
    if address.startswith('/'):
        address = address[1:]

    components = address.split('/')
    return components


class Dispatcher:
    """
    Dispatcher is responsible for handling incoming OSC messages
    """
    def __init__(self):
        self.default_handler = None
        self.handlers = {}

    def map(self, address, handler):
        """
        Maps OSC messages to their corresponding handlers
        :param address: OSC address to map, e.g., /example
        :param handler: Handler function for address
        :return:
        """
        if not asyncio.iscoroutinefunction(handler):
            raise TypeError('Handler must be an async coroutine function.')
        self.handlers[address] = handler

    def unmap(self, address):
        """
        Unmaps OSC messages from their corresponding handlers
        :param address: OSC address to unmap, e.g., /example
        :return:
        """
        if address in self.handlers:
            del self.handlers[address]
        else:
            print(f"No handler found for {address}")

    async def dispatch(self, address, *args):
        """
        Executes handlers with (address, args).
        If no handlers are defined, the default handler is used.
        If no default handler is defined, then the message will
        not be dispatched.
        :param address:
        :param args:
        :return:
        """
        for pattern, handler in self.handlers.items():
            if fnmatch.fnmatch(address, pattern):
                await handler(address, *args)
                return

        if self.default_handler:
            await self.default_handler(address, *args)

    def set_default_handler(self, handler):
        """
        Sets the default handler for all unassigned OSC addresses.
        :param handler:
        :return:
        """
        if not asyncio.iscoroutinefunction(handler):
            raise TypeError('Default handler must be an async coroutine function.')
        self.default_handler = handler


class AsyncTCPServer:
    """
    A simple TCP server that listens for OSC messages and
    sends them to the dispatcher.
    Uses asyncio to handle simultaneous OSC messages.
    """
    def __init__(self, socket_address: Tuple[str, int], dispatcher: Dispatcher):
        self.socket_address = socket_address
        self.ip, self.port = socket_address
        self.dispatcher = dispatcher
        self.server = None

    async def start(self):
        self.server = await asyncio.start_server(
            self.handle_request,
            self.socket_address[0],
            self.socket_address[1]
        )
        print(f'Server started on {self.ip}:{self.port}')
        async with self.server:
            await self.server.serve_forever()

    async def handle_request(self, reader, writer):
        addr = writer.get_extra_info('peername')
        print(f'Connected to {addr}')
        while True:
            data = await reader.read(1024)
            if not data:
                break
            decoded_data = slip_decode(data)
            address, arguments = parse_osc_message(decoded_data)
            if address is not None:
                await self.dispatcher.dispatch(address, arguments)
        writer.close()

#
# HOW TO IMPLEMENT
#
# async def main():
#     dispatcher = Dispatcher()  # Assuming Dispatcher is set up correctly
#     server = TCPServer(('127.0.0.1', 65432), dispatcher)
#     await server.start()
#
# if __name__ == '__main__':
#     asyncio.run(main())
#


class AsyncTCPClient:
    """
    A simple OSC TCP client aligned for asynchronous
    bidirectional communication, using OSC v1.1 SLIP protocol.
    """
    def __init__(self, server_address: Tuple[str, int], dispatcher: Dispatcher):
        self.server_address = server_address
        self.dispatcher = dispatcher
        self.message_buffer = []
        self.message_lock = asyncio.Lock()
        self.reader = None
        self.writer = None
        self.running = False

    async def connect(self):
        """
        Connect to the server.
        :return:
        """
        try:
            self.reader, self.writer = await asyncio.open_connection(*self.server_address)
        except Exception as e:
            print(f"Could not connect to {self.server_address}: {e}")
            raise

    async def add_message(self, message: str, *args: Tuple[Any, ...]):
        """
        Add a message to the message buffer.
        This is the main function for sending OSC messages
        to the server.
        :param message: OSC address, e.g., /example/1/2/fire
        :param args: Arguments that consist of a data-type and a type tag, e.g., (42, 'i')
        :return:
        """
        packed_message = message, args
        async with self.message_lock:
            self.message_buffer.append(packed_message)

    async def get_message(self):
        """
        Gets message from the message buffer.
        Used by the send_messages() function.
        :return: A tuple containing the message and the arguments, else returning None, None
        """
        async with self.message_lock:
            try:
                message = self.message_buffer.pop(0)
                return message
            except IndexError:
                return None, None

    async def send_messages(self):
        """
        Sends OSC messages from the buffer to the server.
        Encodes the messages into a bytearray and then encodes it to SLIP protocol.
        :return:
        """
        if self.writer is None:
            raise ConnectionError("Not connected to server")

        while self.running:
            message, args = await self.get_message()
            if message is None:
                await asyncio.sleep(0.05)
                continue
            try:
                message_byte = create_osc_message(message, args)
                slip_message = slip_encode(message_byte)
                self.writer.write(slip_message)
                await self.writer.drain()
            except Exception as e:
                print(f"Failed to send message: {e}")
                raise

    async def listen(self):
        if self.reader is None:
            raise ConnectionError("Not connected to server")

        while self.running:
            try:
                data = await self.reader.read(1024)
                if not data:
                    break

                decoded_data = slip_decode(data)
                address, arguments = parse_osc_message(decoded_data)
                if address is not None:
                    await self.dispatcher.dispatch(address, arguments)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error while listening: {e}")
                raise

    async def close(self):
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()

    async def shutdown(self):
        self.running = False

        tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]

        for task in tasks:
            task.cancel()

        await asyncio.gather(*tasks, return_exceptions=True)

        await self.close()

    async def run(self):
        try:
            await self.connect()

            self.running = True

            listen_task = asyncio.create_task(self.listen())

            send_task = asyncio.create_task(self.send_messages())

            await listen_task
            await send_task

        except asyncio.CancelledError:
            pass