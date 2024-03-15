"""
Created on Fri 22 Dec 2023:
@author: carey chomsoonthorn
"""
import struct
import fnmatch
import asyncio
from typing import Tuple, Any, Optional, List

SLIP_END = 0xC0
SLIP_ESC = 0xDB
SLIP_ESC_END = 0xDC
SLIP_ESC_ESC = 0xDD


def process_slip_message(buffer: bytes) -> (list, bytes):
    messages = []
    while True:
        if b'\xc0' in buffer:
            end_idx = buffer.find(b'\xc0', 1) + 1
            if end_idx > 1:
                message = buffer[:end_idx]
                messages.append(message)
                buffer = buffer[end_idx:]
            else:
                # If a message starts but does not end, keep it in the buffer
                break
        else:
            break
    return messages, buffer


def slip_encode(data: bytearray) -> bytearray:
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


def slip_decode(data: bytearray) -> bytearray:
    """
    Decoding a SLIP-encoded byte-array into an OSC message.
    :param data: slip encoded bytearray
    :return decoded: bytearray of the decoded message
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


def create_osc_message(address: str, *args: Optional[Tuple[Any]]) -> bytes:
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
    if args is not None:
        for arg, arg_type in zip(args, type_tags):
            print(f"{arg}, {arg_type}")
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
        current_pos = type_tag_end + 1
        if current_pos % 4 != 0:
            current_pos += (4 - current_pos % 4)
        for tag in type_tags:
            value = None
            if tag == 'i':
                value = struct.unpack('>i', data[current_pos:current_pos + 4])[0]
                current_pos += 4
            elif tag == 'f':
                (value,) = struct.unpack('>f', data[current_pos:current_pos + 4])
                current_pos += 4
            elif tag == 's':
                string_end = data.find(b'\0', current_pos)
                value = data[current_pos:string_end].decode()
                # Advance current_pos to the next 4-byte boundary after the null terminator
                current_pos = string_end + 1
                if current_pos % 4 != 0:
                    current_pos += (4 - current_pos % 4)
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


def split_osc_message(address) -> List[str, ...]:
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
        self.reader, self.writer = await asyncio.open_connection(*self.server_address)

    def is_connected(self):
        return self.reader is not None and self.writer is not None

    def alter_server_address(self, new_server_address: Tuple[str, int]):
        """ If you are in need of changing the address of the server """
        self.server_address = new_server_address

    async def add_message(self, message: str, *args):
        """
        Add a message to the message buffer.
        This is the main function for sending OSC messages
        to the server.
        :param message: OSC address, e.g., /example/1/2/fire
        :param args: Arguments that consist of a data-type and a type tag, e.g., (42, 'i')
        :return:
        """
        if args:
            packed_message = message, *args
        else:
            packed_message = message, None
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
                if not self.message_buffer:
                    return None, None
                return self.message_buffer.pop(0)

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
            else:
                if args is not None:
                    message_byte = create_osc_message(message, args)
                else:
                    message_byte = create_osc_message(message)
                try:
                    slip_message = slip_encode(message_byte)
                    self.writer.write(slip_message)
                    await self.writer.drain()
                except Exception as e:
                    print(f"Failed to send message: {e}")
                    continue

        print("Send Handler Stopped")

    async def listen(self):
        if self.reader is None:
            raise ConnectionError("Not connected to server")

        buffer = bytearray()
        while self.running:
            try:
                data = await self.reader.read(1024)
                if not data:
                    break

                buffer.extend(data)
                messages, buffer = process_slip_message(buffer)

                for message in messages:
                    decoded_message = slip_decode(message)
                    # print(f"Raw data length: {len(decoded_message)}, content: {decoded_message}")
                    address, arguments = parse_osc_message(decoded_message)
                    if address is not None:
                        await self.dispatcher.dispatch(address, arguments)
            except asyncio.CancelledError:
                break
            except Exception as e:
                error = f"Error while listening: {e}"
                raise Exception(error) from e

    async def close(self):
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()

    async def shutdown(self):
        self.running = False

        await self.close()

        tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()

        await asyncio.gather(*tasks, return_exceptions=True)

    async def run(self):
        try:
            await self.connect()

            self.running = True

            listen_task = asyncio.create_task(self.listen())
            send_task = asyncio.create_task(self.send_messages())

            await asyncio.gather(listen_task, send_task)
        except asyncio.CancelledError:
            pass
        except (OSError, ConnectionRefusedError):
            pass


class AsyncTCPServer:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.dispatcher = Dispatcher()

    async def listen(self, reader, writer):
        while True:
            data = await reader.read(100)
            if not data:
                break  # Connection closed by client

    async def start(self):
        server = await asyncio.start_server(self.listen, self.host, self.port)
        addr = server.sockets[0].getsockname()
        print(f'Serving on {addr}')

        async with server:
            await server.serve_forever()


class AsyncTCPRedirectingServer(AsyncTCPServer):
    def __init__(self, host, port):
        super().__init__(host, port)
        self.connected_clients = {}  # Maps usernames to their (reader, writer) tuples

    async def listen(self, reader, writer):
        ...
