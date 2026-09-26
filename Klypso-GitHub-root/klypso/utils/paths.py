from pathlib import Path


def user_storage(root, user_id):
    path = Path(root) / "users" / str(user_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_child(root, child):
    root = Path(root).resolve()
    target = (root / child).resolve()
    target.relative_to(root)
    return target
