import socket
import time
import logging
from .ssc_transaction import Ssc_transaction


class Ssc_device():
    """
    :param name: device name
    :param ip: ip address of ssc device

    .. code-block:: python
        :caption: todo

        >>> todo

    """
    def __init__(self,
                 name: str,
                 ip: str = None,
                 port: int = 45):
        self.name = name
        self.ip = ip
        self.socket = None
        self.port = port
        self.connected = False
        self.error = ""
        self._receive_buffer = bytearray()

    def connect(self, interface: str = "%eth0", port: int = 45, timeout: int=4):
        if self.socket is not None:
            self.disconnect()
        self._receive_buffer.clear()
        self.error = ""
        self.port = port
        self.socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        self.socket.setblocking(True)
        self.socket.settimeout(timeout)
        sock_addr = socket.getaddrinfo(self.ip + interface, port, socket.AF_INET6, proto=6)[0][4]
        try:
          self.socket.connect(sock_addr)
        except socket.error as err:
          self.connected =  False
          self.error = err
          return False

        self.connected = True
        return True


    def disconnect(self):
        self.connected = False
        self._receive_buffer.clear()
        if self.socket is not None:
            self.socket.close()

    def _receive_message(self, buffersize, max_response_bytes):
        """Read one SSC TCP frame (CRLF or LF LF), retaining any following bytes."""
        timeout = self.socket.gettimeout()
        deadline = None if timeout is None else time.monotonic() + timeout
        search_from = 0
        try:
            while True:
                boundaries = [self._receive_buffer.find(separator, search_from)
                              for separator in (b'\r\n', b'\n\n')]
                boundaries = [position for position in boundaries if position >= 0]
                if boundaries:
                    end = min(boundaries) + 2
                    if end > max_response_bytes:
                        raise ValueError("SSC response exceeds size limit")
                    message = bytes(self._receive_buffer[:end])
                    del self._receive_buffer[:end]
                    return message
                if len(self._receive_buffer) >= max_response_bytes:
                    raise ValueError("SSC response exceeds size limit")
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise socket.timeout("SSC response timed out")
                    self.socket.settimeout(remaining)
                search_from = max(0, len(self._receive_buffer) - 1)
                chunk = self.socket.recv(min(
                    buffersize, max_response_bytes - len(self._receive_buffer)
                ))
                if not chunk:
                    raise ConnectionError("Connection closed before a complete SSC response")
                self._receive_buffer.extend(chunk)
        finally:
            self.socket.settimeout(timeout)

    def send_ssc(self,
                 command: str,
                 interface: str = "%eth0",
                 buffersize: int = 512,
                 port: int = 45,
                 max_response_bytes: int = 1024 * 1024):
        self.port = port
        if not self.connected:
            return False
        if buffersize <= 0 or max_response_bytes <= 0:
            raise ValueError("buffersize and max_response_bytes must be positive")
        if self._receive_buffer:
            # This synchronous API has no subscription/transaction dispatcher.
            # Do not mistake already-buffered data for the next command's reply.
            self.error = "Unexpected buffered SSC data; reconnect before sending another command"
            self.disconnect()
            return False

        request_raw = f'{command}\r\n'.encode('utf-8')
        try:
            # The socket is already connected, including its IPv6 scope.
            self.socket.sendall(request_raw)
            data = self._receive_message(buffersize, max_response_bytes)
        except Exception as e:
            self.error = str(e)
            self.disconnect()
            return False

        ssc_transaction = Ssc_transaction()
        ssc_transaction.TX = command
        ssc_transaction.RX = data.decode('utf-8', errors='replace')
        return ssc_transaction
