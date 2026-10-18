# A container image built from the same closure as the package, for running Roomsmith where Nix
# is not installed. No shell, no package manager, non-root, data on a volume.
#
#   docker load < $(nix build .#docker --print-out-paths)
#   docker run --rm -p 127.0.0.1:8765:8765 -v roomsmith:/data roomsmith        # design serve
#   docker run --rm -v roomsmith:/data roomsmith check --project house/garage
#
# Publish the port on 127.0.0.1 only. The server checks the Host header, and the one-time login
# link it prints is the only credential.
{ dockerTools, cacert, roomsmith }:
dockerTools.buildLayeredImage {
  name = "roomsmith";
  tag = roomsmith.version;
  contents = [ roomsmith cacert ];
  enableFakechroot = true;
  fakeRootCommands = ''
    mkdir -p /data /tmp
    chown 1000:1000 /data
    chmod 1777 /tmp
  '';
  config = {
    Entrypoint = [ "${roomsmith}/bin/design" ];
    Cmd = [ "serve" "--host" "0.0.0.0" ];
    User = "1000:1000";
    WorkingDir = "/data";
    Env = [
      "ROOMSMITH_HOME=/data"
      "HOME=/tmp"
      "SSL_CERT_FILE=${cacert}/etc/ssl/certs/ca-bundle.crt"
      # Chromium's sandbox needs user namespaces most container runtimes do not grant. Pages
      # are still script-free and network-free by CSP; see engine/chrome.py.
      "ROOMSMITH_CHROME_NO_SANDBOX=1"
    ];
    ExposedPorts."8765/tcp" = { };
    Volumes."/data" = { };
  };
}
