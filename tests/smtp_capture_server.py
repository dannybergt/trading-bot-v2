#!/usr/bin/env python3
import asyncio
import sys


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    writer.write(b"220 smtp-capture.local ESMTP ready\r\n")
    await writer.drain()

    data_mode = False
    message_lines: list[str] = []

    while not reader.at_eof():
      raw_line = await reader.readline()
      if not raw_line:
          break

      line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")

      if data_mode:
          if line == ".":
              print("=== SMTP MESSAGE BEGIN ===", flush=True)
              for message_line in message_lines:
                  print(message_line, flush=True)
              print("=== SMTP MESSAGE END ===", flush=True)
              message_lines.clear()
              data_mode = False
              writer.write(b"250 Message accepted\r\n")
              await writer.drain()
              continue

          if line.startswith(".."):
              line = line[1:]
          message_lines.append(line)
          continue

      upper_line = line.upper()
      if upper_line.startswith("EHLO") or upper_line.startswith("HELO"):
          writer.write(b"250-smtp-capture.local\r\n250 AUTH PLAIN LOGIN\r\n")
      elif upper_line.startswith("MAIL FROM:") or upper_line.startswith("RCPT TO:"):
          writer.write(b"250 OK\r\n")
      elif upper_line == "DATA":
          data_mode = True
          writer.write(b"354 End data with <CR><LF>.<CR><LF>\r\n")
      elif upper_line == "QUIT":
          writer.write(b"221 Bye\r\n")
          await writer.drain()
          break
      elif upper_line == "NOOP" or upper_line == "RSET":
          writer.write(b"250 OK\r\n")
      else:
          writer.write(b"250 OK\r\n")

      await writer.drain()

    writer.close()
    await writer.wait_closed()


async def main() -> None:
    server = await asyncio.start_server(handle_client, host="0.0.0.0", port=1025)
    addresses = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    print(f"SMTP capture server listening on {addresses}", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
