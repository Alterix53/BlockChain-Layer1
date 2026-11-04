"""Test-only ledger oracle: do not call production hash/encoding/execution/verify."""
import hashlib
import struct

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def canonical(value):
    if value is None:
        return b"N"
    if isinstance(value, bool):
        return b"B" + bytes([value])
    if isinstance(value, int):
        return b"I" + struct.pack(">q", value)
    if isinstance(value, str):
        raw = value.encode("utf-8")
        return b"S" + struct.pack(">I", len(raw)) + raw
    if isinstance(value, bytes):
        return b"Y" + struct.pack(">I", len(value)) + value
    if isinstance(value, (list, tuple)):
        return b"L" + struct.pack(">I", len(value)) + b"".join(map(canonical, value))
    raise TypeError(type(value))


def digest(value):
    return hashlib.sha256(canonical(value)).digest()


def signature(pk, domain, body, sig):
    Ed25519PublicKey.from_public_bytes(pk).verify(sig, canonical(domain) + canonical(body))


def assert_finalized(nodes, heights=None, expected_data=None, expected_nonces=None):
    honest = [nd for nd in nodes if not getattr(nd, "is_byzantine", False)]
    assert honest, "oracle requires honest nodes"
    chains = []
    for nd in honest:
        if heights is not None:
            assert nd.done and len(nd.ledger) == heights, (nd.name, len(nd.ledger), heights)
        data, nonces, chain = {}, {}, []
        parent = hashlib.sha256(b"genesis").digest()
        for height, block in enumerate(nd.ledger, 1):
            hd = block.header
            assert hd.height == height and hd.parent == parent, (nd.name, height, "parent/height")
            assert hd.proposer == nd.ctx["vals"][(height + hd.round) % len(nd.ctx["vals"])], "proposer"
            signature(nd.ctx["vpks"][hd.proposer], "HEADER:" + nd.ctx["chain_id"],
                      [hd.height, hd.round, hd.pol_round, hd.parent, hd.state_hash, hd.tx_root, hd.proposer], hd.sig)
            tx_bodies = []
            for tx in block.txs:
                body = [tx.sender, tx.nonce, tx.key, tx.value]
                signature(nd.ctx["acct_pks"][tx.sender], "TX:" + nd.ctx["chain_id"], body, tx.sig)
                assert "/" not in tx.sender and tx.key.partition("/")[0] == tx.sender, "namespace"
                assert type(tx.nonce) is int and tx.nonce == nonces.get(tx.sender, 0) + 1, "nonce/replay"
                data[tx.key], nonces[tx.sender] = tx.value, tx.nonce
                tx_bodies.append([body, tx.sig])
            assert hd.tx_root == digest(tx_bodies), "transaction commitment"
            state_root = digest([sorted(data.items()), sorted(nonces.items())])
            assert hd.state_hash == state_root, "state commitment"
            parent = digest([height, hd.parent, hd.state_hash, hd.tx_root])
            cert = nd.certificates[height]
            assert cert.height == height and cert.block_hash == parent, "certificate target"
            assert len(cert.signatures) >= 2 * nd.ctx["f"] + 1, "certificate quorum"
            assert set(cert.signatures) <= set(nd.ctx["vals"]), "certificate membership"
            for voter, sig in cert.signatures.items():
                signature(nd.ctx["vpks"][voter], "VOTE:" + nd.ctx["chain_id"],
                          ["PRECOMMIT", height, cert.round, parent, voter], sig)
            chain.append(parent)
        assert nd.state.data == data and nd.state.nonces == nonces, "actual state differs from replay"
        if expected_data is not None:
            assert data == expected_data, (nd.name, data, expected_data)
        if expected_nonces is not None:
            assert nonces == expected_nonces, (nd.name, nonces, expected_nonces)
        chains.append(chain)
    for chain in chains:
        for other in chains:
            common = min(len(chain), len(other))
            assert chain[:common] == other[:common], "honest fork"
