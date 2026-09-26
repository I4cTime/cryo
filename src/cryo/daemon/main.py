"""cryod — the Cryo daemon. Run as root (systemd unit provided)."""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from cryo.daemon import config as config_mod
from cryo.daemon import state as state_mod
from cryo.daemon.engine import Engine
from cryo.daemon.server import Server
from cryo.hw.thermal import COMPATIBILITY_URL, UnsupportedHardware

# sysexits.h EX_CONFIG: "unsupported machine" is a configuration verdict,
# not a crash — cryod.service lists it in RestartPreventExitStatus so an
# unsupported box gets one clear message instead of a restart loop.
EXIT_UNSUPPORTED = 78


def main() -> None:
    logging.basicConfig(
        level=logging.DEBUG if "-v" in sys.argv else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("cryod")

    if os.geteuid() != 0:
        log.error("cryod needs root (writes platform_profile, fan boosts, USB). Run via systemd or sudo.")
        sys.exit(1)

    overrides = config_mod.load_overrides()
    cfg = config_mod.merged(overrides)
    try:
        engine = Engine(cfg, state_mod.load())
    except UnsupportedHardware as exc:
        log.error("Cryo can't run on this machine: %s", exc)
        log.error(
            "Run `cryoctl doctor` for the full verdict and see %s. Not restarting.",
            COMPATIBILITY_URL,
        )
        sys.exit(EXIT_UNSUPPORTED)
    server = Server(engine, overrides)
    log.info(
        "Cryo daemon up — profile=%s fans=%d curves=%s auto=%s%s",
        engine.thermal.profile() or "n/a",
        len(engine.thermal.fans),
        cfg["fan_curves"]["enabled"],
        cfg["auto"]["enabled"],
        " (LIMITED)" if engine.thermal.missing else "",
    )
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        log.info("bye")


if __name__ == "__main__":
    main()
