
import json


def load_item_json(file_path):

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        db = {}
        for item in data:
            name = item.get("name").lower().strip()
            db[name] = {
                "display_name": item.get("displayName", name),
                "stack_size": item.get("stackSize", 64),
            }
        return db
    except FileNotFoundError:
        print(f"✗ 文件未找到: {file_path}")
        return None