import json, toml

# 1. load your JSON service‑account key
with open("video-gen-storage-364229b2dba4.json", "r") as jf:
    svc = json.load(jf)

# 2. wrap it under the [gcp_service_account] table
wrapped = {"gcp_service_account": svc}

# 3. dump to a .toml file
with open("secrets.toml", "w") as tf:
    toml.dump(wrapped, tf)
