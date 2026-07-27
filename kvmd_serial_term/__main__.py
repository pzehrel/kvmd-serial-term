"""Entry point — parse CLI args, load config, start the daemon."""

import argparse
import asyncio
import logging

from kvmd_serial_term.config import load_config, DEFAULT_CONFIG_PATH
from kvmd_serial_term.serial_handler import SerialHandler
from kvmd_serial_term.server import SerialTermServer

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PiKVM Serial Console daemon"
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to YAML config file (default: {DEFAULT_CONFIG_PATH})",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s [%(levelname)s] %(message)s",
    )

    cfg = load_config(args.config)

    # The daemon opens the serial port lazily on first client connection,
    # so we don't open it here — the server calls handler.open() on demand.
    handler = SerialHandler(cfg.serial)

    server = SerialTermServer(cfg.server, handler)

    async def run() -> None:
        await server.start()
        # Run forever until SIGTERM
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            await handler.close()
            await server.stop()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Daemon stopped")


if __name__ == "__main__":
    main()
