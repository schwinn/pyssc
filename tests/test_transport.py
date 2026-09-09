"""Offline transport regressions. Only the loopback test opens a TCP socket."""

import json
import socket
import threading
import unittest
from unittest.mock import Mock, patch

from pyssc.ssc_device import Ssc_device


QUERY = '{"device":{"name":null}}'


class TransportTests(unittest.TestCase):
    def device(self, chunks):
        device = Ssc_device("test", "::1")
        device.connected = True
        device.socket = Mock()
        device.socket.gettimeout.return_value = 4.0
        device.socket.recv.side_effect = chunks
        return device

    def test_small_response_is_unchanged(self):
        response = b'{"name":"test"}\r\n'
        device = self.device([response])
        self.assertEqual(device.send_ssc(QUERY, interface="").RX, response.decode())

    def test_fragmented_response_larger_than_default_buffer(self):
        response = json.dumps({"schema": list(range(600))}).encode() + b"\r\n"
        device = self.device([response[i:i + 512] for i in range(0, len(response), 512)])
        transaction = device.send_ssc(QUERY, interface="")
        self.assertEqual(transaction.RX, response.decode())
        self.assertEqual(json.loads(transaction.RX)["schema"], list(range(600)))

    def test_split_terminators(self):
        for separator in (b"\r\n", b"\n\n"):
            with self.subTest(separator=separator):
                device = self.device([b"{}" + separator[:1], separator[1:]])
                self.assertEqual(device.send_ssc(QUERY).RX, (b"{}" + separator).decode())

    def test_single_newline_inside_pretty_printed_json_is_not_a_boundary(self):
        response = b'{\n"name":\n"test"\n}\r\n'
        device = self.device([response[:2], response[2:9], response[9:]])
        self.assertEqual(device.send_ssc(QUERY).RX, response.decode())

    def test_utf8_character_split_between_reads_is_not_corrupted(self):
        response = '{"name":"Küche"}\r\n'.encode()
        split = response.index("ü".encode()) + 1
        device = self.device([response[:split], response[split:]])
        self.assertEqual(device.send_ssc(QUERY).RX, response.decode())

    def test_every_split_position_of_a_response(self):
        response = '{"name":"Küche","value":42}\r\n'.encode()
        for split in range(1, len(response)):
            with self.subTest(split=split):
                device = self.device([response[:split], response[split:]])
                self.assertEqual(device.send_ssc(QUERY).RX, response.decode())

    def test_coalesced_frames_are_returned_separately_by_reader(self):
        device = self.device([b'{"a":1}\r\n{"b":2}\n\n'])
        self.assertEqual(device._receive_message(512, 1024), b'{"a":1}\r\n')
        self.assertEqual(device._receive_message(512, 1024), b'{"b":2}\n\n')
        device.socket.recv.assert_called_once()

    def test_buffered_extra_frame_is_not_misattributed_to_next_command(self):
        device = self.device([b'{"a":1}\r\n{"b":2}\r\n'])
        self.assertEqual(device.send_ssc(QUERY).RX, '{"a":1}\r\n')
        self.assertIs(device.send_ssc(QUERY), False)
        device.socket.sendall.assert_called_once()
        self.assertFalse(device.connected)
        self.assertIn("buffered", device.error)

    def test_partial_extra_frame_also_blocks_next_command(self):
        device = self.device([b'{}\r\n{"b":'])
        self.assertEqual(device.send_ssc(QUERY).RX, '{}\r\n')
        self.assertIs(device.send_ssc(QUERY), False)
        device.socket.sendall.assert_called_once()

    def test_eof_does_not_return_partial_or_empty_transaction(self):
        for chunks in ([b""], [b'{"a":', b""]):
            with self.subTest(chunks=chunks):
                device = self.device(chunks)
                self.assertIs(device.send_ssc(QUERY), False)
                self.assertFalse(device.connected)
                self.assertIn("closed", device.error)
                device.socket.close.assert_called_once()

    def test_timeout_invalidates_partial_response_and_does_not_retry(self):
        device = self.device([b'{"a":', socket.timeout("timed out")])
        self.assertIs(device.send_ssc(QUERY), False)
        self.assertFalse(device.connected)
        self.assertEqual(device._receive_buffer, b"")
        device.socket.close.assert_called_once()
        device.socket.sendall.assert_called_once_with((QUERY + "\r\n").encode())
        self.assertIs(device.send_ssc(QUERY), False)
        device.socket.sendall.assert_called_once()

    def test_send_failure_does_not_receive_or_retry(self):
        device = self.device([])
        device.socket.sendall.side_effect = OSError("send failed")
        self.assertIs(device.send_ssc(QUERY), False)
        self.assertEqual(device.error, "send failed")
        device.socket.recv.assert_not_called()
        device.socket.sendall.assert_called_once()
        device.socket.close.assert_called_once()

    def test_size_limit_rejects_complete_and_unterminated_oversize_messages(self):
        for response in (b"123456789", b"1234567\r\n"):
            with self.subTest(response=response):
                device = self.device([response])
                self.assertIs(device.send_ssc(QUERY, max_response_bytes=8), False)
                self.assertFalse(device.connected)
                self.assertIn("limit", device.error)

    def test_response_at_size_limit_is_accepted(self):
        device = self.device([b"{}\r\n"])
        self.assertEqual(device.send_ssc(QUERY, max_response_bytes=4).RX, "{}\r\n")

    def test_invalid_limits_send_nothing(self):
        for kwargs in ({"buffersize": 0}, {"buffersize": -1}, {"max_response_bytes": 0}):
            with self.subTest(kwargs=kwargs):
                device = self.device([])
                with self.assertRaises(ValueError):
                    device.send_ssc(QUERY, **kwargs)
                device.socket.sendall.assert_not_called()

    def test_receive_deadline_does_not_restart_for_each_chunk(self):
        device = self.device([b'{"a":'])
        with patch("pyssc.ssc_device.time.monotonic", side_effect=[0.0, 1.0, 4.1]):
            self.assertIs(device.send_ssc(QUERY), False)
        self.assertIn("timed out", device.error)
        device.socket.recv.assert_called_once()
        self.assertFalse(device.connected)

    def test_timeout_is_restored_after_success(self):
        device = self.device([b"{}\r\n"])
        device.send_ssc(QUERY)
        self.assertEqual(device.socket.settimeout.call_args.args, (4.0,))

    def test_explicit_blocking_socket_is_supported(self):
        device = self.device([b'{', b'}\r\n'])
        device.socket.gettimeout.return_value = None
        self.assertEqual(device.send_ssc(QUERY).RX, '{}\r\n')
        device.socket.settimeout.assert_called_once_with(None)

    def test_disconnect_clears_receive_state(self):
        device = self.device([])
        device._receive_buffer = bytearray(b"old bytes")
        device.disconnect()
        self.assertFalse(device.connected)
        self.assertEqual(device._receive_buffer, b"")

    def test_reconnect_clears_receive_state(self):
        device = self.device([])
        device._receive_buffer = bytearray(b"old bytes")
        device.error = "old error"
        with patch("pyssc.ssc_device.socket.socket"), patch(
            "pyssc.ssc_device.socket.getaddrinfo",
            return_value=[(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 45, 0, 0))],
        ):
            self.assertTrue(device.connect(interface=""))
        self.assertEqual(device._receive_buffer, b"")
        self.assertEqual(device.error, "")

    def test_ipv6_loopback_server_large_response_and_two_transactions(self):
        listener = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        self.addCleanup(listener.close)
        try:
            listener.bind(("::1", 0))
        except OSError as exc:
            self.skipTest("IPv6 loopback unavailable: " + str(exc))
        listener.listen(1)
        listener.settimeout(3)
        port = listener.getsockname()[1]
        replies = [json.dumps({"values": list(range(600))}).encode() + b"\r\n", b"{}\n\n"]
        received = []
        errors = []

        def server():
            try:
                connection, _ = listener.accept()
                with connection:
                    connection.settimeout(3)
                    for response in replies:
                        request = bytearray()
                        while not request.endswith(b"\r\n"):
                            chunk = connection.recv(1)
                            if not chunk:
                                raise RuntimeError("client closed early")
                            request.extend(chunk)
                        received.append(bytes(request))
                        for i in range(0, len(response), 37):
                            connection.sendall(response[i:i + 37])
            except Exception as exc:
                errors.append(exc)

        worker = threading.Thread(target=server, daemon=True)
        worker.start()
        device = Ssc_device("loopback", "::1")
        try:
            self.assertTrue(device.connect(interface="", port=port, timeout=2))
            for response in replies:
                result = device.send_ssc(QUERY, interface="", port=port, buffersize=31)
                self.assertIsNot(result, False, device.error)
                self.assertEqual(result.RX, response.decode())
        finally:
            device.disconnect()
            worker.join(timeout=4)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(received, [(QUERY + "\r\n").encode()] * 2)


if __name__ == "__main__":
    unittest.main()
