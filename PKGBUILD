# Maintainer: Linky6tt <228955968+Linky6tt@users.noreply.github.com>
pkgname=heat-my-desktop
pkgver=1.0.1
pkgrel=1
pkgdesc="Controlled CPU thermal expansion utility to prevent cold-boot crashes."
arch=('any')
url="https://github.com/Linky6tt/heat-my-desktop"
license=('GPL-3.0-or-later')
depends=(
    'python'
    'python-pyqt6'
    'lm_sensors'
    'hicolor-icon-theme'
)
source=("${pkgname}-${pkgver}.tar.gz::https://github.com/Linky6tt/heat-my-desktop/archive/refs/tags/v${pkgver}.tar.gz")
sha256sums=('SKIP') # Replace with actual sha256 (via updpkgsums) before pushing to AUR

package() {
    cd "${pkgname}-${pkgver}"

    # 1. Install all python modules and scripts to /usr/lib/heat-my-desktop
    install -dm755 "$pkgdir/usr/lib/$pkgname"
    cp -r main.py cli.py gui thermal service "$pkgdir/usr/lib/$pkgname/"

    # 2. Create the executable launcher script in /usr/bin
    install -dm755 "$pkgdir/usr/bin"
    cat << 'EOF' > "$pkgdir/usr/bin/heat-my-desktop"
#!/usr/bin/env bash
exec python3 /usr/lib/heat-my-desktop/main.py "$@"
EOF
    chmod 755 "$pkgdir/usr/bin/heat-my-desktop"

    # 3. Install Desktop shortcut
    install -Dm644 heat-my-desktop.desktop "$pkgdir/usr/share/applications/heat-my-desktop.desktop"

    # 4. Install App SVG Icon
    install -Dm644 assets/heat-my-desktop.svg "$pkgdir/usr/share/icons/hicolor/scalable/apps/heat-my-desktop.svg"

    # 5. Install License
    install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
