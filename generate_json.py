import email
import gzip
import json
from datetime import datetime
from multiprocessing import Pool
from pathlib import Path
from os import environ
import requests
import yaml

with open("config.yml") as config_file:
    config = yaml.safe_load(config_file)

base_url = config["base_url"]
json_url = config["json_url"]


class OpenWrtJsonUpdater:
    def __init__(self, version, destination="./output"):
        self.version = version

        self.version_dir = f"snapshots"
        if self.version != "SNAPSHOT":
            print(f"Using releases/{self.version}/")
            self.version_dir = f"releases/{self.version}"

        self.output_path = Path(destination) / self.version_dir
        self.output_path.mkdir(exist_ok=True, parents=True)

    def get_targets(self):
        req = requests.get(f"{base_url}/{self.version_dir}/targets/?json-targets")
        if req.status_code != 200:
            print(f"Failed to load targets for {self.version}")

        return req.json()

    def parse_origin_packages(self, path, repo):
        packages_text = requests.get(f"{base_url}/{self.version_dir}/{path}").text

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

    def get_packages(self, target):
        arch = config["targets"].get(target, {}).get("arch")
        if not arch:
            print(f"Unknown arch for {target}")
            return

        print(target, arch)
        target_path = self.output_path / target
        target_path.mkdir(exist_ok=True, parents=True)

        packages = self.parse_origin_packages(
            f"targets/{target}/packages/Packages.manifest", target
        )

        for repo in config.get("repos", []):
            packages.update(
                self.parse_origin_packages(
                    f"packages/{arch}/{repo}/Packages.manifest", repo
                )
            )

        if not packages:
            print(f"No packages for {target}")
            return {}

        return packages

    def get_profiles(self, target):
        print(target)
        req = requests.get(f"{json_url}/{self.version_dir}/{target}/profiles.json")
        if req.status_code != 200:
            print(f"No profiles.json found for {target}")
            return {}, {}

        metadata = req.json()
        profiles = metadata.pop("profiles", {})

        for name, data in profiles.items():
            data["target"] = target

        return metadata, profiles

    def write_json_packages(self, target, packages):
        target_path = self.output_path / target

        json_manifest = json.dumps(packages, sort_keys=True, separators=(",", ":"))
        json_index = json.dumps(
            list(packages.keys()), sort_keys=True, separators=(",", ":")
        )

        versions = dict(map(lambda p: (p["package"], p["version"]), packages.values()))

        json_versions = json.dumps(versions, sort_keys=True, separators=(",", ":"))

        (target_path / "manifests.json").write_text(json_manifest)

        with gzip.open(target_path / "manifests.json.gz", "wb") as f:
            f.write(json_manifest.encode())

        (target_path / "index.json").write_text(json_index)

        with gzip.open(target_path / "index.json.gz", "wb") as f:
            f.write(json_index.encode())

        (target_path / "versions.json").write_text(json_versions)

        with gzip.open(target_path / "versions.json.gz", "wb") as f:
            f.write(json_versions.encode())

    def write_json_profiles(self, profiles):
        json_profiles = json.dumps(profiles, sort_keys=True, separators=(",", ":"))

        (self.output_path / "profiles.json").write_text(json_profiles)

        with gzip.open(self.output_path / "profiles.json.gz", "wb") as f:
            f.write(json_profiles.encode())

        json_targets = json.dumps(
            config["targets"], sort_keys=True, separators=(",", ":")
        )

        (self.output_path / "targets.json").write_text(json_targets)

        with gzip.open(self.output_path / "targets.json.gz", "wb") as f:
            f.write(json_targets.encode())

    def update_packages(self, target):
        packages = self.get_packages(target)
        if packages:
            self.write_json_packages(target, packages)

    def update_all(self, threads: int = 10):
        targets = self.get_targets()

        with Pool(threads) as pool:
            pool.map(self.update_packages, targets)

        with Pool(threads) as pool:
            responses = pool.map(self.get_profiles, targets)
            profiles = {"profiles": {}}
            for metadata, profiles_target in responses:
                profiles.update(metadata)
                profiles["profiles"].update(profiles_target)

                profiles.pop("target", None)

                self.write_json_profiles(profiles)



for version in config["versions"]:
    updater = OpenWrtJsonUpdater(version, config["output_dir"])
    updater.update_all(5)
