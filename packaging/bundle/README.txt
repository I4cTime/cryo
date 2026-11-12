Cryo @VERSION@ - command center for Alienware and Dell G-Series laptops on Linux
https://github.com/I4cTime/cryo

INSTALL

    sudo ./install.sh

Run it from this directory, with sudo from your own account. It needs an
x86_64 glibc distro (glibc 2.34 or newer) with systemd, and network
access: it downloads about 300 MB, Python 3.13 (about 35 MB, kept in
/opt/cryo/python so a system Python upgrade cannot break Cryo) and Cryo's
dependencies (about 265 MB, mostly Qt), each checked against the hash in
requirements.txt. Lighting needs the system's libusb-1.0 (every desktop
install has it). No git, uv or pip is needed.

What it installs:

    /opt/cryo                         the program (Python, environment, uninstaller)
    /usr/local/bin/cryoctl, cryo-gui  the commands, for every user
    /etc/systemd/system/cryod.service and cryod-resume.service (enabled)
    /usr/local/share/applications/cryo.desktop and icons under
    /usr/local/share/icons/hicolor
    /etc/cryo/config.json             written only if missing; grants your
                                      group access to the daemon
    /var/lib/cryo                     daemon state

On a machine Cryo cannot drive, cryod exits with status 78 and stays
stopped; run cryoctl doctor to see why.

UPGRADE

Extract the newer bundle and run its install.sh. The new environment is
built beside the old one and swapped in; your settings are kept.

UNINSTALL

    sudo /opt/cryo/uninstall.sh            keeps /etc/cryo and /var/lib/cryo
    sudo /opt/cryo/uninstall.sh --purge    removes them too

When cryod is running, the uninstaller first hands the firmware back to
stock (balanced profile, fan boost 0, CPU cap 100).

Cryo is free software under the GNU GPL, version 3 or later (see LICENSE).
