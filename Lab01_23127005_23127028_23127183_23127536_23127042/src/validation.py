"""Runtime safety, completion and determinism checks for honest nodes."""


def check_safety(nodes):
    """
    Kiểm tra bất biến an toàn (Safety Invariant):
    Tuyệt đối không bao giờ được phép có 2 khối khác nhau (mã băm khác nhau)
    được chốt tại cùng một chiều cao height giữa các validator trung thực.
    Loại trừ các node Byzantine cố ý làm sai ledger.
    """
    honest_nodes = [x for x in nodes if not getattr(x, "is_byzantine", False)]
    if not honest_nodes:
        raise ValueError("không có node trung thực để kiểm")
    max_height = max(len(x.ledger) for x in honest_nodes) if honest_nodes else 0
    for h in range(max_height):
        # Lấy hash của block tại height h của mọi honest node đã chốt height này
        hashes = {x.ledger[h].hash() for x in honest_nodes if len(x.ledger) > h}
        if len(hashes) > 1:
            raise AssertionError(f"FORK phát hiện ở height {h + 1}: {hashes}!")
    return max_height

def check_completion(nodes, heights):
    check_safety(nodes)
    honest = [node for node in nodes if not getattr(node, "is_byzantine", False)]
    lagging = {node.name: len(node.ledger) for node in honest
               if len(node.ledger) != heights or not node.done}
    if lagging:
        raise RuntimeError(f"INCOMPLETE: chưa chốt đủ {heights} block: {lagging}")
    if len({node.state.hash() for node in honest}) != 1:
        raise RuntimeError("state hash của các node trung thực không hội tụ")
    for node in honest:
        if node.state.hash() != node.ledger[-1].header.state_hash:
            raise RuntimeError(f"state của {node.name} không khớp block đã chốt")
    return honest[0]

def snapshot(nodes):
    return [(node.name, tuple(b.hash() for b in node.ledger), node.state.hash())
            for node in nodes if not getattr(node, "is_byzantine", False)]
