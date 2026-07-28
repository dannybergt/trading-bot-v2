"""Guard the reverse-proxy trust configuration.

The backend derives the caller address from `request.client.host` for the auth
rate-limit buckets and the audit IP fingerprints. Behind a reverse proxy that
address is the proxy's, not the caller's, unless uvicorn is told which peers
may set `X-Forwarded-For`. Uvicorn's own default (`127.0.0.1`) never matches
the private compose network the nginx frontend sits on, so the value has to be
configured explicitly -- and it has to be configured identically in the image
and in the compose file, otherwise a compose deploy silently reverts the fix.

These tests pin the two failure modes that would bring the defect back:

1. Drift between the image default and the compose passthrough default.
2. A widened value (`*` or a public range) that would let any caller forge its
   own address and bypass the per-client rate limits it is meant to enforce.
"""
import ipaddress
import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = PROJECT_ROOT / "ops" / "docker" / "backend.Dockerfile"
COMPOSE_FILE = PROJECT_ROOT / "docker-compose.yml"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"

VAR = "FORWARDED_ALLOW_IPS"


def _dockerfile_default() -> str:
    match = re.search(rf"^ENV {VAR}=(\S+)$", DOCKERFILE.read_text(), re.MULTILINE)
    assert match, f"{VAR} ENV default missing from {DOCKERFILE.name}"
    return match.group(1)


def _compose_default() -> str:
    match = re.search(rf"^\s*{VAR}: \$\{{{VAR}:-([^}}]+)\}}$", COMPOSE_FILE.read_text(), re.MULTILINE)
    assert match, f"{VAR} passthrough missing from {COMPOSE_FILE.name}"
    return match.group(1)


def _env_example_default() -> str:
    match = re.search(rf"^{VAR}=(\S+)$", ENV_EXAMPLE.read_text(), re.MULTILINE)
    assert match, f"{VAR} missing from {ENV_EXAMPLE.name}"
    return match.group(1)


class ForwardedAllowIpsTests(unittest.TestCase):
    def test_image_and_compose_defaults_match(self):
        """A compose deploy must not silently override the image default."""
        self.assertEqual(_dockerfile_default(), _compose_default())

    def test_env_example_documents_the_same_default(self):
        self.assertEqual(_dockerfile_default(), _env_example_default())

    def test_default_is_not_wildcard(self):
        """`*` makes uvicorn return the leftmost X-Forwarded-For entry, which is
        fully caller-controlled -- the rate-limit keys would become forgeable."""
        for value in (_dockerfile_default(), _compose_default()):
            self.assertNotIn("*", value)

    def test_default_trusts_only_loopback_and_private_ranges(self):
        """Trusting a public range would let hosts outside the deployment forge
        their address; the proxy chain only ever appears as loopback/private."""
        for entry in _dockerfile_default().split(","):
            entry = entry.strip()
            network = ipaddress.ip_network(entry, strict=False)
            self.assertTrue(
                network.is_private or network.is_loopback,
                f"{entry} is neither private nor loopback",
            )


if __name__ == "__main__":
    unittest.main()
