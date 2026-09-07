# pyssc
A Sennheiser Sound Control Protocol (SSC) Client Implementation for Python

## Introduction 

The [Sennheiser Sound Control Protocol](https://assets.sennheiser.com/global-downloads/file/9541/TI_1093_v2.0_Sennheiser_Sound_Control_Protocol_ew_D1_EN.pdf) is a specific adaption of Open Sound Control. Pyssc is a simple client implementation that allows users to discover SSC Devices in their networks and subsequently communicate with those Devices via SSC.

## Installation

Pyssc is published to [pypi.org/pyssc](https://pypi.org/project/pyssc/).


```
pip install pyssc
```

## Usage

Initially you will have to find out the IP Addresses of your SSC Devices. If you don't know them you can try and find them using [zeroconf](https://pypi.org/project/zeroconf/).

```py
import pyssc as ssc
found_setup = ssc.scan()
```

When you know all the IPs you can store the setup as a JSON file.

```py
found_setup.to_json('setup.json')
```

Here's an example setup JSON:

```json
{
    "Device 1": "fe80::2a36:38ff:fe60:7515",
    "Device 2": "fe80::2a36:38ff:fe60:784f",
}
```

Once you have defined your setups as a JSON you don't need to scan anymore. Simply import your setup at the beginning of your session.

```py
found_setup = ssc.Ssc_device_setup()
found_setup.from_json('setup.json')
```

Now you can send and receive SSC either to and from a single device
```py
device_1 = found_setup.ssc_devices[0]
ssc_transaction = device_1.send_ssc('{"audio":{"out":{"mute":true}}}')
```

or the whole setup.

```py
found_setup.send_all('{"audio":{"out":{"mute":true}}}')
```

Please note that Unix systems require you to specify the network interface. The default value here is "%eth0". On Windows you can specify an empty String as the Value for "interface".

```py
ssc_transaction = device_1.send_ssc('{"audio":{"out":{"mute":true}}}', interface = "")
```

To find out which commands work for your specific SSC Device please refer to the [SSC Documentation](https://assets.sennheiser.com/global-downloads/file/9541/TI_1093_v2.0_Sennheiser_Sound_Control_Protocol_ew_D1_EN.pdf).

## TCP response handling

Call `connect()` before `send_ssc()`. The connected socket determines the peer,
port and IPv6 scope; `send_ssc()` does not change that connection or retry commands.

`buffersize` (default 512) is a receive chunk size, not a maximum message size.
The client reads until a complete SSC TCP separator, CRLF or LF LF, as defined
in section 6.2 of the SSC specification linked above. `RX` retains that separator.
UTF-8 decoding takes place after all bytes of the frame have arrived.

`max_response_bytes` defaults to 1 MiB including the separator, and can be raised
explicitly for a larger expected response. The socket timeout configured by
`connect()` bounds the whole response read, not each individual fragment.
An explicitly blocking socket (`timeout=None`) has no time deadline.

On EOF, timeout or an oversized response, `send_ssc()` returns `False`, records
`error`, closes the connection and clears partial data. It never returns a partial
transaction as a success or automatically resends a command. A failed response
does **not** establish whether the device applied a setting; query its state after
reconnecting before deciding what to do next.

This remains a synchronous, one-command/one-response API, not a subscription or
transaction-ID dispatcher. If extra bytes have already been buffered after the
first frame, the next `send_ssc()` fails before sending and closes the connection,
rather than presenting those old bytes as a new reply. Do not mix unsolicited
notifications with these synchronous calls.

## Offline transport tests

Install the dependencies, then run:

```
python -m unittest discover -s tests -p test_transport.py -v
```

Tests use mocked sockets and an IPv6 loopback server (`::1` on an ephemeral port).
No network discovery or real SSC equipment is used.
