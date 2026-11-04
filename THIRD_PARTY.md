# Upstream components

The encrypted recovery package includes the working binaries together with their
corresponding pinned upstream source archives and upstream license files:

- Kernel: https://github.com/amnezia-vpn/amneziawg-linux-kernel-module/tree/4569c4c67f3a57414969260cafbbd04694fbaae0
- Go engine: https://github.com/amnezia-vpn/amneziawg-go/tree/b5928efb6ca19f0153958460c3d141f04abc5c2e
- Tools: https://github.com/amnezia-vpn/amneziawg-tools/tree/v3.1.20260812

The bootstrap uses the Ubuntu package `python3-cryptography`, rather than vendoring
its code. Documentation: https://cryptography.io/

Fresh relay installs fetch LucX directly from its pinned official release and
verify SHA256. The release archive, including its upstream license files and CLI,
is installed without invoking the upstream installer's optional system upgrades.
Source: https://github.com/AlexeyLCP/lucx-ui/tree/v3.11.0-lucx.339

Pinned geodata is fetched from the same upstream provider used by the official
LucX installer: https://github.com/Loyalsoldier/v2ray-rules-dat

No LucX distribution, panel login, or customer database is committed here.
