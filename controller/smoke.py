"""Quick connectivity check: python -m controller.smoke [SIM_URL]"""
import sys

from controller.api import SimClient


def main(url: str) -> None:
    c = SimClient(url)
    print("state:", c.state())
    for w in c.workflows():
        wid = w["workflow_id"]
        d = c.workflow(wid)
        g = d["governance"]
        print(wid, "| primary:", d["objective"]["primary"],
              "| approver_hours:", g["approver_hours"],
              "| auto_apply:", g["auto_apply"]["enabled"], g["auto_apply"]["allowed_dims"],
              "| config version:", c.config(wid)["version"])
    print("history chunks:", c.chunks("history"))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8700")