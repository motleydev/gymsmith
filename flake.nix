{
  description = "Roomsmith — measured room design with Claude Code: projects, rooms, revisions, an equipment catalog, and a local photo/annotation service";

  # One pinned nixpkgs release for everything: Python, Chromium, fonts, the CVE scanner.
  # `nix flake update` moves the pin; `nix run .#cve-scan` says what that bought you.
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

  outputs = { self, nixpkgs }:
    let
      lib = nixpkgs.lib;
      systems = [ "x86_64-linux" "aarch64-linux" "aarch64-darwin" "x86_64-darwin" ];
      forAll = f: lib.genAttrs systems (system: f (import nixpkgs {
        inherit system;
        # The only unfree package anywhere in this flake, and only in the `agents` shell.
        config.allowUnfreePredicate = pkg: builtins.elem (lib.getName pkg) [ "claude-code" ];
      }));
    in
    {
      packages = forAll (pkgs:
        let roomsmith = pkgs.callPackage ./nix/package.nix { };
        in {
          default = roomsmith;
          inherit roomsmith;
          cve-scan = pkgs.callPackage ./nix/cve-scan.nix { inherit roomsmith; };
        } // lib.optionalAttrs pkgs.stdenv.hostPlatform.isLinux {
          # docker load < $(nix build .#docker --print-out-paths)
          docker = pkgs.callPackage ./nix/docker.nix { inherit roomsmith; };
        });

      # Every `design` subcommand is also an app:  nix run .#check   nix run .#rev -- diff r1..r2
      # Arguments after `--` go to the command. Run from inside a checkout, data lives in the
      # checkout (as ./bin/design does); anywhere else, in ~/.local/share/roomsmith.
      apps = forAll (pkgs:
        let
          pkg = self.packages.${pkgs.system};
          rt = pkg.roomsmith.passthru;
          commands = {
            demo = "a ready-made garage gym in two revisions, to try everything on";
            init = "scaffold a room: init house/garage [--from room|kitchen]";
            rooms = "every project, room and revision; HEAD marked";
            use = "make a room the default: use house/garage";
            status = "where the job is: room, directions, renders, spend, gates";
            gates = "every approval gate and what it guards";
            check = "validate geometry, layouts and catalog clearances";
            approve = "record an approval: approve room-model --note ...";
            rev = "revisions: rev list | new | switch r1 | diff r1..r2";
            catalog = "the equipment catalog: catalog list | show | check | verify | new <id>";
            drawings = "measured drawings: drawings 01, or drawings --shell";
            pack = "one direction end to end, then stop: pack 01";
            render = "photoreal views: render [01] [--dry] [--backend B]";
            report = "build the PDF report";
            serve = "photo upload, annotation, revision flip and catalog review";
            consult = "a second opinion from another model via OpenRouter";
            mcp = "the MCP server (stdio)";
          };
          run = name: args: pkgs.writeShellScript "roomsmith-${name}" ''
            if [ -z "''${ROOMSMITH_HOME:-}" ] && [ -f flake.nix ] && [ -f engine/cli.py ]; then
              export ROOMSMITH_HOME="$PWD"
            fi
            exec ${pkg.roomsmith}/bin/design ${args} "$@"
          '';
          mk = name: desc: {
            type = "app";
            program = toString (run name name);
            meta.description = desc;
          };
          test = pkgs.writeShellScript "roomsmith-test" ''
            [ -f tests/run.sh ] || { echo "run this from the root of a checkout" >&2; exit 1; }
            export PATH=${lib.makeBinPath ([ rt.python ] ++ lib.optional (rt.chrome != null) rt.chrome)}:$PATH
            export FONTCONFIG_FILE=${rt.fonts} PYTHONDONTWRITEBYTECODE=1
            ${lib.optionalString (rt.chrome != null) "export ROOMSMITH_CHROME=${rt.chromeBin}"}
            exec bash tests/run.sh "$@"
          '';
        in
        lib.mapAttrs mk commands // {
          default = { type = "app"; program = toString (run "help" ""); meta.description = "the design CLI"; };
          design = { type = "app"; program = toString (run "design" ""); meta.description = "the design CLI"; };
          test = { type = "app"; program = toString test; meta.description = "the test suite, with the pinned Python and Chromium"; };
          cve-scan = { type = "app"; program = "${pkg.cve-scan}/bin/roomsmith-cve-scan"; meta.description = "CVE scan of the runtime closure"; };
        });

      devShells = forAll (pkgs:
        let
          rt = self.packages.${pkgs.system}.roomsmith.passthru;
          base = [ rt.python pkgs.git pkgs.jq pkgs.vulnix ]
            ++ lib.optional (rt.chrome != null) rt.chrome;
          hook = ''
            # In a checkout, data lives beside the code, exactly as ./bin/design always worked.
            export ROOMSMITH_HOME="''${ROOMSMITH_HOME:-$PWD}"
            export FONTCONFIG_FILE="${rt.fonts}"
            ${lib.optionalString (rt.chrome != null) ''export ROOMSMITH_CHROME="${rt.chromeBin}"''}
            export PYTHONDONTWRITEBYTECODE=1
            # `design check` instead of `./bin/design check`, running this checkout's code.
            export PATH="$PWD/bin:$PATH"
          '';
        in {
          default = pkgs.mkShell { packages = base; shellHook = hook; };
          # Everything above plus the agent CLIs, pinned with the rest. Claude Code is unfree.
          agents = pkgs.mkShell {
            packages = base ++ [ pkgs.claude-code pkgs.codex ];
            shellHook = hook;
          };
        });

      checks = forAll (pkgs: {
        tests = pkgs.callPackage ./nix/tests.nix {
          src = self;
          roomsmith = self.packages.${pkgs.system}.roomsmith;
        };
      });

      formatter = forAll (pkgs: pkgs.nixpkgs-fmt);
    };
}
