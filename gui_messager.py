import asyncio
import configparser
import errno
import os
import re
import threading

import tkinter as tk
from tkinter import scrolledtext, messagebox, font as f

from datetime import datetime

from pythonosctcp import Dispatcher, AsyncTCPClient

running = True

DEFAULT_SETTINGS = "127.0.0.1", 8000

config = configparser.ConfigParser()
if not os.path.exists('config.ini'):
    print('config.ini not found, creating with default settings.')
    config['NETWORK'] = {
        'RX_IP': DEFAULT_SETTINGS[0],
        'RX_PORT': int(DEFAULT_SETTINGS[1]),
        'TX_IP': DEFAULT_SETTINGS[0],
        'TX_PORT': int(DEFAULT_SETTINGS[1])
    }
    with open('config.ini', 'w') as configfile:
        config.write(configfile)
else:
    # Read the existing config file
    config.read('config.ini')

SERVER_ADDRESS = config.get('NETWORK', 'RX_IP'), int(config.get('NETWORK', 'RX_PORT'))

address_prompt = "Address: "
arguments_prompt = "Arguments: "

FOREGROUND = "#FCFCFA"
BACKGROUND = "#2D2A2E"


def on_close():
    global running
    running = False
    tk_app_root.quit()


def console_update(entry):
    gui.console_entry(entry)


async def handle(address, *args):
    message = f"Received: {address}, {args}"
    loop.call_soon_threadsafe(console_update, message)


def parse_element(element):
    element = element.strip()
    try:
        return int(element)
    except ValueError:
        pass

    try:
        return float(element)
    except ValueError:
        pass

    if element.lower() == 'True':
        return True
    if element.lower() == 'False':
        return False

    if element.startswith(("'", '"')) and element.endswith(("'", '"')):
        return element[1:-1]

    return element


def parse_user_input(loop, client, address, args_input):
    global running
    try:
        if not address.startswith('/'):
            raise ValueError(
                f'Invalid address input: {address} - '
                f'OSC addresses must begin with a forward-slash'
            )

        args = []
        if args_input:
            args_list = args_input.split(', ')
            args = [parse_element(arg) for arg in args_list]
        try:
            asyncio.run_coroutine_threadsafe(client.add_message(address, *args), loop)
        except Exception as e:
            console_update(e)
    except ValueError as e:
        console_update(e)
        pass


async def start_client(client):
    client_started = False
    server_address = SERVER_ADDRESS

    while not client_started:
        try:
            client_task = asyncio.create_task(client.run())
            console_update(f"Client successfully connected to address {server_address}")
            client_started = True
            return client_task
        except OSError as e:
            if e.errno == errno.EADDRINUSE:
                new_address_future = gui.network_error_prompt()
                new_address = await new_address_future
                if new_address:
                    server_address = new_address
                    client.alter_server_address(server_address)
                else:
                    # Handle cancel
                    return None
            else:
                raise  # Re-raise the exception if it's not errno 48
        except Exception as e:
            console_update(f"An error occurred: {e}")
            raise


