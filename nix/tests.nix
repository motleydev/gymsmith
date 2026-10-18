# `nix flake check` runs the same suite as tests/run.sh, inside the Nix sandbox: no network, no
# key, against the pinned Python and Chromium.
{ runCommand, src, roomsmith }:
let rt = roomsmith.passthru;
in
runCommand "roomsmith-tests"
{
  nativeBuildInputs = [ rt.python ] ++ (if rt.chrome != null then [ rt.chrome ] else [ ]);
} ''
  cp -r ${src} repo
  chmod -R u+w repo
  cd repo
  export HOME=$TMPDIR ROOMSMITH_HOME=$PWD FONTCONFIG_FILE=${rt.fonts} PYTHONDONTWRITEBYTECODE=1
  ${if rt.chrome != null then "export ROOMSMITH_CHROME=${rt.chromeBin} ROOMSMITH_CHROME_NO_SANDBOX=1" else ""}
  patchShebangs bin tests
  bash tests/run.sh
  touch $out
''
