# Transport Abstraction Layer: Architecture and Sequence Notes

## 1. High-level architecture

```
+-----------------------------------------------------------------------+
|                        CLI / Agent upper layer                        |
+--------------------------+--------------------------------------------+
                           |
                           v
+-----------------------------------------------------------------------+
| MailboxManager                                                        |
| - builds TeamMessage (Pydantic model)                                |
| - serializes to JSON bytes                                            |
| - deserializes bytes to TeamMessage                                   |
| - delegates I/O to self._transport                                    |
+--------------------------+--------------------------------------------+
                           |
                           v
+-----------------------------------------------------------------------+
| Transport interface                                                   |
| deliver(recipient, data: bytes)                                      |
| fetch(agent, limit, consume)                                         |
| count(agent)                                                         |
| list_recipients()                                                    |
| close()                                                              |
+--------------------------+--------------------------------------------+
                           |
             +-------------+-----------------------------+
             |                                           |
             v                                           v
+-----------------------------+            +-------------------------------+
| FileTransport               |            | P2PTransport                  |
| - atomic writes (tmp+rename)|            | - ZeroMQ P2P                 |
| - sorted glob reads         |            | - peer discovery             |
| - durable file queue        |            | - fallback to FileTransport  |
+-----------------------------+            +-------------------------------+
```

## 2. Config resolution flow

Order of precedence for transport backend:

1. `CLAWTEAM_TRANSPORT` environment variable
2. persisted config (`load_config().transport`)
3. default: `file`

Additional notes:

- In P2P mode, bind identity can be derived from `AgentIdentity` when not explicitly set.
- Keep defaults deterministic to avoid behavior drift between shell and spawned workers.

## 3. FileTransport send/receive sequence

1. Sender calls `MailboxManager.send(...)`.
2. `MailboxManager` builds `TeamMessage` and serializes JSON bytes.
3. `FileTransport.deliver(...)` writes a temporary file and renames atomically.
4. Receiver calls `receive()`:
   - list message files in order
   - read/deserialize
   - delete file if `consume=true`

## 4. P2PTransport when peer is online

1. Sender resolves peer endpoint from `peers/*.json`.
2. Sender validates peer liveness (pid/process check where applicable).
3. Sender pushes payload via ZeroMQ.
4. Receiver consumes message from socket.
5. Receiver may also check fallback file queue for missed/offline payloads.

## 5. P2PTransport when peer is offline

1. Sender fails to resolve reachable peer endpoint.
2. Sender falls back to `FileTransport.deliver(...)`.
3. Peer later comes online.
4. Receiver drains fallback file queue via normal receive flow.

This guarantees eventual delivery even when direct P2P is temporarily unavailable.

## 6. P2P channel vs shared filesystem (orthogonal roles)

- P2P channel:
  - transient and low-latency
  - good for notifications, requests, short-lived signaling
- Shared filesystem:
  - persistent and inspectable
  - good for team config, plans, task boards, logs, artifacts

These two layers are intentionally orthogonal: real-time signal path plus durable state path.

## 7. Module dependency map

- `clawteam/transport/base.py`: transport interface
- `clawteam/transport/file.py`: file-backed transport
- `clawteam/transport/p2p.py`: P2P transport with fallback
- `clawteam/team/mailbox.py`: MailboxManager transport consumer
- `clawteam/config.py`: default transport resolution
- `clawteam/identity.py`: identity and optional bind-agent behavior

## 8. Runtime dependency notes

- required: `typer`, `pydantic`, `rich`
- optional (P2P): `pyzmq`
