# The `design` CLI, with everything it shells out to pinned beside it.
#
# Fonts are pinned too: the drawings are laid out in Helvetica/Arial metrics, and Liberation Sans
# is metric-compatible with Arial, so a plan rasterised on any machine lines up the same way.
{ lib
, stdenv
, stdenvNoCC
, python3
, makeWrapper
, makeFontsConf
, liberation_ttf
, dejavu_fonts
, chromium
}:
let
  python = python3.withPackages (ps: [ ps.pyyaml ]);
  fonts = makeFontsConf { fontDirectories = [ liberation_ttf dejavu_fonts ]; };
  # nixpkgs builds Chromium for Linux only. On macOS the engine finds Google Chrome in
  # /Applications, or wherever $ROOMSMITH_CHROME points.
  chrome = if stdenv.hostPlatform.isLinux then chromium else null;
  chromeBin = if chrome != null then "${chrome}/bin/chromium" else "";
in
stdenvNoCC.mkDerivation {
  pname = "roomsmith";
  version = "1.1.0";

  # Only what runs, plus what `design demo` needs. Docs, tests and the worked example are not.
  src = lib.fileset.toSource {
    root = ../.;
    fileset = lib.fileset.unions [
      ../engine ../config/templates ../config/catalog-item.yml ../config/demo
      ../catalog/rogue-rml-390f.yml
    ];
  };

  nativeBuildInputs = [ makeWrapper ];
  dontConfigure = true;
  dontBuild = true;

  installPhase = ''
    runHook preInstall
    mkdir -p $out/share/roomsmith $out/bin
    cp -r engine config catalog $out/share/roomsmith/
    # -P: never put the current directory on sys.path, so a stray engine/ or yaml.py in
    # whatever directory you run `design` from cannot be imported in place of the real one.
    makeWrapper ${python}/bin/python3 $out/bin/design \
      --add-flags "-P -m engine.cli" \
      --prefix PYTHONPATH : $out/share/roomsmith \
      --set PYTHONDONTWRITEBYTECODE 1 \
      --set-default FONTCONFIG_FILE ${fonts} \
      ${lib.optionalString (chrome != null) "--set-default ROOMSMITH_CHROME ${chromeBin}"}
    runHook postInstall
  '';

  passthru = { inherit python fonts chrome chromeBin; };

  meta = {
    description = "Measured room design: rooms, revisions, an equipment catalog and photoreal renders";
    license = lib.licenses.mit;
    mainProgram = "design";
    platforms = lib.platforms.unix;
  };
}
