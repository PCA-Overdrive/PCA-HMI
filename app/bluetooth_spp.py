"""
Bluetooth SPP server for Android app exit commands.

This runs independently from Flask and CAN so a blocking RFCOMM accept/recv
does not stall the display server.
"""

import os
import socket
import threading
import time

try:
    from can_controller import env_bool
except ImportError:
    from .can_controller import env_bool


EXIT_COMMANDS = {
    "CANCEL_EXIT": 0,
    "LEFT_EXIT": 1,
    "RIGHT_EXIT": 2,
    "STRAIGHT_EXIT": 3,
}


class BluetoothSppServer:
    def __init__(self, on_exit_command=None):
        self.on_exit_command = on_exit_command
        self.enabled = env_bool("BLUETOOTH_ENABLED", False)
        self.channel = int(os.getenv("BLUETOOTH_RFCOMM_CHANNEL", "1"))
        self.restart_delay = float(os.getenv("BLUETOOTH_RESTART_DELAY", "2"))
        self.running = False
        self.thread = None

    def start(self):
        if not self.enabled:
            return False
        if self.running:
            return True

        self.running = True
        self.thread = threading.Thread(target=self._serve_forever, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        self.running = False

    def _serve_forever(self):
        while self.running:
            server_sock = None
            client_sock = None

            try:
                print("Bluetooth SPP server starting...", flush=True)
                server_sock = self._create_server_socket()
                server_sock.bind(("", self.channel))
                server_sock.listen(1)
                print(f"Waiting for Android connection on RFCOMM channel {self.channel}", flush=True)

                client_sock, client_info = server_sock.accept()
                print(f"Android connected: {client_info}", flush=True)
                self._handle_client(client_sock)
            except Exception as exc:
                if self.running:
                    print(f"Bluetooth SPP error: {exc}", flush=True)
            finally:
                self._close_socket(client_sock)
                self._close_socket(server_sock)

            if self.running:
                print(
                    f"Bluetooth SPP disconnected. Restarting in {self.restart_delay:g}s...",
                    flush=True,
                )
                time.sleep(self.restart_delay)

    @staticmethod
    def _create_server_socket():
        if hasattr(socket, "AF_BLUETOOTH") and hasattr(socket, "BTPROTO_RFCOMM"):
            return socket.socket(
                socket.AF_BLUETOOTH,
                socket.SOCK_STREAM,
                socket.BTPROTO_RFCOMM,
            )

        try:
            from bluetooth import BluetoothSocket, RFCOMM
        except ImportError as exc:
            raise RuntimeError("Bluetooth RFCOMM socket is not available") from exc

        return BluetoothSocket(RFCOMM)

    def _handle_client(self, client_sock):
        buffer = ""

        while self.running:
            data = client_sock.recv(1024)
            if not data:
                print("Android disconnected", flush=True)
                break

            buffer += data.decode("utf-8", errors="ignore")

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                self._handle_packet(line, client_sock)

    def _handle_packet(self, packet, client_sock):
        packet = packet.strip()
        if not packet:
            return

        print(f"Bluetooth SPP received: {packet}", flush=True)
        command = EXIT_COMMANDS.get(packet)

        if command is None:
            print(f"Unknown Bluetooth SPP packet: {packet}", flush=True)
            return

        if self.on_exit_command:
            self.on_exit_command(packet, command)

        if packet == "CANCEL_EXIT":
            self._send_line(client_sock, "EXIT_CANCELED")
        else:
            self._send_line(client_sock, "EXIT_DONE")

    @staticmethod
    def _send_line(sock, message):
        try:
            payload = f"{message}\n"
            try:
                sock.send(payload)
            except TypeError:
                sock.send(payload.encode("utf-8"))
            print(f"Bluetooth SPP sent: {message}", flush=True)
        except Exception as exc:
            print(f"Bluetooth SPP send failed: {exc}", flush=True)

    @staticmethod
    def _close_socket(sock):
        if sock is None:
            return
        try:
            sock.close()
        except Exception:
            pass
