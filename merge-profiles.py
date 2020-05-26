import email
import gzip
import json
from datetime import datetime
from multiprocessing import Pool
from pathlib import Path

import requests
import yaml

with open("config.yml") as config_file:
    config = yaml.safe_load(config_file)

base_url = "https://images.aparcar.org/rebuild"

output_path = Path(config["output_dir"])
output_path.mkdir(exist_ok=True, parents=True)


def update_target(target):
    print(target)
    request = requests.get(f"{base_url}/{target}/profiles.json")
    if request.status_code != 200:
        print(f"No profiles.json found for {target}")
        return {}, {}

    metadata = request.json()
    profiles = metadata.pop("profiles", {})

    for name, data in profiles.items():
        data["target"] = target

    return metadata, profiles


profiles = {"profiles": {}}

with Pool(10) as pool:
    responses = pool.map(update_target, config.get("targets", {}).keys())
    for metadata, profiles_target in responses:
        profiles.update(metadata)
        profiles["profiles"].update(profiles_target)

    profiles.pop("target")


json_profiles = json.dumps(profiles, sort_keys=True, separators=(",", ":"))

(output_path / "profiles.json").write_text(json_profiles)

with gzip.open(output_path / "profiles.json.gz", "wb") as f:
    f.write(json_profiles.encode())

json_targets = json.dumps(config["targets"], sort_keys=True, separators=(",", ":"))

(output_path / "targets.json").write_text(json_targets)

with gzip.open(output_path / "targets.json.gz", "wb") as f:
    f.write(json_targets.encode())
