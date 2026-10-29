#!/usr/bin/env python3
"""Check the Xcode 16 IORPC compatibility patch against Apple's XNU 8796 source."""

import json
import os
import subprocess
import tempfile
import urllib.request


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELEASE_URL = (
    "https://raw.githubusercontent.com/apple-oss-distributions/"
    "distribution-macOS/macos-135/release.json"
)


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "J2Prime-XNU-CI"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def main():
    release = json.loads(fetch(RELEASE_URL))
    xnu_tag = next(
        project["tag"] for project in release["projects"]
        if project.get("project") == "xnu"
    )
    header = fetch(
        "https://raw.githubusercontent.com/apple-oss-distributions/"
        f"xnu/{xnu_tag}/iokit/DriverKit/IORPC.h"
    )

    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, "iokit", "DriverKit", "IORPC.h")
        os.makedirs(os.path.dirname(target))
        with open(target, "wb") as stream:
            stream.write(header)

        patch = os.path.join(
            ROOT, "xnu", "patches", "0959-xcode16-iorpc-kernelcontent.patch"
        )
        check = subprocess.run(
            ["git", "apply", "--check", patch], cwd=tmp,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if check.returncode == 0:
            subprocess.run(["git", "apply", patch], cwd=tmp, check=True)

        with open(target, encoding="utf-8") as stream:
            source = stream.read()
        start = source.find("struct IORPC {")
        end = source.find("\n};", start)
        if start < 0 or end < 0:
            raise SystemExit("XNU source has no recognizable IORPC struct")
        field = source.find("IORPCMessage     * kernelContent;", start, end)
        if field < 0:
            raise SystemExit("IORPC.kernelContent was not added to the IORPC struct")
        guard = source.rfind("#ifdef KERNEL", start, field)
        guard_end = source.find("#endif /* KERNEL */", field, end)
        if guard < start or guard_end < field:
            raise SystemExit("IORPC.kernelContent is missing or outside the guarded IORPC struct")

    print(f"Xcode 16 IORPC compatibility patch validated against {xnu_tag}")


if __name__ == "__main__":
    main()
