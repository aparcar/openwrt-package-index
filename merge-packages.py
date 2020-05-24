import email
import gzip
import json
from datetime import datetime
from pathlib import Path

import requests
import yaml

with open("config.yml") as config_file:
    config = yaml.safe_load(config_file)

base_url = "https://downloads.cdn.openwrt.org/snapshots/"

output_path = Path("output")


def parse_origin_packages(path, repo):
    packages_text = requests.get(base_url + path).text

    packages = {}
    linebuffer = ""
    for line in packages_text.splitlines():
        if line == "":
            parser = email.parser.Parser()
            package = parser.parsestr(linebuffer)
            package_name = package.get("Package")
            if package_name:
                packages[package_name] = dict(
                    (name.lower().replace("-", "_"), val)
                    for name, val in package.items()
                )
                packages[package_name]["repo"] = repo
            else:
                print(f"Something wired about {package}")
            linebuffer = ""
        else:
            linebuffer += line + "\n"

    return packages


for target, arch in config.get("targets", {}).items():
    print(target)
    target_path = output_path / target
    target_path.mkdir(exist_ok=True, parents=True)

    packages = {}
    packages.update(
        parse_origin_packages(f"targets/{target}/packages/Packages.manifest", target)
    )
    for repo in config.get("repos", []):
        packages.update(
            parse_origin_packages(f"packages/{arch}/{repo}/Packages.manifest", repo)
        )

    if not packages:
        print(f"No packages for {target}")
        continue

    json_manifest = json.dumps(packages, sort_keys=True, separators=(",", ":"))
    json_index = json.dumps(
        list(packages.keys()), sort_keys=True, separators=(",", ":")
    )
    (target_path / "manifests.json").write_text(json_manifest)

    with gzip.open(target_path / "manifests.json.gz", "wb") as f:
        f.write(json_manifest.encode())

    (target_path / "index.json").write_text(json_index)

    with gzip.open(target_path / "index.json.gz", "wb") as f:
        f.write(json_index.encode())
