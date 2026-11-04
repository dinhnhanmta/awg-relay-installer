# Upstream components

The encrypted recovery package includes the working binaries together with their
corresponding pinned upstream source archives and upstream license files:

- Kernel: https://github.com/amnezia-vpn/amneziawg-linux-kernel-module/tree/4569c4c67f3a57414969260cafbbd04694fbaae0
- Go engine: https://github.com/amnezia-vpn/amneziawg-go/tree/b5928efb6ca19f0153958460c3d141f04abc5c2e
- Tools: https://github.com/amnezia-vpn/amneziawg-tools/tree/v3.1.20260812

The bootstrap uses the Ubuntu package `python3-cryptography`, rather than vendoring
its code. Documentation: https://cryptography.io/

The owner supplies and installs LucX separately. No LucX distribution or customer
database is included in this repository.
