"""Inputs for regression tests; expected outcomes use the independent oracle."""
from dataclasses import replace
from src.common import Block, Header, sign
from tests.c_helpers import CHAIN, load_cfg
from tests.independent_oracle import digest


def block_for(proposer, txs=(), **changes):
    """Construct expected commitments without the production executor or hash."""
    data, nonces = dict(proposer.state.data), dict(proposer.state.nonces)
    for tx in txs:
        data[tx.key], nonces[tx.sender] = tx.value, tx.nonce
    hd = Header(proposer.height, proposer.round, -1, proposer.last_hash(),
                digest([sorted(data.items()), sorted(nonces.items())]),
                digest([[[t.sender, t.nonce, t.key, t.value], t.sig] for t in txs]), proposer.name)
    hd = replace(hd, **changes)
    return Block(replace(hd, sig=sign(proposer.kp, "HEADER:" + CHAIN, hd.body())), tuple(txs))



def fast_cfg(**changes):
    cfg = load_cfg(gst=0, delta=1, heights=2, rate_limit=None, peer_block=None,
                   duplicate_probability=0, pre_gst_reorder_probability=0,
                   base_timeout=40, timeout_inc=10, t_end=10000)
    cfg.update(changes)
    return cfg
