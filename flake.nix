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

      apps = forAll (pkgs:
        let
          pkg = self.packages.${pkgs.system};
          app = name: args: {
            type = "app";
            program = toString (pkgs.writeShellScript "roomsmith-${name}" ''
              exec ${pkg.roomsmith}/bin/design ${args} "$@"
            '');
          };
        in {
          default = { type = "app"; program = "${pkg.roomsmith}/bin/design"; };
          design = { type = "app"; program = "${pkg.roomsmith}/bin/design"; };
          serve = app "serve" "serve";
          mcp = app "mcp" "mcp";
          cve-scan = { type = "app"; program = "${pkg.cve-scan}/bin/roomsmith-cve-scan"; };
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