def validate_ip(ip):
    # Regex for validating an IP address
    ip_regex = re.compile(r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$')
    return ip_regex.match(ip) is not None


class BaseDialog(tk.Toplevel):
    def __init__(self, parent, title=None):
        super().__init__(parent)
        self.configure(background=BACKGROUND)

        if title:
            self.title(title)

        self.frame = tk.Frame(self)
        self.frame.pack(expand=True, fill=tk.BOTH)

        # Make it modal
        self.transient(parent)
        self.grab_set()

        self.protocol("WM_DELETE_WINDOW", self.on_cancel)  # Handle close button click

        self.initialize_dialog()  # Initialize dialog contents

        self.wait_window()  # Wait for the dialog to close

    def initialize_dialog(self):
        # This method should be overridden by subclasses
        pass

    def on_cancel(self, event=None):
        # Default cancel behavior
        self.destroy()


class NetworkErrorDialog(BaseDialog):
    def initialize_dialog(self):
        # Initialize the dialog contents here
        self.title("Network Error 48: Port already in use")

        self.geometry("400x100")

        self.ip_label = tk.Label(self.frame, text="Enter IP:", bg=BACKGROUND, foreground=FOREGROUND, font=default_font,
                                 justify=tk.RIGHT)
        self.ip_label.grid(row=0, column=0)

        self.ip_entry = tk.Entry(self.frame, bg=BACKGROUND, foreground=FOREGROUND, font=default_font)
        self.ip_entry.grid(row=0, column=1, sticky="ew")

        self.port_label = tk.Label(self.frame, text="Enter Port:", bg=BACKGROUND, foreground=FOREGROUND, font=default_font,
                                   justify=tk.RIGHT)
        self.port_label.grid(row=1, column=0)

        self.port_entry = tk.Entry(self.frame, bg=BACKGROUND, foreground=FOREGROUND, font=default_font)
        self.port_entry.grid(row=1, column=1, sticky="ew")

        self.apply_button = tk.Button(self.frame, text="Apply", command=self.on_apply, bg=BACKGROUND,
                                      font=default_font)
        self.apply_button.grid(row=2, column=0)

        self.cancel_button = tk.Button(self.frame, text="Cancel", command=self.on_cancel,
                                       font=default_font)
        self.cancel_button.grid(row=2, column=1)

    def on_apply(self):
        ip = self.ip_entry.get()
        port = self.port_entry.get()

        if self.validate(ip, port):
            self.result = ip, int(port)  # Convert port to int here
            self.destroy()
        else:
            messagebox.showerror("Error", "Please enter valid IP and port")

    def validate(self, ip, port):
        if not validate_ip(ip):
            messagebox.showerror("Invalid Input", "Invalid IP Address")
            return False

        if not port.isdigit() or not (49152 <= int(port) <= 65535):
            messagebox.showerror("Invalid Input", "Port must be an integer between 49152 and 65535.")
            return False

        return True

    def on_cancel(self, event=None):
        # Handle cancel button click
        self.result = None, None
        self.destroy()


async def main(loop, client, dispatcher):
    console_update("Welcome to the OSC Messenger!")
    try:
        asyncio.set_event_loop(loop)
        console_update("Main loop started.")

        # dispatcher
        dispatcher.set_default_handler(handle)

        console_update("Dispatcher started.")

        # client
        client_task = await start_client(client)

    except Exception as e:
        console_update(e)
        print(e)
        raise

    try:
        while running:
            await asyncio.sleep(1)
    finally:
        console_update("Shutting down...")
        await client.shutdown()
        client_task.cancel()


class GUI:
    def __init__(self, root, loop, client):
        self.root = root
        self.loop = loop
        self.client = client

        self.root.title("OSC Messenger")
        self.root.geometry("800x600")
        self.root.configure(bg=BACKGROUND)

        self.current_prompt = address_prompt
        self.address_string = ''
        self.args = None

        self.clear_confirm = False
        self.indicator_text = "Send", "Clear?"

        self.default_font = default_font

        self.console = scrolledtext.ScrolledText(self.root,
                                                 wrap=tk.WORD,
                                                 height=20,
                                                 font=self.default_font,
                                                 background=BACKGROUND, foreground=FOREGROUND
                                                 )
        self.console.pack(fill=tk.BOTH, expand=1, padx=5, pady=5)

        self.entry_frame = tk.Frame(root)
        self.entry_frame.grid_columnconfigure(1, weight=1)
        self.entry_frame.pack(fill=tk.X, padx=5, pady=2)

        self.prompt_text = tk.Entry(
            self.entry_frame, background=BACKGROUND, foreground=FOREGROUND, font=self.default_font, justify=tk.RIGHT
        )
        self.prompt_text.bind("<Key>", lambda e: "break")

        self.prompt_text.grid(row=0, column=0)

        self.entry_var = tk.StringVar()
        self.entry_var.trace_add("write", self.on_entry_changed)
        self.user_entry = tk.Entry(
            self.entry_frame, background=BACKGROUND, foreground=FOREGROUND, font=self.default_font,
            textvariable=self.entry_var
        )
        self.user_entry.grid(row=0, column=1, sticky="ew")
        self.user_entry.bind("<Return>", self.on_enter_pressed)
        self.user_entry.bind("<Escape>", self.on_escape_pressed)

        self.send_indicator = tk.Entry(
            self.entry_frame, background=BACKGROUND, foreground=FOREGROUND, font=self.default_font, justify=tk.CENTER,
            width=20
        )
        self.send_indicator.grid(row=0, column=2, sticky="ew")
        self.send_indicator.insert(tk.END, self.indicator_text[0])
        self.send_indicator.config(state="disabled")

        self.new_entry_prompt(address_prompt)

    def console_entry(self, entry):
        self.console.insert(tk.END, f"{datetime.now().strftime("%H:%M:%S")} {entry}\n")
        self.console.see(tk.END)

    def new_entry_prompt(self, new_prompt):
        self.user_entry.delete(0, tk.END)
        self.current_prompt = new_prompt
        self.prompt_text.delete(0, tk.END)
        self.prompt_text.insert(tk.END, self.current_prompt)

    def on_enter_pressed(self, event):
        user_input = self.user_entry.get()
        self.console_entry(self.current_prompt + user_input)
        self.user_entry.delete(0, tk.END)

        # If the current prompt is for the address, store the address and change prompt to arguments
        if self.current_prompt == address_prompt:
            self.address_string = user_input
            if not self.address_string.startswith('/'):
                self.console.insert(tk.END,
                                    f'Invalid address input: {self.address_string} - '
                                    f'OSC addresses must begin with a forward-slash'
                                    )
            self.new_entry_prompt(arguments_prompt)

        # If the current prompt is for the arguments, store the arguments
        # Then call the function to process the address and arguments
        elif self.current_prompt == arguments_prompt:
            self.args = user_input
            self.new_entry_prompt(address_prompt)  # Reset prompt back to address
            parse_user_input(self.loop, self.client, self.address_string, self.args)

    def on_escape_pressed(self, event):
        if not self.clear_confirm:
            self.send_indicator.config(state="normal")
            self.send_indicator.delete(0, tk.END)
            self.send_indicator.insert(tk.END, self.indicator_text[1])
            self.clear_confirm = True
        else:
            self.address_string = ''
            self.args = None
            self.new_entry_prompt(address_prompt)
            self.send_indicator.delete(0, tk.END)
            self.send_indicator.insert(tk.END, self.indicator_text[0])
            self.send_indicator.config(state="disabled")

            self.clear_confirm = False

    def on_entry_changed(self, name, index, mode):
        if len(self.user_entry.get()) > 0:
            self.send_indicator.config(state="normal")
        else:
            self.send_indicator.config(state="disabled")

    def network_error_prompt(self):
        future = asyncio.Future()

        def open_dialog():
            dialog = NetworkErrorDialog(self.root)
            result = dialog.result
            if result:
                ip, port = result
                future.set_result((ip, port))
            else:
                future.set_result((None, None))

        self.loop.call_soon_threadsafe(open_dialog)

        return future


def run_asyncio_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()


if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio_thread = threading.Thread(target=run_asyncio_loop, args=(loop,), daemon=True)
    asyncio_thread.start()

    tk_app_root = tk.Tk()
    tk_app_root.protocol("WM_DELETE_WINDOW", on_close)

    available_fonts = f.families()
    font_family = "Spot Mono"
    font_size = 12
    if font_family not in available_fonts:
        print("fuck")
        font_family = "Cascadia Mono"
        font_size = 11
        if font_family not in available_fonts:
            print("fuck")
            font_family = "Monaco"
            if font_family not in available_fonts:
                print("fuck")
                font_family = "Consolas"
                if font_family not in available_fonts:
                    print("fuckfuckfuck")
    default_font = f.Font(family=font_family, size=font_size)

    dispatcher = Dispatcher()
    client = AsyncTCPClient(dispatcher=dispatcher, server_address=SERVER_ADDRESS)

    gui = GUI(tk_app_root, loop, client)

    # Schedule the main coroutine
    asyncio.run_coroutine_threadsafe(main(loop, client, dispatcher), loop)

    tk_app_root.mainloop()

    loop.call_soon_threadsafe(loop.stop)
    asyncio_thread.join()
