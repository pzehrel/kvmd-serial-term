# Maintainer: pzehrel
pkgname=kvmd-serial-term
pkgver=0.1.0
pkgrel=1
pkgdesc="PiKVM Serial Terminal extra — serial console access to target machine via USB-TTL"
url="https://github.com/pzehrel/kvmd-serial-term"
license=(GPL3)
arch=(any)
depends=(
    python-aiohttp
    python-pyserial
    python-pyserial-asyncio
    python-yaml
)
makedepends=(
    python-build
    python-installer
    python-wheel
    python-setuptools
)
source=("$pkgname-$pkgver.tar.gz::$url/archive/v$pkgver.tar.gz")
md5sums=(SKIP)

build() {
    cd "$srcdir/$pkgname-$pkgver"
    python -m build --wheel --no-isolation
}

package() {
    cd "$srcdir/$pkgname-$pkgver"

    # Python package
    python -m installer --destdir="$pkgdir" dist/*.whl

    # Config
    install -Dm644 config.default.yaml "$pkgdir/etc/kvmd/serial-term.yaml"

    # systemd service
    install -Dm644 kvmd-serial-term.service "$pkgdir/usr/lib/systemd/system/kvmd-serial-term.service"

    # PiKVM extra manifest + nginx (dir name matches manifest path)
    install -Dm644 manifest.yaml "$pkgdir/usr/share/kvmd/extras/serial-term/manifest.yaml"
    install -Dm644 nginx.ctx-server.conf "$pkgdir/usr/share/kvmd/extras/serial-term/nginx.ctx-server.conf"

    # SVG icon
    install -Dm644 web/serial.svg "$pkgdir/usr/share/kvmd/web/share/svg/serial.svg"

    # Web assets
    install -d "$pkgdir/usr/share/kvmd/web/kvmd-serial-term"
    cp -r web/*.html web/*.js web/*.css "$pkgdir/usr/share/kvmd/web/kvmd-serial-term/"
}
